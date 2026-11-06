#!/usr/bin/env python3
"""Linux 4.x.y 内核每日学习工作流。

职责边界：
- 本脚本负责确定性工作：已分析索引、加权随机选题、源码/调用关系提取、
  归档、统计与飞书推送。
- 语义分析由 Agent 阅读生成的 prompt 后完成；prompt 是唯一的分析入口。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

WORKDIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
STATE_DIR = Path(__file__).resolve().parent / ".state"

NOTE_ROOTS = {
    "mm", "kernel", "fs", "drivers", "block", "net", "security",
    "ipc", "lib", "arch", "init", "include",
}
C_KINDS = {".c"}
SOURCE_SUFFIXES = {".c", ".h", ".S"}
CORE_PREFIX = re.compile(
    r"^(?:__?do_|sys_|vfs_|.*_init$|.*_alloc$|.*_free$|.*_map$|.*_unmap$|"
    r".*_probe$|.*_remove$|.*_open$|.*_release$|.*_read$|.*_write$)"
)


def load_config() -> dict:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["workspace"] = os.environ.get("KERNEL_DAILY_WORKSPACE", cfg["workspace"])
    cfg["kernel"]["src"] = os.environ.get("KERNEL_SRC_PATH", cfg["kernel"]["src"])
    cfg["kernel"]["repo"] = os.environ.get("KERNEL_REPO", cfg["kernel"]["repo"])
    cfg["kernel"]["branch"] = os.environ.get("KERNEL_BRANCH", cfg["kernel"]["branch"])
    cfg["archive_root"] = os.environ.get(
        "KERNEL_DAILY_ARCHIVE", cfg["archive_root"]
    )
    cfg["feishu"]["user_id"] = os.environ.get(
        "FEISHU_USER_ID", cfg["feishu"].get("user_id", "")
    )
    cfg["feishu"]["chat_id"] = os.environ.get(
        "FEISHU_CHAT_ID", cfg["feishu"].get("chat_id", "")
    )
    return cfg


def src_root(cfg: dict) -> Path:
    return Path(cfg["kernel"]["src"]).expanduser().resolve()


def archive_root(cfg: dict) -> Path:
    return Path(cfg["archive_root"]).expanduser().resolve()


def git_head(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def kernel_version(path: Path) -> str:
    try:
        txt = (path / "Makefile").read_text(encoding="utf-8", errors="ignore")
        vals = {}
        for key in ("VERSION", "PATCHLEVEL", "SUBLEVEL"):
            m = re.search(rf"^{key}\s*=\s*(\d+)", txt, re.M)
            vals[key] = m.group(1) if m else "?"
        return f"{vals['VERSION']}.{vals['PATCHLEVEL']}.{vals['SUBLEVEL']}"
    except Exception:
        return "unknown"


def now_date() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


# --------------------------------------------------------------------------
# 已学习索引
# --------------------------------------------------------------------------

def build_analyzed_index(cfg: dict) -> tuple[set[str], set[str]]:
    """返回 (已分析函数名集合, 已分析 source:name 集合)。"""
    workspace = Path(cfg["workspace"])
    names: set[str] = set()
    pairs: set[str] = set()

    for p in workspace.rglob("*.md"):
        parts = p.relative_to(workspace).parts
        if len(parts) < 3 or parts[0] not in NOTE_ROOTS:
            continue
        source = parts[1]
        if Path(source).suffix not in SOURCE_SUFFIXES or p.stem == "README":
            continue
        names.add(p.stem)
        pairs.add(f"{parts[0]}/{source}:{p.stem}")

    # README 中的链接条目（例如 mm/README.md -> mm/page_alloc.c/xxx.md）
    for p in workspace.rglob("README.md"):
        try:
            if p.relative_to(workspace).parts[0] not in NOTE_ROOTS:
                continue
            text = read_text(p)
        except Exception:
            continue
        for m in re.finditer(r"\[([^\]]+)\]\((.+?\.md)\)", text):
            name = m.group(1).strip("` ")
            target = m.group(2)
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
                continue
            names.add(name)
            fm = re.search(r"(?:^|/)([^/]+\.(?:c|h|S))/", target)
            if fm:
                pairs.add(f"{fm.group(1)}:{name}")

    # 每日归档索引中也可能记录历史条目
    index = archive_root(cfg) / "INDEX.md"
    if index.exists():
        for name in re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", read_text(index)):
            names.add(name)

    return names, pairs


# --------------------------------------------------------------------------
# 源码解析
# --------------------------------------------------------------------------

def ctags_functions(path: Path) -> list[dict]:
    try:
        out = subprocess.check_output(
            ["ctags", "-f", "-", "-x", "--language-force=C",
             "--kinds-C=f", str(path)],
            text=True, stderr=subprocess.DEVNULL, timeout=30,
        )
    except Exception:
        return []
    funcs = []
    for line in out.splitlines():
        m = re.match(r"^(\S+)\s+function\s+(\d+)\s+(\S+)\s+(.*)$", line)
        if not m:
            continue
        name, start, _src, signature = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        funcs.append({"name": name, "start": start, "signature": signature, "file": str(path)})
    return funcs


def find_function_range_safe(path: Path, start_line: int) -> tuple[int, int] | None:
    """跳过注释/字符串的花括号配对，返回函数起止行（1-based）。"""
    lines = read_text(path).splitlines()
    if start_line < 1 or start_line > len(lines):
        return None

    depth = 0
    started = False
    in_block = False
    quote = ""
    escaped = False

    for i in range(start_line - 1, min(len(lines), start_line + 4000)):
        line = lines[i]
        j = 0
        while j < len(line):
            ch = line[j]
            nxt = line[j + 1] if j + 1 < len(line) else ""
            if in_block:
                if ch == "*" and nxt == "/":
                    in_block = False
                    j += 2
                    continue
                j += 1
                continue
            if quote:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = ""
                j += 1
                continue
            if ch == "/" and nxt == "/":
                break
            if ch == "/" and nxt == "*":
                in_block = True
                j += 2
                continue
            if ch in ("'", '"'):
                quote = ch
                j += 1
                continue
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}" and started:
                depth -= 1
                if depth == 0:
                    return start_line, i + 1
            j += 1
    return None


def exported_symbol(path: Path, name: str) -> bool:
    text = read_text(path)
    return bool(re.search(rf"EXPORT_SYMBOL(?:_GPL)?\s*\(\s*{re.escape(name)}\s*\)", text))


def function_static(path: Path, start_line: int, signature: str) -> bool:
    if re.search(r"\bstatic\b", signature):
        return True
    lines = read_text(path).splitlines()
    prefix = " ".join(lines[max(0, start_line - 4):start_line - 1])
    return bool(re.search(r"\bstatic\b", prefix))


@dataclass
class Candidate:
    name: str
    file: str
    line_start: int
    line_end: int
    subsystem: str
    type: str
    is_static: bool
    exported: bool
    local_calls: int
    weight: float


def candidate_cache_path(cfg: dict, subsystem: str) -> Path:
    head = git_head(src_root(cfg))
    safe = subsystem.replace("/", "_")
    return STATE_DIR / f"candidates-{safe}-{head[:12]}.json"


def collect_candidates(cfg: dict, sub: dict, analyzed_names: set[str]) -> list[Candidate]:
    cache = candidate_cache_path(cfg, sub["name"])
    raw: list[dict] = []
    if cache.exists():
        try:
            raw = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            raw = []

    if not raw:
        root = src_root(cfg)
        excludes = [str(root / e) for e in sub.get("exclude_paths", [])]
        files: list[Path] = []
        for rel in sub["paths"]:
            base = root / rel
            if base.is_dir():
                files.extend(base.rglob("*.c"))
            elif base.suffix == ".c":
                files.append(base)
        files = sorted(set(f for f in files if f.is_file()))
        for path in files:
            if any(str(path).startswith(ex + "/") for ex in excludes):
                continue
            try:
                lines = read_text(path).splitlines()
                funcs = ctags_functions(path)
            except Exception:
                continue
            for fn in funcs:
                name = fn["name"]
                if name.startswith("__") and len(name) < 3:
                    continue
                if name in {"main", "usage", "help"}:
                    continue
                rng = find_function_range_safe(path, fn["start"])
                if not rng:
                    continue
                start, end = rng
                # 过滤明显不是函数体的定义（例如宏/声明）
                body = "\n".join(lines[start - 1:min(end, start + 6)])
                if "{" not in body:
                    continue
                static = function_static(path, start, fn["signature"])
                local_calls = max(
                    0,
                    len(re.findall(rf"\b{re.escape(name)}\b\s*\(", "\n".join(lines))) - 1,
                )
                if static and local_calls < 3:
                    continue
                raw.append({
                    "name": name,
                    "file": path.relative_to(root).as_posix(),
                    "line_start": start,
                    "line_end": end,
                    "subsystem": sub["name"],
                    "type": "function",
                    "is_static": static,
                    "exported": exported_symbol(path, name),
                    "local_calls": local_calls,
                })
        # 同名函数只保留一个定义（优先全局/导出函数）
        dedup: dict[str, dict] = {}
        for item in raw:
            old = dedup.get(item["name"])
            if old is None or (item["exported"] and not old["exported"]):
                dedup[item["name"]] = item
        raw = list(dedup.values())
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    out: list[Candidate] = []
    for item in raw:
        if item["name"] in analyzed_names:
            continue
        weight = 1.0
        if item["exported"]:
            weight += 3.0
        if CORE_PREFIX.search(item["name"]):
            weight += 2.0
        if item["local_calls"] >= 10:
            weight += 1.5
        elif item["local_calls"] >= 3:
            weight += 0.5
        out.append(Candidate(**item, weight=weight))
    return out


def weighted_pick(candidates: list[Candidate]) -> Candidate:
    total = sum(c.weight for c in candidates)
    r = random.SystemRandom().uniform(0, total)
    upto = 0.0
    for c in candidates:
        upto += c.weight
        if upto >= r:
            return c
    return candidates[-1]


def select_target(cfg: dict) -> dict:
    analyzed_names, analyzed_pairs = build_analyzed_index(cfg)
    root = src_root(cfg)
    if not root.exists() or not (root / "Makefile").exists():
        raise SystemExit(f"未找到内核源码：{root}\n请先运行 {Path(__file__).parent}/prepare_source.sh")

    weights = [s["weight"] for s in cfg["priority"]]
    subs = list(cfg["priority"])
    # 按权重选子系统；若候选为空则降级到下一个
    for _ in range(len(subs)):
        r = random.SystemRandom().uniform(0, sum(weights))
        upto = 0.0
        chosen_idx = 0
        for i, w in enumerate(weights):
            upto += w
            if upto >= r:
                chosen_idx = i
                break
        sub = subs[chosen_idx]
        cands = collect_candidates(cfg, sub, analyzed_names)
        if cands:
            target = weighted_pick(cands)
            break
        weights[chosen_idx] = 0
    else:
        raise SystemExit("所有优先子系统均无未分析候选，请人工检查索引。")

    version = kernel_version(root)
    today = now_date()
    report = archive_root(cfg) / today[:4] / today[5:7] / today
    report.mkdir(parents=True, exist_ok=True)
    report_name = f"{target.subsystem.replace('/', '_')}_{target.name}.md"
    report_path = report / report_name

    payload = {
        "selected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": today,
        "kernel_version": version,
        "kernel_head": git_head(root),
        "kernel_src": str(root),
        "target": asdict(target),
        "candidates_considered": len(cands),
        "analyzed_total": len(analyzed_names),
        "analyzed_pairs": len(analyzed_pairs),
        "report_path": str(report_path),
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "current-target.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


# --------------------------------------------------------------------------
# 上下文与 prompt
# --------------------------------------------------------------------------

def caller_map(path: Path, funcs: list[dict] | None = None) -> list[tuple[int, int, str]]:
    funcs = funcs or ctags_functions(path)
    out = []
    for fn in funcs:
        rng = find_function_range_safe(path, fn["start"])
        if rng:
            out.append((rng[0], rng[1], fn["name"]))
    return out


def find_callers(cfg: dict, target: dict) -> list[dict]:
    root = src_root(cfg)
    name = target["name"]
    pattern = rf"\b{re.escape(name)}\b\s*\("
    try:
        proc = subprocess.run(
            ["rg", "-n", "--no-heading", "-g", "*.c", "-g", "*.h", pattern, str(root)],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return []
    hits = []
    if proc.returncode not in (0, 1):
        return []
    for line in proc.stdout.splitlines():
        m = re.match(r"^(.*?):(\d+):(.*)$", line)
        if not m:
            continue
        path = Path(m.group(1))
        lineno = int(m.group(2))
        text = m.group(3).strip()
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        # 跳过目标自身的函数头和函数体
        if rel == target["file"] and target["line_start"] <= lineno <= target["line_end"]:
            continue
        if re.match(rf"^\s*(?:static\s+)?(?:[A-Za-z_]\w*\s+)+\**{re.escape(name)}\s*\(", text):
            continue
        hits.append((rel, lineno, text, path))

    # 按文件解析调用者所在函数，找最近的包裹函数
    cache: dict[str, list[tuple[int, int, str]]] = {}
    callers, seen = [], set()
    for rel, lineno, text, path in hits:
        if rel not in cache:
            cache[rel] = caller_map(path)
        containing = [(s, e, n) for s, e, n in cache[rel] if s <= lineno <= e and n != name]
        if not containing:
            continue
        s, e, caller = min(containing, key=lambda x: x[1] - x[0])
        key = (rel, caller)
        if key in seen:
            continue
        seen.add(key)
        callers.append({
            "caller": caller,
            "file": rel,
            "line": lineno,
            "context": text[:180],
            "range": f"{s}-{e}",
        })
        if len(callers) >= 8:
            break
    return callers


def find_callees(cfg: dict, target: dict) -> list[dict]:
    root = src_root(cfg)
    path = root / target["file"]
    lines = read_text(path).splitlines()
    body = "\n".join(lines[target["line_start"] - 1:target["line_end"]])
    keywords = {
        "if", "for", "while", "switch", "return", "sizeof", "typeof", "case",
        "do", "else", "goto", "break", "continue", "defined", "likely", "unlikely",
        "IS_ENABLED", "ARRAY_SIZE", "offsetof", "container_of", "min", "max",
        "WARN_ON", "WARN_ON_ONCE", "BUG_ON", "BUILD_BUG_ON",
    }
    counts: dict[str, int] = {}
    for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", body):
        name = m.group(1)
        if name in keywords or name == target["name"]:
            continue
        counts[name] = counts.get(name, 0) + 1
    helper_re = re.compile(
        r"^(?:[a-z_]*lock|lock_|unlock|spin_|raw_|rcu_|atomic_|smp_|"
        r"trace_|printk|pr_|WARN|BUG|kmalloc|kzalloc|kfree|memcpy|memset|"
        r"list_|hlist_|bit_|test_|set_|clear_|get_|put_)"
    )
    out = []
    for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
        out.append({
            "name": name,
            "calls": count,
            "kind": "helper" if helper_re.match(name) else "core",
        })
    return out


PROMPT_TEMPLATE = """# 每日内核源码分析任务

