#!/usr/bin/env python3
import os, re, random, json, subprocess
from collections import defaultdict

WORKSPACE = '/workspace'
KERNEL_SRC = os.path.expanduser('~/linux-stable')

# Step 1: Build ANALYZED_SET
analyzed = set()
analyzed_list = []
for root, dirs, files in os.walk(WORKSPACE):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for f in files:
        if not f.endswith('.md'):
            continue
        rel_dir = os.path.relpath(root, WORKSPACE)
        parts = rel_dir.split(os.sep)
        if len(parts) >= 2:
            subsystem = parts[0]
            if subsystem in ['README.md', 'System.map']:
                continue
            source_file = parts[1]
            func_name = f.replace('.md', '')
            analyzed.add((subsystem, source_file, func_name))
            analyzed_list.append({'subsystem': subsystem, 'file': source_file, 'func': func_name})

print(f'已分析函数数量: {len(analyzed_list)}')

os.makedirs('/workspace/daily', exist_ok=True)
with open('/workspace/daily/INDEX.json', 'w') as fp:
    json.dump(analyzed_list, fp, indent=2, ensure_ascii=False)

# Step 2: Weighted subsystem selection
priority_subsystems = ['mm', 'kernel/sched', 'drivers', 'fs', 'kernel', 'ipc', 'net', 'block', 'security', 'lib']
weights = [25, 25, 15, 15, 5, 5, 5, 3, 2, 2]

def get_functions_ctags(filepath):
    funcs = []
    try:
        result = subprocess.run(['ctags', '-x', '--c-kinds=f', filepath], capture_output=True, text=True, timeout=10)
        for line in result.stdout.split('\n'):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                try:
                    line_no = int(parts[2])
                except ValueError:
                    continue
                funcs.append((name, line_no))
    except Exception:
        pass
    return funcs

def is_analyzed(subsys, filename, func_name):
    for a_sub, a_file, a_func in analyzed:
        if a_sub.replace('/', '_') == subsys.replace('/', '_') and a_file == filename and a_func == func_name:
            return True
        if a_sub == subsys.split('/')[0] and a_file == filename and a_func == func_name:
            return True
    return False

# Shuffle subsystems by weight
subsys_order = random.choices(priority_subsystems, weights=weights, k=len(priority_subsystems))
# Deduplicate while preserving order
seen = set()
ordered = []
for s in subsys_order:
    if s not in seen:
        seen.add(s)
        ordered.append(s)

selected = None
for subsys in ordered:
    subsys_path = os.path.join(KERNEL_SRC, subsys)
    if not os.path.isdir(subsys_path):
        continue
    # Collect all .c files
    c_files = []
    for root, dirs, files in os.walk(subsys_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith('.c'):
                c_files.append(os.path.join(root, f))
    if not c_files:
        continue
    # Randomly sample up to 100 files for efficiency
    sample_size = min(100, len(c_files))
    sampled = random.sample(c_files, sample_size)
    candidates = []
    for filepath in sampled:
        rel_path = os.path.relpath(filepath, KERNEL_SRC)
        filename = os.path.basename(filepath)
        funcs = get_functions_ctags(filepath)
        for name, line in funcs:
            if not is_analyzed(subsys, filename, name):
                candidates.append({'name': name, 'file': rel_path, 'line': line, 'subsystem': subsys})
    print(f'  {subsys}: scanned {sample_size} files, found {len(candidates)} candidates')
    if candidates:
        selected = random.choice(candidates)
        break

if selected is None:
    print('ERROR: No unanalyzed candidate found')
else:
    print('\n选中目标:')
    print(json.dumps(selected, indent=2, ensure_ascii=False))
    with open('/workspace/daily/TARGET.json', 'w') as fp:
        json.dump(selected, fp, indent=2, ensure_ascii=False)
