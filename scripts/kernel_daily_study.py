#!/usr/bin/env python3
"""Linux 内核每日学习自动化工具。

职责（分析正文由 Agent 依据本仓库 Skill 生成）：
  pick      扫描已分析文档，按子系统加权随机选取一个未分析过的核心函数，
            从 Linux v4.4 源码抓取函数体，输出 TARGET 元信息 JSON。
  archive   将分析 Markdown 按日期归档，并更新 daily/ 索引与进度统计，
            同时镜像到 {子系统}/{源文件}/{函数}.md。
  publish   将分析摘要推送到飞书（lark-cli），默认发送到当前用户私聊。

示例：
  python3 scripts/kernel_daily_study.py pick --out /tmp/target.json
  python3 scripts/kernel_daily_study.py archive --meta /tmp/target.json --analysis /tmp/analysis.md
  python3 scripts/kernel_daily_study.py publish --meta /tmp/target.json --analysis /tmp/analysis.md

环境变量：
  KERNEL_STUDY_ROOT  默认 /workspace
  KERNEL_VERSION     默认 v4.4（与本仓库文档对应）
  KERNEL_SRC_BASE    默认 jsDelivr 上的 torvalds/linux 对应版本
  FEISHU_CHAT_ID     默认当前用户私聊
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(os.environ.get("KERNEL_STUDY_ROOT", "/workspace"))
VERSION = os.environ.get("KERNEL_VERSION", "v4.4")
_env_base = os.environ.get("KERNEL_SRC_BASE")
SRC_BASES = [_env_base] if _env_base else [
    f"https://cdn.jsdelivr.net/gh/torvalds/linux@{VERSION}",
    "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain",
]
CACHE = Path(os.environ.get(
    "KERNEL_STUDY_CACHE", str(Path.home() / ".cache" / "kernel-study" / VERSION)
))
ARCHIVE = ROOT / "daily"
DEFAULT_CHAT = "oc_b6b08e4754c49d68a85f5e11326c2cad"

# 优先级子系统与权重（Skill 建议：mm 25%、sched 25%、drivers 15%、fs 15%、其余 20%）
PRIORITY = [
    ("mm", 25),
    ("kernel/sched", 25),
    ("drivers", 15),
    ("fs", 15),
    ("kernel", 5),
    ("ipc", 4),
    ("net", 4),
    ("block", 3),
    ("security", 2),
    ("lib", 2),
]

KEYWORDS = {
    "if", "for", "while", "switch", "return", "else", "do", "case", "goto",
    "break", "continue", "sizeof", "typeof", "defined", "typedef", "struct",
    "enum", "union", "static", "extern", "inline", "asm", "volatile",
}


# ---------------------------------------------------------------- 基础工具

def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def date_key(meta: dict | None = None) -> str:
    return (meta or {}).get("date") or dt.date.today().isoformat()


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ------------------------------------------------------- Step 1 已学习索引

def analyzed_set() -> set[str]:
    """从仓库文档目录收集已分析过的函数/结构名。"""
    names: set[str] = set()
    for base in (ROOT / "mm", ROOT / "kernel", ROOT / "drivers", ROOT / "fs",
                 ROOT / "ipc", ROOT / "net", ROOT / "block", ROOT / "security",
                 ROOT / "lib", ROOT / "include", ROOT / "arch", ROOT / "init"):
        if not base.exists():
            continue
        for md in base.rglob("*.md"):
            if md.parent.name in {"res", "dot", "issues", "misc", "src"}:
                continue
            if md.name.lower() == "readme.md":
                continue
            if md.parent.name.endswith((".c", ".h")):
                names.add(md.stem)
    stats = load_json(ARCHIVE / "progress-stats.json", {})
    for item in stats.get("analyzed", []):
        if isinstance(item, dict) and item.get("name"):
            names.add(item["name"])
        elif isinstance(item, str):
            names.add(item)
    return names


# ------------------------------------------------------- Step 2 目标选取

def source_files(subsystem: str) -> list[str]:
    """返回该子系统下已知的源文件（依据仓库中 {源文件}/ 文档目录）。"""
    base = ROOT / subsystem
    files: list[str] = []
    if not base.exists():
        return files
    for d in base.rglob("*"):
        if not d.is_dir() or not d.name.endswith((".c", ".h")):
            continue
        if subsystem == "kernel" and (d.parent.name == "sched" or "sched" in rel(d).split("/")):
            continue
        if any(d.glob("*.md")):
            files.append(rel(d))
    return sorted(files)


def source_url(base: str, repo_path: str) -> str:
    url = f"{base}/{repo_path}"
    if "git.kernel.org" in base:
        url += f"?h={VERSION}"
    return url


def fetch_source(repo_path: str) -> Path | None:
    """下载并缓存内核源码文件（GitHub 镜像优先，kernel.org 兜底）。"""
    cached = CACHE / repo_path.replace("/", "__")
    if cached.exists() and cached.stat().st_size > 0:
        return cached
    CACHE.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(2):
        for base in SRC_BASES:
            req = urllib.request.Request(
                source_url(base, repo_path),
                headers={"User-Agent": "kernel-daily-study/1.0"},
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
                if data:
                    cached.write_bytes(data)
                    return cached
            except (urllib.error.URLError, urllib.error.HTTPError) as exc:
                last_err = exc
    print(f"  ! 抓取失败 {repo_path}: {last_err}", file=sys.stderr)
    return None


def find_body_end(lines: list[str], start_idx: int) -> int:
    """从函数体起始行开始做括号配对，忽略字符串与注释。"""
    depth = 0
    in_block = in_line = in_str = in_chr = False
    i = start_idx
    while i < len(lines):
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
            elif in_line:
                pass
            elif in_str:
                if ch == "\\":
                    j += 2
                    continue
                if ch == '"':
                    in_str = False
            elif in_chr:
                if ch == "\\":
                    j += 2
                    continue
                if ch == "'":
                    in_chr = False
            else:
                if ch == "/" and nxt == "*":
                    in_block = True
                    j += 2
                    continue
                if ch == "/" and nxt == "/":
                    in_line = True
                    j += 2
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "'":
                    in_chr = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i
            j += 1
        in_line = False
        i += 1
    return len(lines) - 1


def find_functions(text: str) -> list[dict]:
    """启发式提取函数定义（仅文件作用域、带函数体）。"""
    lines = text.splitlines()
    funcs: list[dict] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if (not stripped or line[:1] in (" ", "\t")
                or stripped.startswith(("#", "/*", "*", "//", "*/"))):
            i += 1
            continue
        # 收集签名直到 '{' 或 ';'
        sig_lines: list[str] = []
        j = i
        has_brace = False
        while j < n and j < i + 12:
            cur = lines[j]
            if ";" in cur:
                break
            sig_lines.append(cur)
            if "{" in cur:
                has_brace = True
                break
            j += 1
        if not has_brace:
            i += 1
            continue
        sig = " ".join(sig_lines)
        first = sig.strip().split()[0] if sig.strip() else ""
        if first in KEYWORDS or first.startswith(("EXPORT_", "#", "typedef")):
            i += 1
            continue
        if "(" not in sig:
            i += 1
            continue
        m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", sig)
        if not m:
            i += 1
            continue
        name = m.group(1)
        if name in KEYWORDS or len(name) < 2:
            i += 1
            continue
        brace_line = i + len(sig_lines) - 1
        end = find_body_end(lines, brace_line)
        body_size = end - i + 1
        if body_size < 6:
            i = end + 1
            continue
        tail = "\n".join(lines[end:end + 3]) if end + 3 < n else "\n".join(lines[end:])
        exported = bool(re.search(r"EXPORT_SYMBOL(_GPL)?\s*\(\s*" + re.escape(name), tail))
        funcs.append({
            "name": name,
            "line_start": i + 1,
            "line_end": end + 1,
            "static": sig.lstrip().startswith("static"),
            "exported": exported,
            "body_lines": body_size,
        })
        i = end + 1
    return funcs


def is_core(fn: dict) -> bool:
    """核心函数：有实际逻辑体量，或导出给其他模块使用。"""
    if fn["body_lines"] >= 25:
        return True
    return fn["exported"] and fn["body_lines"] >= 15


def weighted_order(items: list[tuple[str, int]]) -> list[str]:
    """按权重做不放回抽样，得到子系统尝试顺序。"""
    pool = list(items)
    ordered: list[str] = []
    while pool:
        chosen = random.choices([s for s, _ in pool], weights=[w for _, w in pool], k=1)[0]
        ordered.append(chosen)
        pool = [(s, w) for s, w in pool if s != chosen]
    return ordered


def pick_target(exclude: set[str], only: str | None = None) -> dict | None:
    subsystems = [(only, 100)] if only else PRIORITY
    ordered = weighted_order(subsystems)
    for sub in ordered:
        all_files = source_files(sub)
        if not all_files:
            print(f"  - {sub}: 无文档化源文件", file=sys.stderr)
            continue
        # 每个子系统最多探测 15 个源文件（随机抽样），并并行抓取
        files = random.sample(all_files, min(15, len(all_files)))
        with ThreadPoolExecutor(max_workers=6) as pool:
            fetched = list(pool.map(fetch_source, files))
        candidates: list[dict] = []
        analyzed_in_sub = 0
        for repo_path, real in zip(files, fetched):
            if not real:
                continue
            text = real.read_text(encoding="utf-8", errors="replace")
            for fn in find_functions(text):
                if fn["name"] in exclude:
                    analyzed_in_sub += 1
                    continue
                if not is_core(fn):
                    continue
                fn["file"] = repo_path
                fn["subsystem"] = sub
                fn["source_path"] = str(real)
                candidates.append(fn)
        if not candidates:
            print(f"  - {sub}: 无未分析核心候选（已分析 {analyzed_in_sub}）", file=sys.stderr)
            continue
        if analyzed_in_sub / max(1, analyzed_in_sub + len(candidates)) > 0.7 and len(ordered) > 1:
            print(f"  - {sub}: 覆盖率过高，降级到下一子系统", file=sys.stderr)
            continue
        # 偏好导出/非 static，并随机
        chosen = random.choice(candidates)
        chosen["type"] = "function"
        chosen["version"] = VERSION
        return chosen
    return None


# ------------------------------------------------------- Step 5 归档索引

def upsert_table_row(path: Path, header: list[str], row: str) -> None:
    """在 Markdown 表格中追加行；完全相同的内容视为重复。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (path.read_text(encoding="utf-8").splitlines()
             if path.exists() else list(header))
    key = row.strip()
    out: list[str] = []
    inserted = False
    for line in lines:
        if line.strip() == key:
            continue  # 去重
        if not inserted and line.startswith("|") and "---" in line:
            out.append(line)
            out.append(row)
            inserted = True
            continue
        out.append(line)
    if not inserted:
        out.append(row)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def update_index(meta: dict, note_rel: str) -> None:
    date = date_key(meta)
    row = (f"| {date} | {meta['subsystem']} | `{meta['name']}` | "
           f"`{meta['file']}:{meta['line_start']}-{meta['line_end']}` | "
           f"[笔记]({note_rel}) |")
    upsert_table_row(
        ARCHIVE / "INDEX.md",
        ["# Linux 内核每日学习索引", "", "| 日期 | 子系统 | 目标 | 源文件 | 笔记 |",
         "| --- | --- | --- | --- | --- |"],
        row,
    )


