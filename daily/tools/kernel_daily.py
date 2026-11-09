#!/usr/bin/env python3
"""
Linux 内核每日源码学习工作流（确定性部分）。

Agent 负责「理解与写作」，本脚本负责可复现的工程环节：
  1. 扫描 workspace 中已有笔记，构建「已分析集合」；
  2. 按子系统权重随机挑选一个未分析的核心函数；
  3. 从 GitHub 拉取对应 Linux 源码（带本地缓存）；
  4. 输出目标元数据 + 源码片段，交给 Agent 分析；
  5. 归档分析结果、维护索引/统计，并把结果推送到飞书。

子命令：
  prepare   选取今日目标并抓取源码
  finalize  归档分析结果（可选 --push 推送飞书）
  stats     查看累计进度
  doctor    环境与网络自检
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
DAILY_ROOT = WORKSPACE / "daily"
CONFIG_PATH = DAILY_ROOT / "config.json"
CACHE_ROOT = Path.home() / ".cache" / "kernel-daily"

# 每个子系统精选的核心源文件（Linux v4.9 路径）。只从这些文件里取候选，
# 避免扫描整棵内核树带来的巨大网络与时间开销。
CORE_FILES: dict[str, list[str]] = {
    "mm": [
        "mm/page_alloc.c", "mm/slab.c", "mm/slub.c", "mm/slab_common.c",
        "mm/vmscan.c", "mm/vmalloc.c", "mm/mmap.c", "mm/memory.c",
        "mm/memblock.c", "mm/swap.c", "mm/swapfile.c", "mm/page-writeback.c",
        "mm/filemap.c", "mm/truncate.c", "mm/shmem.c", "mm/huge_memory.c",
        "mm/compaction.c", "mm/migrate.c", "mm/cma.c", "mm/page_isolation.c",
        "mm/sparse.c", "mm/percpu.c", "mm/bootmem.c", "mm/nobootmem.c",
        "mm/util.c", "mm/list_lru.c", "mm/mempolicy.c", "mm/oom_kill.c",
        "mm/workingset.c", "mm/zsmalloc.c", "mm/ioremap.c", "mm/nommu.c",
        "mm/userfaultfd.c", "mm/process_vm_access.c", "mm/gup.c",
    ],
    "kernel/sched": [
        "kernel/sched/core.c", "kernel/sched/fair.c", "kernel/sched/rt.c",
        "kernel/sched/deadline.c", "kernel/sched/idle.c",
        "kernel/sched/stop_task.c", "kernel/sched/loadavg.c",
        "kernel/sched/clock.c", "kernel/sched/cputime.c",
        "kernel/sched/stats.c", "kernel/sched/wait.c",
        "kernel/sched/completion.c", "kernel/sched/swait.c",
        "kernel/sched/auto_group.c", "kernel/sched/debug.c",
    ],
    "drivers": [
        "drivers/base/core.c", "drivers/base/driver.c", "drivers/base/device.c",
        "drivers/base/platform.c", "drivers/base/bus.c",
        "drivers/base/dma-mapping.c",
        "drivers/tty/tty_io.c", "drivers/tty/n_tty.c",
        "drivers/char/mem.c", "drivers/char/random.c",
        "drivers/block/loop.c", "drivers/block/brd.c",
        "drivers/usb/core/hcd.c", "drivers/usb/core/hub.c",
        "drivers/usb/core/message.c", "drivers/usb/core/urb.c",
        "drivers/pci/probe.c", "drivers/pci/pci.c", "drivers/pci/bus.c",
        "drivers/gpio/gpiolib.c", "drivers/of/base.c", "drivers/of/irq.c",
        "drivers/mmc/core/core.c", "drivers/i2c/i2c-core.c",
        "drivers/spi/spi.c", "drivers/md/md.c",
        "drivers/net/ethernet/intel/e1000/e1000_main.c",
        "drivers/net/ethernet/intel/e1000e/netdev.c",
    ],
    "fs": [
        "fs/super.c", "fs/inode.c", "fs/dentry.c", "fs/file.c", "fs/open.c",
        "fs/read_write.c", "fs/namei.c", "fs/dcache.c", "fs/buffer.c",
        "fs/block_dev.c", "fs/namespace.c", "fs/stat.c", "fs/pipe.c",
        "fs/splice.c", "fs/eventpoll.c", "fs/timerfd.c", "fs/seq_file.c",
        "fs/xattr.c", "fs/libfs.c", "fs/fs-writeback.c", "fs/sync.c",
        "fs/utimes.c", "fs/exec.c", "fs/fcntl.c", "fs/ioctl.c", "fs/poll.c",
        "fs/select.c", "fs/d_path.c",
        "fs/ext4/super.c", "fs/ext4/inode.c", "fs/ext4/namei.c",
        "fs/ext4/file.c", "fs/ext4/extents.c", "fs/ext4/balloc.c",
        "fs/ext4/ialloc.c", "fs/ext4/mballoc.c", "fs/ext4/dir.c",
        "fs/ext4/fsync.c", "fs/ext4/xattr.c", "fs/ext4/resize.c",
    ],
    "kernel": [
        "kernel/fork.c", "kernel/exit.c", "kernel/signal.c",
        "kernel/workqueue.c", "kernel/timer.c", "kernel/time/timer.c",
        "kernel/time/timekeeping.c", "kernel/locking/mutex.c",
        "kernel/locking/spinlock.c", "kernel/locking/rwsem.c",
        "kernel/locking/rtmutex.c", "kernel/rcupdate.c", "kernel/module.c",
        "kernel/kthread.c", "kernel/printk/printk.c", "kernel/sys.c",
        "kernel/pid.c", "kernel/nsproxy.c", "kernel/async.c",
        "kernel/cred.c", "kernel/params.c", "kernel/resource.c",
        "kernel/softirq.c", "kernel/task_work.c", "kernel/groups.c",
        "kernel/user_namespace.c",
    ],
    "block": [
        "block/blk-core.c", "block/bio.c", "block/elevator.c",
        "block/blk-merge.c", "block/blk-mq.c", "block/bounce.c",
        "block/genhd.c", "block/partition-generic.c", "block/blk-timeout.c",
    ],
    "net": [
        "net/core/dev.c", "net/core/skbuff.c", "net/core/sock.c",
        "net/core/net_namespace.c", "net/core/rtnetlink.c",
        "net/ipv4/tcp.c", "net/ipv4/udp.c", "net/ipv4/route.c",
        "net/unix/af_unix.c", "net/packet/af_packet.c",
        "net/netlink/af_netlink.c",
    ],
    "ipc": [
        "ipc/msg.c", "ipc/sem.c", "ipc/shm.c", "ipc/util.c",
        "ipc/mqueue.c", "ipc/msgutil.c",
    ],
    "security": [
        "security/security.c", "security/commoncap.c",
        "security/keys/process_keys.c", "security/selinux/hooks.c",
        "security/selinux/inode.c",
    ],
    "lib": [
        "lib/string.c", "lib/kobject.c", "lib/vsprintf.c", "lib/rbtree.c",
        "lib/idr.c", "lib/bitmap.c", "lib/list_sort.c", "lib/crc32.c",
        "lib/random32.c", "lib/sort.c", "lib/devres.c", "lib/klist.c",
        "lib/kref.c", "lib/percpu_ref.c", "lib/assoc_array.c",
        "lib/bsearch.c", "lib/hweight.c", "lib/gcd.c", "lib/parser.c",
        "lib/cmdline.c", "lib/dump_stack.c",
    ],
}

NOISE_NAMES = {
    "if", "for", "while", "switch", "sizeof", "return", "do", "else",
    "__attribute__", "typeof", "asm", "defined", "main",
}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #

def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def now_cn() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:  # pragma: no cover
        return datetime.now(timezone(timedelta(hours=8)))


def makedirs(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def subsystem_of(path: str) -> str:
    if path.startswith("kernel/sched/"):
        return "kernel/sched"
    return path.split("/", 1)[0]


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name)


# --------------------------------------------------------------------------- #
# 已分析集合
# --------------------------------------------------------------------------- #

def scan_analyzed(workspace: Path = WORKSPACE) -> tuple[set[tuple[str, str]], set[str]]:
    """扫描现有笔记，返回 ({(源文件, 函数)}, {函数名})。

    兼容两种布局：
      - 子系统就地笔记：mm/page_alloc.c/__alloc_pages.md
      - 每日归档：daily/YYYY/MM/YYYY-MM-DD/mm__func.md
    """
    pairs: set[tuple[str, str]] = set()
    names: set[str] = set()

    for md in workspace.rglob("*.md"):
        rel = md.relative_to(workspace)
        parts = rel.parts
        if any(p in {".git", "node_modules"} for p in parts):
            continue
        if md.name == "README.md":
            continue

        # 布局 A：<subsystem>/<source.c|h>/<func>.md
        if len(parts) >= 3 and parts[-2].endswith((".c", ".h")):
            src = "/".join(parts[:-1])
            func = md.stem
            pairs.add((src, func))
            names.add(func)
            continue

        # 布局 B：daily/.../<subsystem>__<func>.md
        if parts[0] == "daily" and "__" in md.stem and len(parts) >= 5:
            func = md.stem.split("__", 1)[1]
            names.add(func)

    return pairs, names


# --------------------------------------------------------------------------- #
# 源码获取与函数抽取
# --------------------------------------------------------------------------- #

def fetch_source(path: str, cfg: dict[str, Any], refresh: bool = False) -> str:
    kernel = cfg["kernel"]
    local_src = kernel.get("local_src") or ""
    if local_src:
        local_file = Path(local_src) / path
        if local_file.is_file():
            return local_file.read_text(encoding="utf-8", errors="replace")

    tag = safe_name(kernel["tag"])
    cache = CACHE_ROOT / tag / path
    if cache.is_file() and cache.stat().st_size > 0 and not refresh:
        return cache.read_text(encoding="utf-8", errors="replace")

    url = kernel["raw_url"].format(repo=kernel["repo"], tag=kernel["tag"], path=path)
    req = urllib.request.Request(url, headers={"User-Agent": "linux-kernel-daily/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise RuntimeError(f"下载源码失败 {url}: {exc}") from exc

    makedirs(cache.parent)
    cache.write_text(text, encoding="utf-8")
    return text


def blank_comments_and_strings(src: str) -> str:
    """把注释/字符串替换为空格（保持长度与换行），便于做括号匹配。"""
    out = list(src)
    i, n, state = 0, len(src), None
    while i < n:
        c = src[i]
        if state is None:
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                state = "line"
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                state = "block"
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if c == '"':
                state = "str"
                out[i] = " "
                i += 1
                continue
            if c == "'":
                state = "chr"
                out[i] = " "
                i += 1
                continue
        elif state == "line":
            if c == "\n":
                state = None
            else:
                out[i] = " "
            i += 1
            continue
        elif state == "block":
            out[i] = " "
            if c == "*" and i + 1 < n and src[i + 1] == "/":
                out[i + 1] = " "
                i += 2
                state = None
                continue
            i += 1
            continue
        elif state in ("str", "chr"):
            if c == "\\":
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
                continue
            if (state == "str" and c == '"') or (state == "chr" and c == "'"):
                out[i] = " "
                state = None
                i += 1
                continue
            if c == "\n":
                state = None
            out[i] = " "
            i += 1
            continue
        i += 1
    return "".join(out)


def match_brace(clean: str, open_idx: int) -> int | None:
    depth = 0
    for k in range(open_idx, len(clean)):
        if clean[k] == "{":
            depth += 1
        elif clean[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return None


def parse_signature(clean: str, close_paren: int) -> tuple[str, int, bool] | None:
    """从 `{` 前的 `)` 反推函数名、声明起点、是否 static。"""
    depth = 0
    k = close_paren
    open_paren = None
    while k >= 0:
        if clean[k] == ")":
            depth += 1
        elif clean[k] == "(":
            depth -= 1
            if depth == 0:
                open_paren = k
                break
        k -= 1
    if open_paren is None:
        return None

    j = open_paren - 1
    while j >= 0 and clean[j].isspace():
        j -= 1
    name_end = j + 1
    while j >= 0 and (clean[j].isalnum() or clean[j] == "_"):
        j -= 1
    name = clean[j + 1:name_end]
    if not name or not re.match(r"^[A-Za-z_]\w*$", name):
        return None

    decl_start = j + 1
    while decl_start > 0:
        ch = clean[decl_start - 1]
        if ch in ";}{":
            break
        if ch == "#" and (decl_start - 1 == 0 or clean[decl_start - 2] == "\n"):
            break
        decl_start -= 1

    # 跳过前导空行与被清空的注释区，定位到真正的声明起始 token
    while decl_start < open_paren and clean[decl_start].isspace():
        decl_start += 1

    sig = clean[decl_start:open_paren]
    if re.search(r"[=]\s*$", sig) or "_HOOK" in sig:
        return None
    return name, decl_start, bool(re.search(r"\bstatic\b", sig))


def extract_functions(src: str) -> list[dict[str, Any]]:
    clean = blank_comments_and_strings(src)
    funcs: list[dict[str, Any]] = []
    depth = 0
    i, n = 0, len(clean)
    exported = set(re.findall(r"EXPORT_SYMBOL(?:_GPL)?\s*\(\s*(\w+)\s*\)", clean))

    while i < n:
        c = clean[i]
        if c == "{":
            if depth == 0:
                j = i - 1
                while j >= 0 and clean[j].isspace():
                    j -= 1
                if j >= 0 and clean[j] == ")":
                    parsed = parse_signature(clean, j)
                    if parsed:
                        name, decl_start, is_static = parsed
                        end = match_brace(clean, i)
                        if end is not None:
                            start_line = src.count("\n", 0, decl_start) + 1
                            end_line = src.count("\n", 0, end) + 1
                            funcs.append({
                                "name": name,
                                "line_start": start_line,
                                "line_end": end_line,
                                "static": is_static,
                                "exported": name in exported,
                            })
                            i = end + 1
                            continue
                depth = 1
            else:
                depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        i += 1
    return funcs


def is_core_function(fn: dict[str, Any]) -> bool:
    name = fn["name"]
    if name in NOISE_NAMES or len(name) < 3:
        return False
    if re.match(r"^[A-Z0-9_]+$", name):
        return False
    if fn["line_end"] - fn["line_start"] < 2:
        return False
    if fn["exported"] or not fn["static"]:
        return True
    if re.match(r"^(__?do_|do_|sys_|vfs_|__?k?sys_)", name):
        return True
    if re.search(r"(_alloc|_free|_map|_unmap|_init|_exit)$", name):
        return True
    return False


def build_subsystem_catalog(subsystem: str, cfg: dict[str, Any],
                            refresh: bool = False) -> dict[str, Any]:
    tag = safe_name(cfg["kernel"]["tag"])
    cache = CACHE_ROOT / tag / "catalog" / f"{safe_name(subsystem)}.json"
    if cache.is_file() and not refresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    files: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    for path in CORE_FILES[subsystem]:
        try:
            src = fetch_source(path, cfg, refresh=refresh)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        allowed = [
            fn for fn in extract_functions(src)
            if is_core_function(fn) and not fn["name"].startswith("__builtin")
        ]
        if allowed:
            files[path] = allowed

    catalog = {
        "subsystem": subsystem,
        "tag": cfg["kernel"]["tag"],
        "generated_at": now_cn().isoformat(timespec="seconds"),
        "files": files,
        "errors": errors,
    }
    makedirs(cache.parent)
    cache.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog


# --------------------------------------------------------------------------- #
# 选取目标
# --------------------------------------------------------------------------- #

def choose_target(cfg: dict[str, Any], seed: int | None = None,
                  refresh: bool = False) -> dict[str, Any]:
    pairs, names = scan_analyzed()
    rng = random.Random(seed) if seed is not None else random.Random()
    weights: dict[str, float] = dict(cfg["priority_subsystems"])

    # 按权重无放回地尝试子系统，避免选中「已全部分析」的子系统后卡死
    remaining = [s for s in weights if s in CORE_FILES]
    for _ in range(len(remaining)):
        total_w = sum(weights[s] for s in remaining)
        if total_w <= 0:
            break
        pick = rng.choices(remaining, weights=[weights[s] for s in remaining], k=1)[0]
        remaining.remove(pick)

        try:
            catalog = build_subsystem_catalog(pick, cfg, refresh=refresh)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 构建 {pick} 候选失败：{exc}", file=sys.stderr)
            continue

        candidates: list[tuple[str, dict[str, Any]]] = []
        for path, fns in catalog["files"].items():
            for fn in fns:
                if (path, fn["name"]) in pairs or fn["name"] in names:
                    continue
                candidates.append((path, fn))

        if not candidates:
            print(f"[info] {pick} 已无可分析候选，降级到下一子系统", file=sys.stderr)
            continue

        path, fn = rng.choice(candidates)
        return {
            "date": now_cn().strftime("%Y-%m-%d"),
            "target": {
                "name": fn["name"],
                "file": path,
                "line_start": fn["line_start"],
                "line_end": fn["line_end"],
                "subsystem": subsystem_of(path),
                "type": "function",
                "static": fn["static"],
                "exported": fn["exported"],
            },
            "kernel": {
                "repo": cfg["kernel"]["repo"],
                "tag": cfg["kernel"]["tag"],
                "url": cfg["kernel"]["raw_url"].format(
                    repo=cfg["kernel"]["repo"], tag=cfg["kernel"]["tag"], path=path),
            },
            "selection": {
                "candidates_in_subsystem": len(candidates),
                "analyzed_pairs": len(pairs),
            },
        }

    raise RuntimeError("所有优先子系统都没有未分析候选，请检查 CORE_FILES 或扩大候选池")


def cmd_prepare(args: argparse.Namespace) -> int:
    cfg = load_config()

    if args.target:
        path = args.file
        if not path:
            raise SystemExit("--target 必须与 --file 一起使用，例如 --target do_fork --file kernel/fork.c")
        pairs, names = scan_analyzed()
        if (path, args.target) in pairs or args.target in names:
            raise SystemExit(f"{args.target} 已分析过，请换一个目标")
        src = fetch_source(path, cfg, refresh=args.refresh)
        fns = [f for f in extract_functions(src) if f["name"] == args.target]
        if not fns:
            raise SystemExit(f"在 {path} 中未找到函数 {args.target}")
        fn = fns[0]
        result = {
            "date": now_cn().strftime("%Y-%m-%d"),
            "target": {
                "name": fn["name"], "file": path,
                "line_start": fn["line_start"], "line_end": fn["line_end"],
                "subsystem": subsystem_of(path), "type": "function",
                "static": fn["static"], "exported": fn["exported"],
            },
            "kernel": {
                "repo": cfg["kernel"]["repo"], "tag": cfg["kernel"]["tag"],
                "url": cfg["kernel"]["raw_url"].format(
                    repo=cfg["kernel"]["repo"], tag=cfg["kernel"]["tag"], path=path),
            },
            "selection": {"candidates_in_subsystem": 1, "analyzed_pairs": len(pairs)},
        }
    else:
        result = choose_target(cfg, seed=args.seed, refresh=args.refresh)

    target = result["target"]
    src = fetch_source(target["file"], cfg, refresh=args.refresh)
    lines = src.splitlines()
    lo = max(0, target["line_start"] - 1 - args.context)
    hi = min(len(lines), target["line_end"] + args.context)
    result["source_excerpt"] = "\n".join(lines[lo:hi])
    result["excerpt_range"] = [lo + 1, hi]

    out = Path(args.out) if args.out else CACHE_ROOT / "state" / f"target-{result['date']}.json"
    makedirs(out.parent)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "date": result["date"],
        "target": target,
        "source_url": result["kernel"]["url"],
        "target_json": str(out),
        "excerpt_range": result["excerpt_range"],
    }, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# 归档与索引
# --------------------------------------------------------------------------- #

def extract_summary(analysis: str, limit: int = 140) -> str:
    match = re.search(r"##\s*1\.\s*功能作用\s*\n+(.+?)(?:\n##|\Z)", analysis, re.S)
    text = (match.group(1) if match else analysis).strip()
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"[`*|]", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def validate_analysis(analysis: str) -> list[str]:
    required = ["## 1. 功能作用", "## 2. 关键数据结构",
                "## 3. 核心逻辑流程图", "## 4. 调用关系"]
    return [sec for sec in required if sec not in analysis]


def write_inplace_note(target: dict[str, Any], analysis: str) -> Path | None:
    """按本仓库的笔记布局写入 <源文件路径>/<函数>.md。"""
    src_path = WORKSPACE / target["file"]
    top = WORKSPACE / target["subsystem"].split("/", 1)[0]
    if src_path.is_dir():
        dest = src_path / f"{target['name']}.md"
    elif top.is_dir():
        dest = src_path / f"{target['name']}.md"
    else:
        return None
    makedirs(dest.parent)
    dest.write_text(analysis, encoding="utf-8")
    return dest


def rebuild_indexes(cfg: dict[str, Any]) -> dict[str, Any]:
    index_file = DAILY_ROOT / "index.json"
    if index_file.is_file():
        index = json.loads(index_file.read_text(encoding="utf-8"))
    else:
        index = {"entries": []}
    entries = index.setdefault("entries", [])
    entries.sort(key=lambda e: (e["date"], e["name"]), reverse=True)

    lines = [
        "# Linux 内核每日源码分析索引",
        "",
        "> 由 `daily/tools/kernel_daily.py` 自动维护，按日期倒序。",
        "",
        "| 日期 | 子系统 | 函数 | 源文件:行号 | 摘要 | 飞书 |",
        "|------|--------|------|-------------|------|------|",
    ]
    for e in entries:
        link = f"[{e['name']}]({e['archive']})"
        summary = (e.get("summary") or "").replace("|", "\\|")
        doc = f"[文档]({e['doc_url']})" if e.get("doc_url") else "-"
        lines.append(
            f"| {e['date']} | {e['subsystem']} | {link} | "
            f"`{e['file']}:{e['line_start']}-{e['line_end']}` | {summary} | {doc} |"
        )
    (DAILY_ROOT / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        grouped.setdefault(e["subsystem"], []).append(e)
    by_lines = ["# 按子系统索引", ""]
    for subsystem in sorted(grouped):
        by_lines.append(f"## {subsystem}")
        by_lines.append("")
        for e in grouped[subsystem]:
            by_lines.append(
                f"- {e['date']} — [{e['name']}]({e['archive']}) "
                f"(`{e['file']}:{e['line_start']}-{e['line_end']}`)"
            )
        by_lines.append("")
    (DAILY_ROOT / "by-subsystem.md").write_text("\n".join(by_lines), encoding="utf-8")

    stats = {
        "generated_at": now_cn().isoformat(timespec="seconds"),
        "total": len(entries),
        "subsystems": {k: len(v) for k, v in sorted(grouped.items())},
        "last_entry": entries[0] if entries else None,
    }
    (DAILY_ROOT / "progress-stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    index["entries"] = entries
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def run_lark(args: list[str], cwd: Path | None = None) -> dict[str, Any]:
    proc = subprocess.run(
        ["lark-cli", *args], cwd=str(cwd or WORKSPACE),
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"lark-cli 失败 ({proc.returncode}): {proc.stderr.strip()[:500]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"lark-cli 输出非 JSON: {proc.stdout[:300]}") from exc


def find_url(obj: Any) -> str | None:
    if isinstance(obj, dict):
        for k in ("url", "doc_url", "document_url", "link"):
            if isinstance(obj.get(k), str) and obj[k].startswith("http"):
                return obj[k]
        for v in obj.values():
            found = find_url(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_url(v)
            if found:
                return found
    return None


def push_feishu(cfg: dict[str, Any], target: dict[str, Any], analysis_path: Path,
                summary: str, analysis: str) -> dict[str, Any]:
    feishu = cfg.get("feishu") or {}
    chat_id = feishu.get("chat_id")

    title = f"内核源码每日分析 {target['date']} · {target['name']}"
    doc_url = None
    if feishu.get("create_doc", True):
        args = [
            "docs", "+create",
            "--title", title,
            "--doc-format", "markdown",
            "--content", f"@{analysis_path.name}",
        ]
        if feishu.get("parent_position"):
            args += ["--parent-position", feishu["parent_position"]]
        out = run_lark(args, cwd=analysis_path.parent)
        if not out.get("ok", True):
            raise RuntimeError(f"创建飞书文档失败：{out.get('error')}")
        doc_url = find_url(out)

    message_error = None
    if feishu.get("send_im_message", False) and chat_id:
        message = [
            f"**{title}**",
            "",
            f"**位置**：`{target['file']}:{target['line_start']}-{target['line_end']}`"
            f"（{target['subsystem']}）",
            "",
            f"**功能**：{summary}",
            "",
        ]
        if doc_url:
            message.append(f"[查看完整分析（飞书文档）]({doc_url})")
        else:
            message.append("```markdown")
            message.append(analysis[:12000])
            message.append("```")
        try:
            run_lark([
                "im", "+messages-send",
                "--chat-id", chat_id,
                "--markdown", "\n".join(message),
            ])
        except RuntimeError as exc:
            message_error = str(exc)

    return {
        "ok": bool(doc_url) or message_error is None,
        "doc_url": doc_url,
        "chat_id": chat_id,
        "message_error": message_error,
    }


def cmd_finalize(args: argparse.Namespace) -> int:
    cfg = load_config()
    target_doc = json.loads(Path(args.target_json).read_text(encoding="utf-8"))
    target = target_doc["target"]
    analysis_path = Path(args.analysis)
    analysis = analysis_path.read_text(encoding="utf-8")

    missing = validate_analysis(analysis)
    if missing:
        print(f"[warn] 分析缺少章节：{', '.join(missing)}", file=sys.stderr)

    date = target_doc["date"]
    y, m, d = date.split("-")
    archive_dir = DAILY_ROOT / y / m / date
    makedirs(archive_dir)
    archive_name = f"{safe_name(target['subsystem'])}__{target['name']}.md"
    archive = archive_dir / archive_name
    archive.write_text(analysis, encoding="utf-8")

    inplace = None if args.no_inplace else write_inplace_note(target, analysis)

    summary = args.summary or extract_summary(analysis)
    rel_archive = archive.relative_to(DAILY_ROOT).as_posix()

    index_file = DAILY_ROOT / "index.json"
    index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.is_file() \
        else {"entries": []}
    entries = [e for e in index.get("entries", [])
               if not (e["date"] == date and e["name"] == target["name"])]
    push_result = None
    if args.push:
        push_result = push_feishu(cfg, {"date": date, **target}, archive, summary, analysis)

    doc_url = args.feishu_doc or (push_result or {}).get("doc_url")
    entries.append({
        "date": date,
        "subsystem": target["subsystem"],
        "name": target["name"],
        "file": target["file"],
        "line_start": target["line_start"],
        "line_end": target["line_end"],
        "type": target.get("type", "function"),
        "summary": summary,
        "archive": rel_archive,
        "doc_url": doc_url,
    })
    index["entries"] = entries
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    stats = rebuild_indexes(cfg)

    if push_result:
        state = CACHE_ROOT / "state" / f"push-{date}-{safe_name(target['name'])}.json"
        makedirs(state.parent)
        state.write_text(json.dumps(push_result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "archive": str(archive),
        "inplace": str(inplace) if inplace else None,
        "index": str(DAILY_ROOT / "INDEX.md"),
        "stats": stats,
        "feishu": push_result,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    stats_file = DAILY_ROOT / "progress-stats.json"
    if not stats_file.is_file():
        print(json.dumps({"ok": True, "total": 0, "subsystems": {}}, ensure_ascii=False, indent=2))
        return 0
    print(stats_file.read_text(encoding="utf-8"))
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    cfg = load_config()
    checks: list[dict[str, Any]] = []

    pairs, names = scan_analyzed()
    checks.append({"name": "analyzed_index", "ok": True,
                   "message": f"{len(pairs)} 个(文件,函数) / {len(names)} 个函数名"})

    try:
        src = fetch_source(CORE_FILES["mm"][0], cfg)
        checks.append({"name": "github_source", "ok": True,
                       "message": f"{CORE_FILES['mm'][0]} {len(src)} bytes"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "github_source", "ok": False, "message": str(exc)})

    try:
        out = run_lark(["contact", "+get-user"])
        name = (out.get("data") or {}).get("user", {}).get("name")
        checks.append({"name": "feishu_identity", "ok": bool(out.get("ok")),
                       "message": name or "unknown"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "feishu_identity", "ok": False, "message": str(exc)})

    ok = all(c["ok"] for c in checks)
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description="Linux 内核每日源码学习工作流")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", help="随机选取未分析目标并抓取源码")
    p.add_argument("--seed", type=int, help="固定随机种子，便于复现")
    p.add_argument("--refresh", action="store_true", help="忽略缓存重新抓取")
    p.add_argument("--target", help="指定函数名（需配合 --file）")
    p.add_argument("--file", help="指定源文件路径，如 kernel/fork.c")
    p.add_argument("--context", type=int, default=20, help="源码片段前后上下文行数")
    p.add_argument("--out", help="目标 JSON 输出路径")
    p.set_defaults(func=cmd_prepare)

    f = sub.add_parser("finalize", help="归档分析并更新索引")
    f.add_argument("--target-json", required=True)
    f.add_argument("--analysis", required=True)
    f.add_argument("--summary", help="覆盖自动提取的一句话摘要")
    f.add_argument("--feishu-doc", help="已有飞书文档 URL（不重复创建文档）")
    f.add_argument("--push", action="store_true", help="推送到飞书")
    f.add_argument("--no-inplace", action="store_true", help="不写子系统就地笔记")
    f.set_defaults(func=cmd_finalize)

    s = sub.add_parser("stats", help="查看累计进度")
    s.set_defaults(func=cmd_stats)

    d = sub.add_parser("doctor", help="环境与网络自检")
    d.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
