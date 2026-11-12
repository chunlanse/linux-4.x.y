#!/usr/bin/env python3
"""每日内核源码学习 —— 目标选取与源码抽取。

职责（确定性部分，供每日自动化流水线调用）：
  1. 扫描 workspace 中既有的 `子系统/源文件.c/<函数名>.md` 笔记，构建 ANALYZED_SET；
  2. 按子系统权重随机抽取一个子系统（当日已分析比例过高则降权重抽）；
  3. 用 ctags 提取该子系统全部函数定义，过滤已分析项，按「核心度」加权随机选 1 个；
  4. 抽取源码片段（含上下文），输出 JSON 到 daily/.state/selection.json。
分析解读与归档由 Agent 依据该 JSON 完成。

用法:
    python3 daily/scripts/select_target.py [--date YYYY-MM-DD] [--subsystem mm] [--function NAME]
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path

WORKSPACE = Path(os.environ.get("WORKSPACE", "/workspace"))
KERNEL_SRC = Path(os.environ.get("KERNEL_SRC_PATH", os.path.expanduser("~/linux-stable")))
STATE_DIR = WORKSPACE / "daily" / ".state"

# 子系统 -> (源码目录列表, 权重)
SUBSYSTEMS = {
    "mm": (["mm"], 25),
    "sched": (["kernel/sched"], 25),
    "drivers": (["drivers/tty", "drivers/base", "drivers/char"], 15),
    "fs": (["fs"], 15),
    "kernel": (["kernel"], 8),
    "ipc": (["ipc"], 4),
    "lib": (["lib"], 4),
    "init": (["init"], 2),
}

CORE_PREFIX = re.compile(
    r"^(do_|__do_|sys_|__sys_|vfs_|kern_|__.*_(alloc|free|map|unmap|init)$|.*_(alloc|free|map|unmap|init|exit)$)"
)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


_TEXT_CACHE = {}


def read_text(path):
    key = str(path)
    if key not in _TEXT_CACHE:
        try:
            _TEXT_CACHE[key] = Path(path).read_text(errors="ignore")
        except OSError:
            _TEXT_CACHE[key] = ""
    return _TEXT_CACHE[key]


def load_analyzed():
    """返回 {(源文件名, 函数名)}，来源：workspace 中已存在的函数笔记目录结构。"""
    analyzed = set()
    for p in WORKSPACE.rglob("*.md"):
        if ".git" in p.parts:
            continue
        parent = p.parent.name
        if parent.endswith((".c", ".h", ".S")):
            analyzed.add((parent, p.stem))
    return analyzed


def list_functions(src_dirs):
    """ctags 提取函数定义。返回 [{name,file,line,static,exported,callers,score}]"""
    funcs = []
    for d in src_dirs:
        abs_dir = KERNEL_SRC / d
        if not abs_dir.is_dir():
            continue
        out = run(
            ["ctags-universal", "-x", "--kinds-C=f", "-R", str(abs_dir)]
        ).stdout
        for line in out.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 4 or parts[1] != "function":
                continue
            name, lineno, rel = parts[0], int(parts[2]), Path(parts[3])
            path = rel if rel.is_absolute() else KERNEL_SRC / rel
            text = read_text(path)
            if not text:
                continue
            # ctags 给的是签名首行，向前找真正的函数名行
            lines = text.splitlines()
            line_no = lineno
            for i in range(max(0, lineno - 6), min(len(lines), lineno + 3)):
                if re.match(rf"^[A-Za-z_][\w \t\*]*\**\s*{re.escape(name)}\s*\(", lines[i]):
                    line_no = i + 1
                    break
            sig = [lines[line_no - 1]]
            j = line_no - 2
            while j >= 0 and len(sig) < 3 and lines[j].rstrip().endswith(("*", "(", ",")):
                sig.insert(0, lines[j])
                j -= 1
            funcs.append({
                "name": name,
                "file": str(path.relative_to(KERNEL_SRC)),
                "line": line_no,
                "static": "static" in " ".join(sig),
            })
    return funcs


def enrich(funcs, analyzed):
    """基础核心度打分（不含调用点统计，调用点在全仓库一次扫描中批量统计）。"""
    result = []
    for f in funcs:
        key = (Path(f["file"]).name, f["name"])
        if key in analyzed or f["name"] in {"main", "init_module", "cleanup_module"}:
            continue
        text = read_text(KERNEL_SRC / f["file"])
        if not text:
            continue
        exported = bool(
            re.search(rf"EXPORT_SYMBOL(_GPL)?\s*\(\s*{re.escape(f['name'])}\s*\)", text)
        )
        score = 1.0
        if not f["static"]:
            score += 3
        if exported:
            score += 4
        if CORE_PREFIX.match(f["name"]):
            score += 1.5
        f.update(exported=exported, callers=0, score=round(score, 2))
        result.append(f)
    return result


def count_occurrences(names):
    """一次 git grep 扫描统计各标识符在全部已 checkout 源码中的出现次数。"""
    if not names:
        return {}
    pattern = "|".join(re.escape(n) for n in names)
    out = run(
        ["git", "-C", str(KERNEL_SRC), "grep", "-w", "-h", "-o", "-I", "-E", pattern, "--", "*.c", "*.h"]
    ).stdout
    return dict(Counter(out.split()))


@lru_cache(maxsize=None)
def cached_functions(dirs):
    return tuple(list_functions(list(dirs)))


def coverage(src_dirs, analyzed):
    funcs = cached_functions(tuple(src_dirs))
    total = len({f["name"] for f in funcs})
    done = len({f["name"] for f in funcs if (Path(f["file"]).name, f["name"]) in analyzed})
    return total, done


def pick(day, forced_subsystem=None, forced_function=None):
    analyzed = load_analyzed()
    rng = random.Random(day)

    if forced_function:
        for sub, (dirs, _) in SUBSYSTEMS.items():
            for f in list_functions(dirs):
                if f["name"] == forced_function:
                    return sub, f
        sys.exit(f"未在已 checkout 的源码中找到函数 {forced_function}")

    subs = [forced_subsystem] if forced_subsystem else list(SUBSYSTEMS)
    for _ in range(20):
        weights = []
        for s in subs:
            dirs, w = SUBSYSTEMS[s]
            total, done = coverage(dirs, analyzed)
            ratio = done / total if total else 1.0
            weights.append(w * (0.25 if ratio > 0.7 else 1.0))
        sub = rng.choices(subs, weights=weights, k=1)[0]
        cands = [f for f in enrich(list(cached_functions(tuple(SUBSYSTEMS[sub][0]))), analyzed) if f["line"]]
        if cands:
            break
    else:
        sys.exit("所有子系统的核心候选均已分析完毕")

    cands.sort(key=lambda f: (-f["score"], f["name"]))
    pool = cands[: max(40, len(cands) // 10)]
    counts = count_occurrences([f["name"] for f in pool])
    for f in pool:
        f["callers"] = counts.get(f["name"], 0)
        if f["callers"] >= 3:
            f["score"] = round(f["score"] + min(f["callers"], 20) * 0.2, 2)
    weights = [f["score"] for f in pool]
    return sub, rng.choices(pool, weights=weights, k=1)[0]


def extract_source(target, ctx=20):
    path = KERNEL_SRC / target["file"]
    lines = path.read_text(errors="ignore").splitlines()
    start = target["line"]
    # 从定义行向下找到配对的花括号结束
    depth, end, seen = 0, start, False
    for i in range(start - 1, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if "{" in lines[i]:
            seen = True
        if seen and depth <= 0:
            end = i + 1
            break
    lo = max(1, start - ctx)
    hi = min(len(lines), end + ctx)
    return lo, hi, "\n".join(f"{i:>6}\t{lines[i - 1]}" for i in range(lo, hi + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--subsystem", choices=list(SUBSYSTEMS))
    ap.add_argument("--function")
    args = ap.parse_args()

    if not KERNEL_SRC.is_dir():
        sys.exit(f"未找到内核源码: {KERNEL_SRC}，请设置 KERNEL_SRC_PATH")

    sub, target = pick(args.date, args.subsystem, args.function)
    lo, hi, snippet = extract_source(target)

    data = {
        "date": args.date,
        "subsystem": sub,
        "name": target["name"],
        "file": target["file"],
        "line_start": lo,
        "line_end": hi,
        "def_line": target["line"],
        "static": target["static"],
        "exported": target["exported"],
        "callers": target["callers"],
        "score": target["score"],
        "kernel_src": str(KERNEL_SRC),
        "snippet": snippet,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / f"selection-{args.date}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in data.items() if k != "snippet"}, ensure_ascii=False, indent=2))
    print(f"\n源码片段已写入 {out}")


if __name__ == "__main__":
    main()