你是一名 Linux 内核源码分析 Agent。请**严格**只分析下面给定的目标，不要另选函数。
分析语言为中文，输出 Markdown，必须包含以下 5 个章节：
1. 功能作用
2. 关键数据结构
3. 核心逻辑流程图（Mermaid flowchart TD，并附 3~8 条要点）
4. 调用关系（4.1 调用者表格、4.2 被调用者分类、4.3 Mermaid flowchart LR）
5. 易错点 / 边界场景 / 设计权衡

最后附「核心源码片段」，只保留关键行并注明 `{{FILE}}:{{START}}-{{END}}`。

注意事项：
- 所有结论必须能从给定源码或调用关系中核实；不确定的地方标注「需结合配置/架构确认」。
- 调用者表格至少 3 行（若源码中不足则列出全部）。
- 流程图中的条件、循环、错误路径要与代码一致。
- 不要重复已有的同名分析，不要编造函数或行号。

## 目标元信息

- 日期：{{DATE}}
- 内核版本：{{VERSION}}（{{BRANCH}}，HEAD `{{HEAD}}`）
- 子系统：{{SUBSYSTEM}}
- 源文件：{{FILE}}:{{START}}-{{END}}
- 类型：function
- static：{{STATIC}}
- EXPORT_SYMBOL：{{EXPORTED}}
- 本文件内调用次数：{{LOCAL_CALLS}}
- 候选池大小：{{CANDIDATES}}；已分析函数名：{{ANALYZED_TOTAL}}

