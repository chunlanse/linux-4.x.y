#!/usr/bin/env python3
import os, re, random, json
from collections import defaultdict

WORKSPACE = "/workspace"
KERNEL_SRC = os.path.expanduser("~/linux-stable")

# Step 1: Build ANALYZED_SET
analyzed = set()  # (subsystem, filename, func_name)
analyzed_list = []

for root, dirs, files in os.walk(WORKSPACE):
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    for f in files:
        if not f.endswith(".md"):
            continue
        rel_dir = os.path.relpath(root, WORKSPACE)
        parts = rel_dir.split(os.sep)
        if len(parts) >= 2:
            subsystem = parts[0]
            if subsystem in ["README.md", "System.map"]:
                continue
            source_file = parts[1] if len(parts) >= 2 else ""
            func_name = f.replace(".md", "")
            analyzed.add((subsystem, source_file, func_name))
            analyzed_list.append({"subsystem": subsystem, "file": source_file, "func": func_name, "path": rel_dir})

print(f"已分析函数数量: {len(analyzed_list)}")

os.makedirs("/workspace/daily", exist_ok=True)
with open("/workspace/daily/INDEX.json", "w") as fp:
    json.dump(analyzed_list, fp, indent=2, ensure_ascii=False)

# Step 2: Find candidates in kernel source
priority_subsystems = ["mm", "kernel/sched", "drivers", "fs", "kernel", "ipc", "net", "block", "security", "lib"]
weights = [25, 25, 15, 15, 5, 5, 5, 3, 2, 2]

def extract_functions_from_file(filepath):
    funcs = []
    try:
        with open(filepath, "r", errors="ignore") as fp:
            content = fp.read()
    except Exception:
        return funcs
    lines = content.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(static\s+)?(?:inline\s+)?(?:__init\s+)?(?:const\s+)?[\w\s_\*]+?\b([\w_]+)\s*\([^;]*\{?", line)
        if m:
            name = m.group(2)
            if name in ["if", "for", "while", "switch", "return", "sizeof", "offsetof", "likely", "unlikely", "NULL", "true", "false"]:
                continue
            has_export = False
            for j in range(i, min(i+5, len(lines))):
                if "EXPORT_SYMBOL" in lines[j] and name in lines[j]:
                    has_export = True
                    break
            is_core = False
            if not line.strip().startswith("static") and has_export:
                is_core = True
            if any(name.startswith(p) for p in ["do_", "sys_", "__do_", "vfs_"]):
                is_core = True
            if any(name.endswith(s) for s in ["_init", "_alloc", "_free", "_map", "_unmap"]):
                is_core = True
            if is_core:
                funcs.append((name, i+1))
    return funcs

candidates_by_subsys = defaultdict(list)

for subsys in priority_subsystems:
    subsys_path = os.path.join(KERNEL_SRC, subsys)
    if not os.path.isdir(subsys_path):
        continue
    for root, dirs, files in os.walk(subsys_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if not (f.endswith(".c") or f.endswith(".h")):
                continue
            filepath = os.path.join(root, f)
            rel_path = os.path.relpath(filepath, KERNEL_SRC)
            funcs = extract_functions_from_file(filepath)
            for name, line in funcs:
                already = False
                for a_sub, a_file, a_func in analyzed:
                    if a_sub.replace("/", "_") == subsys.replace("/", "_") and a_file == f and a_func == name:
                        already = True
                        break
                    if a_sub == subsys.split("/")[0] and a_file == f and a_func == name:
                        already = True
                        break
                if not already:
                    candidates_by_subsys[subsys].append({
                        "name": name,
                        "file": rel_path,
                        "line": line,
                        "subsystem": subsys
                    })

print("各子系统候选数量:")
for subsys in priority_subsystems:
    print(f"  {subsys}: {len(candidates_by_subsys[subsys])}")

all_candidates = []
for subsys, w in zip(priority_subsystems, weights):
    for cand in candidates_by_subsys[subsys]:
        all_candidates.append((cand, w))

if not all_candidates:
    print("ERROR: No candidates found")
else:
    total_w = sum(w for _, w in all_candidates)
    r = random.uniform(0, total_w)
    cum = 0
    selected = None
    for cand, w in all_candidates:
        cum += w
        if r <= cum:
            selected = cand
            break
    if selected is None:
        selected = all_candidates[-1][0]
    print("\n选中目标:")
    print(json.dumps(selected, indent=2, ensure_ascii=False))
    with open("/workspace/daily/TARGET.json", "w") as fp:
        json.dump(selected, fp, indent=2, ensure_ascii=False)
