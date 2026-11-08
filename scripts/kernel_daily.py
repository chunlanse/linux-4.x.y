#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Linux 内核每日学习工作流的确定性部分。

子命令:
  prepare   构建已学习索引 -> 加权随机选题 -> 输出 TARGET
  archive   归档笔记(日期目录 + 子系统就地目录 + 索引/进度统计)
  push      将笔记导入飞书文档并向飞书推送摘要

分析(LLM 部分)由 Agent 按 TARGET 完成, 本脚本只处理可自动化的环节。
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, ".kernel-daily", "config.json")
STATE_DIR = os.path.join(ROOT, ".kernel-daily", "state")
TARGET_PATH = os.path.join(STATE_DIR, "target.json")

KEYWORDS = {
    "if", "for", "while", "switch", "return", "sizeof", "else", "do", "case",
    "default", "goto", "break", "continue", "typeof", "__attribute__",
    "inline", "asm", "volatile", "struct", "union", "enum", "typedef",
}
PREFIXES = ("do_", "__do_", "sys_", "vfs_", "__")
SUFFIXES = ("_init", "_alloc", "_free", "_map", "_unmap")

DEF_START = re.compile(r"^([A-Za-z_][A-Za-z0-9_\s\*]*?)\b([A-Za-z_]\w*)\s*\(")
EXPORT_RE = re.compile(r"EXPORT_SYMBOL(?:_GPL)?\s*\(\s*(\w+)\s*\)")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("subsystems", [])
    return cfg


def rel(path, base):
    return os.path.relpath(path, base).replace(os.sep, "/")


def build_analyzed(notes_root, archive_root, subsystems=()):
    """返回已分析函数名集合与按子系统计数。"""
    names = set()
    counts = Counter()
    prefixes = sorted((s.replace("/", "_") + "_" for s in subsystems), key=len, reverse=True)
    note_re = re.compile(r"^(.*?)/([^/]+\.(?:c|h|S))/([^/]+)\.md$")
    for dirpath, dirnames, filenames in os.walk(notes_root):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".kernel-daily")]
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            p = rel(os.path.join(dirpath, fn), notes_root)
            m = note_re.match(p)
            if not m:
                continue
            name = m.group(3)
            if name.lower() in ("readme", "index"):
                continue
            names.add(name)
            counts[m.group(1).split("/")[0]] += 1
    if os.path.isdir(archive_root):
        for dirpath, _, filenames in os.walk(archive_root):
            for fn in filenames:
                if not fn.endswith(".md") or fn in ("INDEX.md", "by-subsystem.md"):
                    continue
                base = fn[:-3]
                for pref in prefixes:
                    if base.startswith(pref):
                        names.add(base[len(pref):])
                        break
    return names, counts


def parse_functions(path, src_root):
    """解析 C 文件中的函数定义: 返回 [{name,start,end,static,body_lines}]"""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    exports = set(EXPORT_RE.findall("".join(lines)))
    funcs, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if (not line.strip() or line[0] in " \t#}" or line.lstrip().startswith(("/*", "*", "//"))):
            i += 1
            continue
        if "(" not in line:
            i += 1
            continue
        # 收集函数签名(跨行), 直到 '{' 或 ';'
        sig, j, kind = line, i, None
        while j < n and j < i + 12:
            if ";" in sig and "{" not in sig:
                kind = "decl"
                break
            if "{" in sig:
                kind = "def"
                break
            j += 1
            if j < n:
                sig += " " + lines[j].strip()
        if kind != "def":
            i += 1
            continue
        head = sig.split("{")[0]
        m = DEF_START.match(line)
        name = m.group(2) if m else None
        if not name:
            cand = re.findall(r"([A-Za-z_]\w*)\s*\(", head)
            name = cand[0] if cand else None
        if not name or name in KEYWORDS or "=" in head or "->" in head:
            i = j + 1
            continue
        # 花括号配对求函数体结束行
        depth, end = 0, None
        for k in range(j, n):
            depth += lines[k].count("{") - lines[k].count("}")
            if depth <= 0:
                end = k
                break
        if end is None or end <= j:
            i = j + 1
            continue
        funcs.append({
            "name": name,
            "start": i + 1,
            "end": end + 1,
            "static": line.lstrip().startswith("static"),
            "exported": name in exports,
            "body_lines": end - j,
        })
        i = end + 1
    return funcs


