#!/usr/bin/env python3
"""Select a random, not-yet-analyzed core kernel function.

ANALYZED_SET is derived from the notes repo (/workspace) which stores one
directory per source file and one markdown file per analyzed symbol.
Candidate source is the pristine Linux v4.3 tree in /workspace/.kernel-src/linux.
"""
import os, re, math, random, json, datetime, sys

WS = "/workspace"
SRC = os.path.join(WS, ".kernel-src/linux")
SUBSYS_ROOTS = ["mm", "kernel/sched", "drivers", "fs", "ipc", "block", "net", "security", "lib", "kernel"]
# 用户指定的优先子系统（随机采样仅在优先级池内进行）
PRIORITY = ["mm", "kernel/sched", "drivers"]

BAD = re.compile(r"(SYSCALL_DEFINE|EXPORT_SYMBOL|^__init|^__exit|_init$|_exit$|_show$|_store$|debug|trace|sysctl|notifier|_attr|early_param|core_param|module_)")
FN_RE = re.compile(r"^(?!static\s+inline\s+void\s*$)([A-Za-z_][\w\s\*]*?)\b([A-Za-z_]\w*)\s*\(([^;{}]*?)\)\s*\{", re.S | re.M)
SKIP_NAMES = {"if", "for", "while", "switch", "return", "sizeof", "typeof", "do"}

def analyzed_set():
    names = set()
    for root, dirs, files in os.walk(WS):
        if "/.git" in root or "/.kernel-src" in root or "/daily" in root:
            continue
        for f in files:
            if f.endswith(".md") and f != "README.md":
                names.add(f[:-3])
    return names

def brace_end(text, open_idx):
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text) - 1

_COUNTS = None
def build_counts():
    global _COUNTS
    counts = {}
    token = re.compile(r"([A-Za-z_]\w*)\s*\(")
    for d in ("kernel", "mm", "fs", "include"):
        for root, _, files in os.walk(os.path.join(SRC, d)):
            for f in files:
                if not f.endswith((".c", ".h")):
                    continue
                try:
                    text = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for m in token.finditer(text):
                    n = m.group(1)
                    counts[n] = counts.get(n, 0) + 1
    _COUNTS = counts

def corpus_call_count(name):
    global _COUNTS
    if _COUNTS is None:
        build_counts()
    return _COUNTS.get(name, 0)

def candidates():
    analyzed = analyzed_set()
    cands = []
    for sub in SUBSYS_ROOTS:
        root = os.path.join(WS, sub)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            for d in dirnames:
                if not d.endswith((".c", ".h")):
                    continue
                rel_src = os.path.relpath(os.path.join(dirpath, d), WS)
                src_path = os.path.join(SRC, rel_src)
                if not os.path.isfile(src_path):
                    continue
                note_dir = os.path.join(dirpath, d)
                try:
                    text = open(src_path, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for m in FN_RE.finditer(text):
                    prefix = m.group(1) or ""
                    name = m.group(2)
                    if name in SKIP_NAMES or BAD.search(name):
                        continue
                    if name in analyzed:
                        continue
                    # only top-level-ish definitions: match must start at column 0
                    line_start = text.count("\n", 0, m.start()) + 1
                    line_text = text.splitlines()[line_start - 1]
                    if line_text[:1].isspace() or line_text.startswith("#"):
                        continue
                    static = bool(re.search(r"\bstatic\b", prefix + " " + line_text))
                    if "inline" in line_text and static:
                        continue
                    if "__init" in line_text or "__exit" in line_text:
                        continue
                    open_idx = text.find("{", m.end() - 1)
                    end_idx = brace_end(text, open_idx)
                    line_end = text.count("\n", 0, end_idx) + 1
                    body_lines = line_end - line_start
                    if body_lines < 4:
                        continue
                    cands.append({
                        "name": name, "subsystem": sub, "file": rel_src,
                        "line_start": line_start, "line_end": line_end,
                        "static": static, "body_lines": body_lines,
                    })
    return cands

def main():
    seed = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    rng = random.Random(seed)
    cands = candidates()
    # de-dup name+file
    seen = set(); uniq = []
    for c in cands:
        k = (c["name"], c["file"])
        if k not in seen:
            seen.add(k); uniq.append(c)
    # core filter + weight (核心度 = 调用点多少 + 函数体规模 + 是否全局导出)
    pool = []
    for c in uniq:
        if c["body_lines"] < 12:
            continue
        cc = corpus_call_count(c["name"])
        if cc < 4:
            continue
        if c["static"] and cc < 6:
            continue
        c["calls"] = cc
        c["weight"] = math.log1p(cc) * 2 + math.log1p(c["body_lines"]) + (0 if c["static"] else 2)
        pool.append(c)
    # 仅在用户指定的优先子系统内加权采样（mm 25 / sched 25 / drivers 15）
    prio_w = {"mm": 25, "kernel/sched": 25, "drivers": 15}
    sub_w = {}
    for c in pool:
        if c["subsystem"] in prio_w:
            sub_w[c["subsystem"]] = sub_w.get(c["subsystem"], 0) + c["weight"] * prio_w[c["subsystem"]]
    subs = list(sub_w)
    sub = rng.choices(subs, weights=[sub_w[s] for s in subs], k=1)[0]
    picks = [c for c in pool if c["subsystem"] == sub]
    chosen = rng.choices(picks, weights=[c["weight"] for c in picks], k=1)[0]
    print(json.dumps({"seed": seed, "analyzed_total": len(analyzed_set()),
                      "candidates": len(pool), "subsystem_pool": sub,
                      "chosen": chosen}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