## 源码上下文

```c
{{SOURCE}}
```

## 源码中出现的调用者（已解析到包裹函数）

{{CALLERS}}

## 目标函数直接调用的函数（按出现次数）

{{CALLEES}}

## 输出要求

把完整分析写入：`{{REPORT_PATH}}`
写完后运行：`python3 {{SCRIPT}} archive --report {{REPORT_PATH}}`
"""


def render_prompt(cfg: dict, payload: dict, callers: list[dict], callees: list[dict]) -> str:
    target = payload["target"]
    root = src_root(cfg)
    path = root / target["file"]
    lines = read_text(path).splitlines()
    start = target["line_start"]
    end = target["line_end"]
    ctx_start = max(1, start - 20)
    ctx_end = min(len(lines), end + 20)
    source = "\n".join(f"{i:5d}  {lines[i - 1]}" for i in range(ctx_start, ctx_end + 1))

    caller_rows = (
        "| 调用方 | 位置 | 调用点上下文 |\n|--------|------|--------------|\n"
        + "\n".join(
            f"| `{c['caller']}` | `{c['file']}:{c['line']}` | `{c['context']}` |"
            for c in callers
        )
    ) if callers else "| 调用方 | 位置 | 调用点上下文 |\n|--------|------|--------------|\n| 未找到 | - | - |"
    callee_rows = (
        "| 被调用者 | 出现次数 | 分类 |\n|----------|----------|------|\n"
        + "\n".join(f"| `{c['name']}` | {c['calls']} | {c['kind']} |" for c in callees)
    ) if callees else "| 被调用者 | 出现次数 | 分类 |\n|----------|----------|------|\n| 未找到 | 0 | - |"

    def repl(txt: str) -> str:
        return (txt
                .replace("{{FILE}}", target["file"])
                .replace("{{START}}", str(start))
                .replace("{{END}}", str(end))
                .replace("{{DATE}}", payload["date"])
                .replace("{{VERSION}}", payload["kernel_version"])
                .replace("{{BRANCH}}", cfg["kernel"]["branch"])
                .replace("{{HEAD}}", payload["kernel_head"][:12])
                .replace("{{SUBSYSTEM}}", target["subsystem"])
                .replace("{{STATIC}}", "是" if target["is_static"] else "否")
                .replace("{{EXPORTED}}", "是" if target["exported"] else "否")
                .replace("{{LOCAL_CALLS}}", str(target["local_calls"]))
                .replace("{{CANDIDATES}}", str(payload["candidates_considered"]))
                .replace("{{ANALYZED_TOTAL}}", str(payload["analyzed_total"]))
                .replace("{{SOURCE}}", source)
                .replace("{{CALLERS}}", caller_rows)
                .replace("{{CALLEES}}", callee_rows)
                .replace("{{REPORT_PATH}}", payload["report_path"])
                .replace("{{SCRIPT}}", str(Path(__file__).resolve())))

    body = PROMPT_TEMPLATE
    return repl(body)


def prepare_context(cfg: dict, payload: dict) -> Path:
    target = payload["target"]
    callers = find_callers(cfg, target)
    callees = find_callees(cfg, target)
    prompt = render_prompt(cfg, payload, callers, callees)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path = STATE_DIR / "current-prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    context = {"callers": callers, "callees": callees, "prompt_path": str(prompt_path)}
    (STATE_DIR / "current-context.json").write_text(
        json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return prompt_path


# --------------------------------------------------------------------------
# 归档与索引
# --------------------------------------------------------------------------

def load_current(cfg: dict, report: str | None = None) -> dict:
    p = STATE_DIR / "current-target.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        if report:
            payload["report_path"] = report
        return payload
    if report:
        return {"report_path": report, "date": now_date()}
    raise SystemExit("没有当前选题，请先运行 select")


def parse_report(path: Path) -> dict:
    text = read_text(path)
    lines = [l.strip() for l in text.splitlines()]
    name = ""
    for line in lines:
        m = re.match(r"^# 每日内核源码分析[：:]\s*(.+)$", line)
        if m:
            name = m.group(1).strip()
            break
    date = ""
    sub = ""
    source = ""
    for line in lines:
        m = re.match(r"- \*\*日期\*\*[：:]\s*(.+)", line)
        if m:
            date = m.group(1).strip()
        m = re.match(r"- \*\*子系统\*\*[：:]\s*(.+)", line)
        if m:
            sub = m.group(1).strip()
        m = re.match(r"- \*\*源文件\*\*[：:]\s*(.+)", line)
        if m:
            source = m.group(1).strip()
    if not name:
        name = path.stem.split("_", 1)[-1]
    return {"name": name, "date": date or now_date(), "subsystem": sub or "unknown",
            "source": source, "text": text}


def iter_reports(cfg: dict) -> list[Path]:
    root = archive_root(cfg)
    if not root.exists():
        return []
    return sorted(
        (p for p in root.rglob("*.md") if p.name != "INDEX.md" and p.name != "by-subsystem.md"),
        key=lambda p: p.as_posix(),
    )


def rebuild_indexes(cfg: dict) -> None:
    root = archive_root(cfg)
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for p in iter_reports(cfg):
        meta = parse_report(p)
        entries.append({**meta, "path": p.relative_to(root).as_posix()})
    entries.sort(key=lambda e: (e["date"], e["name"]), reverse=True)

    index_lines = [
        "# Linux 内核每日学习索引", "",
        "| 日期 | 子系统 | 目标 | 源码位置 | 分析 |",
        "|------|--------|------|----------|------|",
    ]
    for e in entries:
        index_lines.append(
            f"| {e['date']} | `{e['subsystem']}` | `{e['name']}` | "
            f"`{e['source']}` | [阅读](./{e['path']}) |"
        )
    (root / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    by_sub: dict[str, list[dict]] = {}
    for e in entries:
        by_sub.setdefault(e["subsystem"], []).append(e)
    lines = ["# 按子系统索引", ""]
    for sub in sorted(by_sub):
        lines += [f"## {sub}", "", "| 日期 | 目标 | 源码位置 | 分析 |", "|------|------|----------|------|"]
        for e in by_sub[sub]:
            lines.append(f"| {e['date']} | `{e['name']}` | `{e['source']}` | [阅读](./{e['path']}) |")
        lines.append("")
    (root / "by-subsystem.md").write_text("\n".join(lines), encoding="utf-8")


def update_progress(cfg: dict, meta: dict) -> dict:
    path = archive_root(cfg) / "progress-stats.json"
    data = {"total": 0, "subsystems": {}, "analyzed": [], "last_update": ""}
    if path.exists():
        try:
            data.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    key = f"{meta['subsystem']}:{meta['name']}"
    if key not in data["analyzed"]:
        data["analyzed"].append(key)
        data["total"] = len(data["analyzed"])
        data["subsystems"][meta["subsystem"]] = data["subsystems"].get(meta["subsystem"], 0) + 1
        data["last_update"] = meta["date"]
    data["total"] = len(data["analyzed"])
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def update_readme(cfg: dict, meta: dict, note_path: Path, summary: str) -> None:
    workspace = Path(cfg["workspace"])
    src_file = meta["source"].split(":")[0]
    sub = meta["subsystem"]
    readme = workspace / sub / src_file / "README.md"
    if not readme.exists():
        return
    text = read_text(readme)
    marker = "<!-- kernel-daily:begin -->"
    end_marker = "<!-- kernel-daily:end -->"
    row = f"| {meta['date']} | `{meta['name']}` | {summary.replace('|', '/')[:80]} | [笔记](./{meta['name']}.md) |"
    if marker not in text:
        block = (
            "\n\n<!-- kernel-daily:begin -->\n"
            "## 每日学习记录\n\n"
            "| 日期 | 函数/代码段 | 一句话摘要 | 分析 |\n"
            "|------|------------|------------|------|\n"
            f"{row}\n"
            "<!-- kernel-daily:end -->\n"
        )
        readme.write_text(text.rstrip() + block, encoding="utf-8")
        return
    start = text.index(marker)
    end = text.index(end_marker, start) if end_marker in text[start:] else len(text)
    block = text[start:end]
    if row in block:
        return
    lines = block.splitlines()
    insert_at = None
    for i, line in enumerate(lines):
        if line.startswith("|------|"):
            insert_at = i + 1
            break
    if insert_at is None:
        lines += ["", "| 日期 | 函数/代码段 | 一句话摘要 | 分析 |",
                  "|------|------------|------------|------|", row]
    else:
        lines.insert(insert_at, row)
    text = text[:start] + "\n".join(lines) + ("\n" if end < len(text) else "") + text[end:]
    readme.write_text(text, encoding="utf-8")


def archive_report(cfg: dict, report: Path) -> None:
    if not report.exists():
        raise SystemExit(f"分析报告不存在：{report}")
    meta = parse_report(report)
    payload = load_current(cfg, str(report))
    target = payload.get("target", {})
    if target:
        meta["name"] = target["name"]
        meta["subsystem"] = target["subsystem"]
        meta["source"] = f"{target['file']}:{target['line_start']}-{target['line_end']}"
        meta["date"] = payload.get("date", meta["date"])

    root = archive_root(cfg)
    dest = root / meta["date"][:4] / meta["date"][5:7] / meta["date"] / report.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if report.resolve() != dest.resolve():
        dest.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")

    # 子系统就地归档
    if target:
        note_dir = Path(cfg["workspace"]) / target["subsystem"] / Path(target["file"]).name
        note_dir.mkdir(parents=True, exist_ok=True)
        note = note_dir / f"{target['name']}.md"
        note.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")

        summary = ""
        m = re.search(r"## 1\. 功能作用\s*\n+([^\n]+)", report.read_text(encoding="utf-8"))
        if m:
            summary = m.group(1).strip()
        update_readme(cfg, {**meta, "source": target["file"], "subsystem": target["subsystem"]},
                      note, summary)

    rebuild_indexes(cfg)
    stats = update_progress(cfg, meta)
    print(json.dumps({
        "ok": True,
        "archived": str(dest),
        "in_place": str(note) if target else None,
        "total": stats["total"],
        "subsystems": stats["subsystems"],
    }, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------
# 飞书推送
# --------------------------------------------------------------------------

def publish(cfg: dict, report: Path) -> None:
    if not report.exists():
        raise SystemExit(f"分析报告不存在：{report}")
    text = read_text(report)
    if len(text) > 28000:
        text = text[:28000] + "\n\n> 内容过长已截断，完整版见归档文件。"
    payload = load_current(cfg)
    target = payload.get("target", {})
    date = payload.get("date", now_date())
    version = payload.get("kernel_version", "")
    name = target.get("name", report.stem)
    summary = ""
    m = re.search(r"## 1\. 功能作用\s*\n+([^\n]+)", text)
    if m:
        summary = m.group(1).strip()
    header = (
        f"# 每日内核源码学习 · {date}\n\n"
        f"**目标**：`{name}`  ·  `{target.get('file', '')}:{target.get('line_start', '')}-{target.get('line_end', '')}`\n"
        f"**子系统**：`{target.get('subsystem', '')}`  ·  内核 `{version}`\n"
        f"**一句话**：{summary}\n\n---\n\n"
    )
    content = header + text
    workspace = Path(cfg["workspace"])
    msg_path = STATE_DIR / "feishu-message.md"
    msg_path.write_text(content, encoding="utf-8")
    rel_str = os.path.relpath(msg_path.resolve(), workspace.resolve())
    if rel_str.startswith(".."):
        raise SystemExit("消息文件必须位于 workspace 内，才能通过 lark-cli 相对路径发送")
    key = f"kernel-daily-{date}-{name}"[:50]

    feishu = cfg["feishu"]
    cmd = ["lark-cli", "im", "+messages-send"]
    if feishu.get("chat_id"):
        cmd += ["--chat-id", feishu["chat_id"]]
    else:
        cmd += ["--user-id", feishu["user_id"]]
    cmd += ["--markdown", f"@{rel_str}", "--idempotency-key", key, "--format", "json"]

    proc = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, timeout=120)
    if proc.stdout:
        try:
            out = json.loads(proc.stdout)
        except Exception:
            out = {"raw": proc.stdout.strip()}
    else:
        out = {}
    if proc.returncode != 0 or out.get("ok") is not True:
        print(proc.stdout or proc.stderr, file=sys.stderr)
        raise SystemExit(f"飞书推送失败（exit={proc.returncode}）")
    print(json.dumps(out, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Linux 4.x.y 每日学习工作流")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index", help="重建已分析索引并输出统计")
    p_select = sub.add_parser("select", help="加权随机选择一个未分析函数")
    p_select.add_argument("--no-context", action="store_true")
    sub.add_parser("context", help="重新生成当前选题的 prompt")
    p_archive = sub.add_parser("archive", help="归档报告并更新索引")
    p_archive.add_argument("--report", required=True)
    p_publish = sub.add_parser("publish", help="推送报告到飞书")
    p_publish.add_argument("--report", default="")
    sub.add_parser("status", help="显示学习进度")
    args = parser.parse_args()
    cfg = load_config()

    if args.cmd == "index":
        names, pairs = build_analyzed_index(cfg)
        print(json.dumps({
            "analyzed_names": len(names),
            "analyzed_pairs": len(pairs),
            "kernel_src": str(src_root(cfg)),
            "kernel_version": kernel_version(src_root(cfg)),
        }, ensure_ascii=False, indent=2))
    elif args.cmd == "select":
        payload = select_target(cfg)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if not args.no_context:
            prompt = prepare_context(cfg, payload)
            print(f"\nprompt: {prompt}")
    elif args.cmd == "context":
        payload = load_current(cfg)
        prompt = prepare_context(cfg, payload)
        print(prompt)
    elif args.cmd == "archive":
        payload = load_current(cfg, args.report)
        archive_report(cfg, Path(args.report))
        if payload.get("report_path") != args.report:
            payload["report_path"] = args.report
            (STATE_DIR / "current-target.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    elif args.cmd == "publish":
        report = Path(args.report) if args.report else Path(load_current(cfg)["report_path"])
        publish(cfg, report)
    elif args.cmd == "status":
        path = archive_root(cfg) / "progress-stats.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