def score(f):
    s = 1
    if not f["static"]:
        s += 3
    if f["exported"]:
        s += 4
    if f["name"].startswith(PREFIXES):
        s += 2
    if f["name"].endswith(SUFFIXES):
        s += 2
    if f["body_lines"] >= 20:
        s += 2
    if f["body_lines"] >= 60:
        s += 2
    return s


def iter_c_files(subsystem, src_root):
    base = os.path.join(src_root, subsystem)
    for dirpath, dirnames, filenames in os.walk(base):
        if subsystem == "kernel":
            dirnames[:] = [d for d in dirnames if d != "sched"]
        for fn in filenames:
            if fn.endswith(".c"):
                yield os.path.join(dirpath, fn)


def prepare(args):
    cfg = load_config()
    src_root = cfg["kernel_src"]
    if not os.path.isdir(src_root):
        sys.exit(f"内核源码不存在: {src_root} (请先执行稀疏克隆)")
    analyzed, counts = build_analyzed(
        cfg["notes_root"], cfg["archive_root"], [s["path"] for s in cfg["subsystems"]])
    rng = random.Random(args.seed)

    pools, coverage = {}, {}
    for sub in cfg["subsystems"]:
        path = sub["path"]
        if not os.path.isdir(os.path.join(src_root, path)):
            continue
        funcs, total = [], 0
        for cfile in iter_c_files(path, src_root):
            try:
                parsed = parse_functions(cfile, src_root)
            except OSError:
                continue
            total += len(parsed)
            for f in parsed:
                sc = score(f)
                if f["name"] in analyzed or sc < 6:
                    continue
                funcs.append((sc, cfile, f))
        if funcs:
            pools[path] = funcs
            coverage[path] = {
                "total": total,
                "analyzed": counts.get(path.split("/")[0], 0),
                "candidates": len(funcs),
            }

    if not pools:
        sys.exit("所有优先子系统的核心候选均已分析完毕, 请扩展子系统范围或降低评分阈值")

    # 覆盖率 > 70% 的子系统降权
    weights = {}
    for sub in cfg["subsystems"]:
        if sub["path"] in pools:
            cov = coverage[sub["path"]]["analyzed"] / max(coverage[sub["path"]]["total"], 1)
            w = sub["weight"] * (0.2 if cov > 0.7 else 1.0)
            weights[sub["path"]] = w
    subsystem = rng.choices(list(weights), weights=list(weights.values()))[0]

    pool = pools[subsystem]
    top = max(sc for sc, _, _ in pool)
    best = [x for x in pool if x[0] >= top - 1]           # 在最高分附近随机
    sc, cfile, f = rng.choice(best)
    relfile = rel(cfile, src_root)

    # 统计调用点数量(全树 grep, 仅对最终目标执行一次)
    try:
        out = subprocess.run(
            ["grep", "-rIl", "--include=*.c", "--include=*.h", rf"\b{f['name']}\s*(",
             src_root], capture_output=True, text=True, timeout=60)
        callers = max(len(out.stdout.splitlines()) - 1, 0)
    except Exception:
        callers = -1

    target = {
        "date": date.today().isoformat(),
        "name": f["name"],
        "file": relfile,
        "line_start": f["start"],
        "line_end": f["end"],
        "subsystem": subsystem,
        "type": "function",
        "score": sc,
        "static": f["static"],
        "exported": f["exported"],
        "body_lines": f["body_lines"],
        "caller_files": callers,
        "kernel_ref": cfg["kernel_ref"],
        "coverage": coverage,
        "analyzed_total": len(analyzed),
    }
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(TARGET_PATH, "w", encoding="utf-8") as fh:
        json.dump(target, fh, ensure_ascii=False, indent=2)
    print(json.dumps(target, ensure_ascii=False, indent=2))


def load_target():
    with open(TARGET_PATH, encoding="utf-8") as f:
        return json.load(f)