def update_by_subsystem(meta: dict, note_rel: str) -> None:
    date = date_key(meta)
    row = f"| {date} | `{meta['name']}` | `{meta['file']}` | [笔记]({note_rel}) |"
    path = ARCHIVE / "by-subsystem.md"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 按子系统分类索引\n", encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    section = f"## {meta['subsystem']}\n\n| 日期 | 目标 | 源文件 | 笔记 |\n| --- | --- | --- | --- |"
    if section not in text:
        text = text.rstrip() + "\n\n" + section + "\n"
    path.write_text(text, encoding="utf-8")
    upsert_table_row(path, [], row)


def update_stats(meta: dict) -> dict:
    stats = load_json(ARCHIVE / "progress-stats.json",
                      {"updated": "", "total": 0, "by_subsystem": {}, "analyzed": []})
    record = {
        "name": meta["name"], "file": meta["file"], "subsystem": meta["subsystem"],
        "date": date_key(meta), "line_start": meta["line_start"], "line_end": meta["line_end"],
    }
    added = not any(x.get("name") == record["name"] for x in stats.get("analyzed", [])
                    if isinstance(x, dict))
    if added:
        stats.setdefault("analyzed", []).append(record)
    stats["total"] = len(stats["analyzed"])
    counts = stats.setdefault("by_subsystem", {})
    if added:
        counts[meta["subsystem"]] = counts.get(meta["subsystem"], 0) + 1
    stats["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    dump_json(ARCHIVE / "progress-stats.json", stats)
    return stats


def cmd_archive(args) -> None:
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    meta.setdefault("date", dt.date.today().isoformat())
    analysis = Path(args.analysis).read_text(encoding="utf-8")
    date = date_key(meta)
    y, m, d = date.split("-")
    day_dir = ARCHIVE / y / m / date
    day_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{meta['subsystem'].replace('/', '_')}_{meta['name']}.md"
    note = day_dir / filename
    note.write_text(analysis, encoding="utf-8")
    note_rel = f"{y}/{m}/{date}/{filename}"

    mirror_dir = ROOT / meta["file"]
    mirror = mirror_dir / f"{meta['name']}.md"
    if mirror_dir.is_dir():
        mirror_dir.mkdir(parents=True, exist_ok=True)
        mirror.write_text(analysis, encoding="utf-8")

    update_index(meta, note_rel)
    update_by_subsystem(meta, note_rel)
    stats = update_stats(meta)
    print(json.dumps({
        "note": str(note), "mirror": str(mirror) if mirror.exists() else None,
        "total": stats["total"], "by_subsystem": stats["by_subsystem"],
    }, ensure_ascii=False, indent=2))


# ------------------------------------------------------- Step 6 飞书推送

def build_preview(meta: dict, analysis: str) -> str:
    """把完整分析整理成适合飞书消息的内容（不渲染 Mermaid）。"""
    body = analysis.replace("```mermaid", "```text")  # 飞书不渲染 Mermaid
    if len(body) > 12000:
        body = body[:12000].rstrip() + "\n\n…（完整内容见归档）"
    return body


def cmd_publish(args) -> None:
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    analysis = Path(args.analysis).read_text(encoding="utf-8")
    text = build_preview(meta, analysis)
    chat = args.chat or os.environ.get("FEISHU_CHAT_ID") or DEFAULT_CHAT
    cmd = [
        "lark-cli", "im", "+messages-send",
        "--chat-id", chat,
        "--markdown", "-",
        "--idempotency-key", f"kernel-study-{date_key(meta)}-{meta['name']}"[:50],
    ]
    if args.dry_run:
        print(text)
        return
    proc = subprocess.run(cmd, input=text, text=True, capture_output=True)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise SystemExit(f"飞书推送失败（exit={proc.returncode}）")
    print(proc.stdout)


def cmd_pick(args) -> None:
    exclude = analyzed_set()
    target = pick_target(exclude, only=args.subsystem)
    if not target:
        raise SystemExit("未找到可分析的候选函数：请检查内核源码路径或已学习索引。")
    print(f"已分析索引：{len(exclude)} 个目标", file=sys.stderr)
    print(f"今日目标：{target['name']} ({target['file']}:{target['line_start']}-"
          f"{target['line_end']}, {target['body_lines']} 行)", file=sys.stderr)
    if args.out:
        dump_json(Path(args.out), target)
    print(json.dumps(target, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Linux 内核每日学习自动化工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pick = sub.add_parser("pick", help="随机选取未分析核心函数")
    p_pick.add_argument("--out", help="输出 TARGET JSON 路径")
    p_pick.add_argument("--subsystem", help="仅在该子系统内选取")
    p_pick.set_defaults(func=cmd_pick)

    p_arch = sub.add_parser("archive", help="归档分析并更新索引")
    p_arch.add_argument("--meta", required=True)
    p_arch.add_argument("--analysis", required=True)
    p_arch.set_defaults(func=cmd_archive)

    p_pub = sub.add_parser("publish", help="推送飞书")
    p_pub.add_argument("--meta", required=True)
    p_pub.add_argument("--analysis", required=True)
    p_pub.add_argument("--chat", help="飞书 chat_id，默认环境变量 FEISHU_CHAT_ID")
    p_pub.add_argument("--dry-run", action="store_true")
    p_pub.set_defaults(func=cmd_publish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