def archive(args):
    cfg = load_config()
    t = load_target()
    with open(args.file, encoding="utf-8") as f:
        content = f.read()
    d = t["date"]
    y, m, _ = d.split("-")
    date_dir = os.path.join(cfg["archive_root"], y, m, d)
    os.makedirs(date_dir, exist_ok=True)
    main_name = f"{t['subsystem'].replace('/', '_')}_{t['name']}.md"
    main_path = os.path.join(date_dir, main_name)
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 子系统就地归档: {notes}/{subsystem}/{源文件名}/{函数名}.md
    inplace_dir = os.path.join(cfg["notes_root"], t["subsystem"], os.path.basename(t["file"]))
    os.makedirs(inplace_dir, exist_ok=True)
    inplace_path = os.path.join(inplace_dir, t["name"] + ".md")
    with open(inplace_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 索引（幂等：同一天同一函数只追加一次）
    os.makedirs(cfg["archive_root"], exist_ok=True)
    index_path = os.path.join(cfg["archive_root"], "INDEX.md")
    entry = (f"| {d} | {t['subsystem']} | `{t['name']}` | "
             f"[{t['file']}:{t['line_start']}]({y}/{m}/{d}/{main_name}) |\n")
    if not os.path.exists(index_path):
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("# 内核每日学习索引\n\n| 日期 | 子系统 | 函数 | 位置 |\n|---|---|---|---|\n")
    with open(index_path, encoding="utf-8") as f:
        index_text = f.read()
    if f"| {d} | {t['subsystem']} | `{t['name']}` |" not in index_text:
        with open(index_path, "a", encoding="utf-8") as f:
            f.write(entry)

    by_sub_path = os.path.join(cfg["archive_root"], "by-subsystem.md")
    if not os.path.exists(by_sub_path):
        with open(by_sub_path, "w", encoding="utf-8") as f:
            f.write("# 按子系统归档\n")
    with open(by_sub_path, encoding="utf-8") as f:
        by_sub_text = f.read()
    sub_prefix = f"- `{t['subsystem']}` · `{t['name']}` · {d} ·"
    if sub_prefix not in by_sub_text:
        with open(by_sub_path, "a", encoding="utf-8") as f:
            f.write(f"{sub_prefix} [笔记]({y}/{m}/{d}/{main_name})\n")

    # 进度统计
    analyzed, counts = build_analyzed(
        cfg["notes_root"], cfg["archive_root"], [s["path"] for s in cfg["subsystems"]])
    stats_path = os.path.join(cfg["archive_root"], "progress-stats.json")
    stats = {"total": len(analyzed), "by_subsystem": dict(counts), "last_run": d}
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "main": main_path, "inplace": inplace_path, "total_analyzed": len(analyzed),
    }, ensure_ascii=False, indent=2))


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def push(args):
    cfg = load_config()
    t = load_target()
    title = f"内核每日学习 {t['date']} · {t['name']}（{t['subsystem']}）"

    # 1) 导入飞书文档
    doc = run(["lark-cli", "docs", "+create", "--title", title,
               "--doc-format", "markdown", "--content", "@" + args.file], timeout=120)
    url, token = "", ""
    try:
        data = json.loads(doc.stdout)
        doc_data = data.get("data", {})
        token = (doc_data.get("document", {}) or {}).get("document_id", "") or doc_data.get("document_id", "")
        url = (doc_data.get("document", {}) or {}).get("url", "") or doc_data.get("url", "")
    except Exception:
        pass
    if not url:
        url = f"https://feishu.cn/docx/{token}" if token else ""

    # 2) 推送摘要消息
    summary = args.summary
    if args.summary_file:
        with open(args.summary_file, encoding="utf-8") as f:
            summary = f.read()
    if url:
        summary += f"\n\n[查看完整分析文档]({url})"

    cmd = ["lark-cli", "im", "+messages-send", "--markdown", summary]
    chat_id = args.chat_id or cfg["feishu"].get("chat_id")
    if chat_id:
        cmd += ["--chat-id", chat_id]
    else:
        cmd += ["--user-id", cfg["feishu"]["user_id"]]
    msg = run(cmd, timeout=60)
    print(json.dumps({
        "doc_create_ok": doc.returncode == 0 and bool(url),
        "doc_url": url,
        "doc_raw": doc.stdout[-500:] if doc.returncode else "",
        "message_ok": msg.returncode == 0,
        "message_raw": msg.stdout[-500:],
    }, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--seed", type=int, default=None)
    p.set_defaults(func=prepare)
    a = sub.add_parser("archive")
    a.add_argument("--file", required=True)
    a.set_defaults(func=archive)
    s = sub.add_parser("push")
    s.add_argument("--file", required=True)
    s.add_argument("--summary", default="")
    s.add_argument("--summary-file")
    s.add_argument("--chat-id", default="")
    s.set_defaults(func=push)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
