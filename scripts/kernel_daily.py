#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kernel_daily.py - Linux 内核每日源码学习核心引擎（可被 cron 独立调用）

职责：
  1. 构建 ANALYZED_SET，避免重复分析
  2. 按子系统加权权重 + 核心函数判定标准 随机选取目标
  3. 从 GitHub novelinux/linux-4.x.y 按需抓取源码并定位定义
  4. 生成六大章节的中文深度分析 Markdown（启发式 + 源码注释语义提取）
  5. 双写归档（日期归档 + 子系统就地归档）并更新 INDEX / by-subsystem / progress-stats
  6. 调用 lark-cli 创建飞书云文档或发送 IM 摘要
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# ============================================================
# 0. 工具函数 / 全局初始化
# ============================================================
WORKSPACE_ROOT = Path("/workspace")
DEFAULT_CONFIG_PATH = Path("/workspace/scripts/.kernel-daily-config.json")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _setup_logger(log_path: Path) -> logging.Logger:
    _ensure_dir(log_path.parent)
    logger = logging.getLogger("kernel_daily")
    logger.setLevel(logging.DEBUG)
    # 每次重新配置以防重复 handler
    for h in list(logger.handlers):
        logger.removeHandler(h)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(sh)
    return logger


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def today_str(override: str | None = None) -> str:
    if override:
        # 校验格式
        try:
            _dt.date.fromisoformat(override)
            return override
        except Exception:
            pass
    env_override = os.environ.get("KERNEL_DAILY_DATE_OVERRIDE")
    if env_override:
        try:
            _dt.date.fromisoformat(env_override)
            return env_override
        except Exception:
            pass
    return _dt.date.today().isoformat()


# ============================================================
# 1. 构建已学习索引 ANALYZED_SET
# ============================================================
def _matches_exclude(rel: str, exclude_globs: list[str]) -> bool:
    for g in exclude_globs:
        if fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g + "/*"):
            return True
    return False


def _scan_readme_for_funcs(readme_path: Path) -> set[tuple[str, str]]:
    """扫描 README 表格中的函数名列。"""
    result: set[tuple[str, str]] = set()
    try:
        text = readme_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return result
    srcfile_ctx = readme_path.parent.name  # e.g. page_alloc.c
    subsys_ctx = readme_path.parent.parent.name  # e.g. mm
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cols:
            continue
        first = cols[0]
        if first in {"函数名", "名称", "Name", "Function", "-", "---"} or set(first) == {"-"}:
            continue
        # 只取类似标识符的列
        m = re.match(r"^[_a-zA-Z][_a-zA-Z0-9]*$", first)
        if m:
            result.add((first, f"{subsys_ctx}/{srcfile_ctx}"))
    return result


def build_analyzed_set(cfg: dict, logger: logging.Logger) -> set[tuple[str, str]]:
    """返回 set[(func_name, subsys/srcfile)] — 已分析过的条目键集合。"""
    ws = Path(cfg["workspace_root"])
    exclude = cfg.get("analyze_exclude_globs", [])
    result: set[tuple[str, str]] = set()
    readme_extra: set[tuple[str, str]] = set()

    for md in ws.rglob("*.md"):
        try:
            rel = str(md.relative_to(ws))
        except ValueError:
            continue
        if _matches_exclude(rel, exclude):
            continue
        parts = md.relative_to(ws).parts
        # 模式 A: {subsys}/{srcfile}/{name}.md — 三层且后缀 .md
        if len(parts) == 3 and md.suffix == ".md":
            subsys, srcfile, namemd = parts
            name = md.stem
            if "." in srcfile and (srcfile.endswith(".c") or srcfile.endswith(".h")):
                key = (name, f"{subsys}/{srcfile}")
                result.add(key)
                continue
        # 模式 B: README.md 函数索引
        if md.name == "README.md" and len(parts) == 3:
            readme_extra |= _scan_readme_for_funcs(md)

    result |= readme_extra
    logger.info(f"已分析函数集构建完成，共 {len(result)} 条（README 补充 {len(readme_extra)} 条）")
    return result


# ============================================================
# 2. GitHub 源码抓取 / 定位 / 片段
# ============================================================
def _http_get(url: str, cfg: dict, logger: logging.Logger) -> str:
    retries = int(cfg["kernel_repo"].get("fetch_retries", 3))
    backoff = float(cfg["kernel_repo"].get("fetch_retry_backoff_sec", 2.0))
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "kernel-daily-study/1.0", "Accept": "application/vnd.github.v3+json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            # Detect encoding
            text = data.decode("utf-8", errors="replace")
            return text
        except Exception as exc:  # pragma: no cover - network dependent
            last_exc = exc
            logger.warning(f"抓取失败 (尝试 {attempt}/{retries}) {url}: {exc}")
            time.sleep(backoff * attempt)
    raise RuntimeError(f"抓取 {url} 失败：{last_exc}")


def _ksrc_raw_base(cfg: dict) -> str:
    """获取实际内核源码 raw base（优先 kernel_source，否则退回到 kernel_repo）。"""
    return (cfg.get("kernel_source", {})
            .get("raw_base")
            or cfg["kernel_repo"]["raw_base"]).rstrip("/")


def _ksrc_retries(cfg: dict) -> tuple[int, float]:
    src = cfg.get("kernel_source", cfg.get("kernel_repo", {}))
    return (
        int(src.get("fetch_retries", 3)),
        float(src.get("fetch_retry_backoff_sec", 2.0)),
    )


def fetch_source_file(rel_path: str, cfg: dict, logger: logging.Logger) -> str:
    """从 torvalds/linux v4.14 抓取 .c/.h 实际内核源码文件。"""
    raw_base = _ksrc_raw_base(cfg)
    url = f"{raw_base}/{rel_path}"
    retries, backoff = _ksrc_retries(cfg)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "kernel-daily-study/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            text = data.decode("utf-8", errors="replace")
            logger.debug(f"抓取源码 {rel_path} {len(text)} 字节")
            return text
        except Exception as exc:
            last_exc = exc
            logger.warning(f"抓取失败 (尝试 {attempt}/{retries}) {url}: {exc}")
            time.sleep(backoff * attempt)
    raise RuntimeError(f"抓取 {url} 失败：{last_exc}")


def list_subsystem_files(subdir: str, cfg: dict, logger: logging.Logger) -> list[str]:
    """
    遍历 workspace 中 {subdir}/ 下以 .c/.h 结尾的目录——它们是该学习笔记仓库
    正在追踪的内核源文件（同名），代表「已知存在且值得分析的源文件」。
    也递归支持 include/linux/ 这类多层子系统名：subdir='include/linux'。
    返回相对子系统的路径列表（如 'page_alloc.c'、'cpu.c'、'asm-generic/fixmap.h'）。
    """
    ws = Path(cfg["workspace_root"])
    sd_path = ws / subdir
    if not sd_path.exists() or not sd_path.is_dir():
        logger.warning(f"工作区缺少子系统目录：{sd_path}")
        return []
    files: list[str] = []
    for p in sorted(sd_path.rglob("*")):
        if not p.is_dir():
            continue
        name = p.name
        if not (name.endswith(".c") or name.endswith(".h")):
            continue
        # 相对 workspace/subdir 的路径（如 page_alloc.c 或 drivers 下的子嵌套）
        rel_parts = p.relative_to(sd_path).parts
        files.append("/".join(rel_parts))
    # 去重、按名排序
    files = sorted(set(files))
    logger.info(f"子系统 {subdir} 工作区追踪到 {len(files)} 个源文件目录")
    return files


def locate_definition(source: str, name: str, kind: str = "function") -> tuple[int, int]:
    """返回 (line_start_1based, line_end_1based)。若无法定位返回 (1, min(50, len))。"""
    lines = source.splitlines()
    start = -1
    end = -1
    if kind in ("function", "code-block"):
        # Pattern: return_type *name(args) 可能多行，name 在前一行末尾或当前行
        # 1) name( 开头的行（更保守）
        for i, ln in enumerate(lines):
            if re.search(rf"\b{re.escape(name)}\s*\(", ln):
                # 过滤明显的注释/调用点：// /* if (name( =name( -> 必须更严格
                stripped = ln.lstrip()
                if stripped.startswith("*") or stripped.startswith("//"):
                    continue
                # 函数定义通常不包含分号（声明才用）
                if stripped.endswith(";") and "{" not in ln:
                    continue
                start = i + 1
                break
        if start == -1:
            # Fallback: EXPORT_SYMBOL(name) 下方的函数定义不适用，查找 EXPORT 附近
            for i, ln in enumerate(lines):
                if re.search(rf"EXPORT_SYMBOL(?:_GPL)?\s*\(\s*{re.escape(name)}\s*\)", ln):
                    for j in range(i, min(i + 30, len(lines))):
                        if re.search(rf"\b{re.escape(name)}\s*\(", lines[j]):
                            start = j + 1
                            break
                    break
    elif kind == "struct" or kind == "enum":
        for i, ln in enumerate(lines):
            m = re.search(rf"(struct|enum)\s+{re.escape(name)}\s*\{{", ln)
            if m:
                start = i + 1
                break
        if start == -1:
            for i, ln in enumerate(lines):
                m = re.search(rf"(struct|enum)\s+{re.escape(name)}\s*$", ln)
                if m and i + 1 < len(lines) and "{" in lines[i + 1]:
                    start = i + 1
                    break
    if start == -1:
        return (1, min(50, len(lines)))

    # 找到结束行：函数 = 同级 { } 平衡；struct/enum = 遇到 } + 可选后缀
    brace_depth = 0
    started_brace = False
    for i in range(start - 1, len(lines)):
        ln = lines[i]
        # 粗略去掉字符串和注释中的花括号（不影响块深度估算）
        clean = re.sub(r"/\*.*?\*/", "", ln)
        clean = re.sub(r"//.*", "", clean)
        for ch in clean:
            if ch == "{":
                brace_depth += 1
                started_brace = True
            elif ch == "}":
                brace_depth -= 1
        if started_brace and brace_depth == 0:
            end = i + 1
            break
    if end == -1:
        end = min(start + 80, len(lines))
    return (start, end)


def extract_range(source: str, L: int, M: int, ctx: int = 20) -> tuple[str, int, int]:
    lines = source.splitlines()
    L0 = max(1, L - ctx)
    M0 = min(len(lines), M + ctx)
    frag = "\n".join(lines[L0 - 1 : M0])
    return frag, L0, M0


# ============================================================
# 3. 候选识别 + 加权随机选取
# ============================================================
def _analyzed_count_for_file(ws: Path, subsys: str, file_rel: str,
                            analyzed_keys: set[tuple[str, str]]) -> int:
    """统计某 {subsys}/{file_rel} 下已完成的分析笔记数量。
    file_rel 形如 page_alloc.c 或 drivers/xxx/yyy.c。"""
    p = ws / subsys / file_rel
    if not p.exists():
        return 0
    md_names = [x.stem for x in p.iterdir() if x.suffix == ".md" and x.name != "README.md"]
    key_set = set((n, f"{subsys}/{file_rel}") for n in md_names)
    # 同时参考 analyzed_keys 传入值
    key_set |= {(name, f"{subsys}/{file_rel}") for (name, f) in analyzed_keys
                if f == f"{subsys}/{file_rel}"}
    return len(key_set)


def _detect_functions_in_src(src: str, fname: str, prefixes: list[str],
                             max_per: int) -> list[tuple[str, str]]:
    """在单个 .c/.h 源码中检测候选函数/结构，返回 [(name, 'function'|'struct'|'enum')]。"""
    names_found: list[tuple[str, str]] = []

    # (a) EXPORT_SYMBOL 导出函数（最可靠的「核心」）
    for m in re.finditer(r"EXPORT_SYMBOL(?:_GPL)?\s*\(\s*([a-zA-Z_]\w*)\s*\)", src):
        names_found.append((m.group(1), "function"))

    # (b) 命名前缀匹配的函数
    precompiled = [re.compile(p) for p in prefixes]
    # 按行扫描定义：排除注释、#include、宏体
    for line in src.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("*", "//", "#", "module_", "MODULE_")):
            continue
        # 形如 xxx( 的疑似定义；需要更严格的「定义」判断：排除纯调用点
        # 先看有没有 (，且前面是合法 C 标识符名
        m0 = re.search(r"\b([a-zA-Z_]\w*)\s*\(", stripped)
        if not m0:
            continue
        nm = m0.group(1)
        # 定义行特征：行末不是分号（或有 {），或以类型开头
        is_def_like = False
        if "{" in stripped or (not stripped.rstrip().endswith(";") and len(stripped.split()) >= 2):
            is_def_like = True
        # 命名前缀命中
        for rx in precompiled:
            if rx.search(nm):
                names_found.append((nm, "function"))
                break
        # 若为定义行且返回类型复杂（包含 struct/指针/typedef 常见返回），视为核心度加分加入
        if is_def_like and not any(n[0] == nm for n in names_found):
            parts = stripped[: m0.start()].strip().split()
            if len(parts) >= 1:
                last_tok = parts[-1]
                if any(tok in ("struct", "static", "inline", "extern", "asmlinkage",
                               "__init", "__must_check", "unsigned", "signed", "long")
                       for tok in parts) or last_tok.endswith("*") or last_tok in (
                    "int", "long", "void", "char", "short", "size_t", "pid_t",
                    "gfp_t", "pgoff_t", "pte_t", "pmd_t", "pgd_t"):
                    names_found.append((nm, "function"))

    # (c) .h 文件中的 struct / enum 定义
    if fname.endswith(".h"):
        for m in re.finditer(r"^\s*(struct|enum)\s+([a-zA-Z_]\w*)\s*(\{|;)", src, re.MULTILINE):
            kind = m.group(1)
            nm = m.group(2)
            if len(nm) >= 4:  # 过滤常见 1-3 字母占位结构
                names_found.append((nm, kind))

    # 去重保序，限制每文件数量
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for nm, tp in names_found:
        if nm in seen:
            continue
        if len(nm) < 3:
            continue
        seen.add(nm)
        result.append((nm, tp))
        if len(result) >= max_per:
            break
    return result


def identify_core_candidates(subdir: str, cfg: dict, logger: logging.Logger,
                              analyzed_keys: set[tuple[str, str]] | None = None) -> list[dict]:
    """
    返回 list[dict(name, file=f'{subdir}/{fname}', type)]。
    高效策略：利用 workspace 本地目录快速得到已追踪源文件与各文件分析笔记数量，
    只下载「未分析笔记多」的前 N 个文件做真实 C 源码函数检测，避免每轮抓 60 个文件。
    """
    files = list_subsystem_files(subdir, cfg, logger)
    if not files:
        return []
    ws = Path(cfg["workspace_root"])
    if analyzed_keys is None:
        analyzed_keys = set()
    prefixes = cfg["naming_prefixes_function"]
    max_per = int(cfg.get("max_toplevel_candidates_per_file", 25))

    # (a) 工作区每个源文件的已分析笔记数（越低优先级越高，越可能存在未分析核心）
    file_stats: list[tuple[int, str]] = []
    for fname in files:
        n = _analyzed_count_for_file(ws, subdir, fname, analyzed_keys)
        file_stats.append((n, fname))

    # (b) 先处理 0 笔记的文件（全新），然后 1-3 条，最多下载 N 个文件
    file_stats.sort(key=lambda x: x[0])
    N_FILES_TO_SCAN = 4
    chosen_files = [f for (_, f) in file_stats[:N_FILES_TO_SCAN]]
    logger.info(
        f"子系统 {subdir} 准备扫描 {len(chosen_files)} 个源文件 "
        f"(未分析笔记数从低到高：{[n for n,_ in file_stats[:N_FILES_TO_SCAN]]})"
    )

    all_cands: list[dict] = []
    for fname in chosen_files:
        rel = f"{subdir}/{fname}"
        try:
            src = fetch_source_file(rel, cfg, logger)
        except Exception as exc:
            logger.warning(f"抓取 {rel} 失败跳过：{exc}")
            continue
        pairs = _detect_functions_in_src(src, fname, prefixes, max_per)
        batch = [{"name": nm, "file": rel, "type": tp} for (nm, tp) in pairs]
        all_cands.extend(batch)
        logger.debug(f"  {fname}: 检测到 {len(batch)} 候选")
    logger.info(f"子系统 {subdir} 候选总数：{len(all_cands)}")
    return all_cands


def _subsystem_fast_coverage_estimate(
    subdir: str, cfg: dict, analyzed_keys: set[tuple[str, str]], logger: logging.Logger
) -> tuple[int, int]:
    """
    粗略估算某个子系统的已覆盖率（不下载任何文件，仅基于 workspace 本地统计）。
    返回 (analyzed_estimate, total_estimate)。
    粗略规则：每个追踪的源文件 × 平均核心函数数（用 15 作保守估计）作为 total。
    """
    ws = Path(cfg["workspace_root"])
    sd_path = ws / subdir
    if not sd_path.exists():
        return 0, 0
    tracked_files = list_subsystem_files(subdir, cfg, logger)
    analyzed_count = sum(
        1 for (nm, f) in analyzed_keys if f.startswith(f"{subdir}/")
    )
    # 每个追踪文件平均「核心函数容量」估 15；若文件已存分析笔记 ≥ 15 则将该文件 capacity 扩展
    capacity_per_file = 15
    total = 0
    for fname in tracked_files:
        n_done = _analyzed_count_for_file(ws, subdir, fname, analyzed_keys)
        total += max(capacity_per_file, n_done)
    return analyzed_count, max(total, 1)


def _weighted_choice(items: list[dict], weight_key: str = "weight") -> dict:
    total = sum(it.get(weight_key, 1) for it in items)
    r = random.uniform(0, total)
    acc = 0.0
    for it in items:
        acc += it.get(weight_key, 1)
        if acc >= r:
            return it
    return items[-1]


def weighted_subsystem_choice(
    cfg: dict, analyzed: set[tuple[str, str]], logger: logging.Logger
) -> tuple[str, list[dict]]:
    """返回 (subdir, unanalyzed_candidates)；自动处理覆盖率降级。"""
    subsystems = list(cfg["priority_subsystems"])
    threshold = float(cfg.get("subsystem_coverage_threshold", 0.7))
    pick = _weighted_choice(subsystems)
    attempt_list = [pick["dir"]] + [s["dir"] for s in subsystems if s["dir"] != pick["dir"]]

    for sd in attempt_list:
        # 先用本地粗估覆盖率，快速跳过已明显饱和的子系统（不下载）
        an, tot = _subsystem_fast_coverage_estimate(sd, cfg, analyzed, logger)
        est_cov = an / tot if tot > 0 else 0.0
        logger.info(f"子系统 {sd} 粗估覆盖率：{an}/{tot} = {est_cov*100:.1f}%")
        if est_cov >= threshold and sd != attempt_list[-1]:
            logger.info(f"  → 粗估已饱和，跳过下载探测")
            continue
        cands = identify_core_candidates(sd, cfg, logger, analyzed_keys=analyzed)
        if not cands:
            logger.info(f"子系统 {sd} 下载后无候选，降级")
            continue
        unanalyzed = [c for c in cands if (c["name"], c["file"]) not in analyzed]
        total = len(cands)
        if total == 0:
            continue
        coverage = 1.0 - (len(unanalyzed) / total)
        logger.info(f"子系统 {sd}（精确）: 候选 {total}，未分析 {len(unanalyzed)}，已覆盖率 {coverage*100:.1f}%")
        if unanalyzed and (coverage < threshold or sd == attempt_list[-1] or est_cov < threshold):
            return sd, unanalyzed
        if unanalyzed:
            logger.info(f"  → 真实覆盖率 ≥{threshold*100:.0f}%，尝试下一子系统")
    logger.warning("所有子系统核心候选均已覆盖，将退回到首次候选子系统的剩余列表")
    for sd in [s["dir"] for s in subsystems]:
        cands = identify_core_candidates(sd, cfg, logger, analyzed_keys=analyzed)
        unanalyzed = [c for c in cands if (c["name"], c["file"]) not in analyzed]
        if unanalyzed:
            return sd, unanalyzed
    raise RuntimeError("无法在任何子系统中找到未分析候选；请检查网络或分析集扫描。")


def pick_random_target(
    cfg: dict, analyzed: set[tuple[str, str]], logger: logging.Logger, seed: int | None = None
) -> dict:
    if seed is not None:
        random.seed(seed)
    sd, cands = weighted_subsystem_choice(cfg, analyzed, logger)
    chosen = random.choice(cands)
    logger.info(f"随机选定目标：{chosen['name']} @ {chosen['file']} (type={chosen['type']})")
    # 定位行号
    src = fetch_source_file(chosen["file"], cfg, logger)
    L, M = locate_definition(src, chosen["name"], chosen.get("type", "function"))
    frag, L0, M0 = extract_range(src, L, M, ctx=int(cfg.get("mermaid_context_lines", 20)))
    subsys = chosen["file"].split("/")[0]
    target = {
        "name": chosen["name"],
        "file": chosen["file"],
        "line_start": L0,
        "line_end": M0,
        "def_line_start": L,
        "def_line_end": M,
        "subsystem": subsys,
        "type": chosen.get("type", "function"),
        "source_snippet": frag,
        "source_full": src,
    }
    return target


# ============================================================
# 4. 中文分析生成（启发式 + 源码注释语义提取）
# ============================================================
def _summarize_func_comments(src: str, name: str) -> str:
    """提取函数前的 kerneldoc / 多行注释作为功能描述基础。"""
    lines = src.splitlines()
    L, _ = locate_definition(src, name, "function")
    # 向前扫描 40 行找块注释或 /** kerneldoc */
    start_scan = max(0, L - 1 - 40)
    comment_lines: list[str] = []
    in_comment = False
    end = L - 2
    for i in range(end, start_scan - 1, -1):
        ln = lines[i].rstrip()
        if not in_comment:
            if ln.endswith("*/") and "/*" not in ln:
                in_comment = True
                comment_lines.append(ln)
            elif "/*" in ln and "*/" in ln:
                comment_lines.append(ln)
                break
            elif ln.lstrip().startswith("*"):
                comment_lines.append(ln)
                in_comment = True
            else:
                # 非注释行：若已收集则停
                if comment_lines:
                    break
        else:
            if "/*" in ln:
                comment_lines.append(ln)
                break
            else:
                comment_lines.append(ln)
    comment_lines.reverse()
    raw = "\n".join(comment_lines)
    # 清除 /* */ 与行首 *
    cleaned = re.sub(r"/\*\*?", "", raw)
    cleaned = re.sub(r"\*/", "", cleaned)
    cleaned = "\n".join(re.sub(r"^\s*\*\s?", "", ln) for ln in cleaned.splitlines())
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _parse_signature(src: str, name: str) -> dict:
    lines = src.splitlines()
    L, _ = locate_definition(src, name, "function")
    # 从 L-1 开始收集直到遇到 { 或 ;
    sig_lines = []
    for i in range(L - 1, len(lines)):
        ln = lines[i]
        sig_lines.append(ln)
        if "{" in ln or ln.rstrip().endswith(";"):
            break
    sig = " ".join(l.strip() for l in sig_lines).strip()
    params_match = re.search(rf"\b{re.escape(name)}\s*\(([^)]*)\)", sig, re.DOTALL)
    params = params_match.group(1).strip() if params_match else ""
    ret_match = re.match(r"^\s*(?:static\s+|inline\s+|extern\s+|asmlinkage\s+|__init\s+|__must_check\s+)*(.*?)\s*\*?\s*" + re.escape(name) + r"\s*\(", sig)
    ret = ret_match.group(1).strip().rstrip("*").strip() if ret_match else "void"
    if not ret:
        ret = "void"
    # 返回类型的星号归属
    sig_clean = sig
    return {"signature": sig_clean, "params": params, "return": ret}


def _params_to_structs(params: str, ret: str) -> list[str]:
    """提取参数和返回类型中出现的 struct/typedef 名。"""
    tokens = re.findall(r"struct\s+([a-zA-Z_]\w+)|enum\s+([a-zA-Z_]\w+)|([a-zA-Z_]\w+_t)\b", f"{params} {ret}")
    found = []
    for s, e, t in tokens:
        if s:
            found.append(f"struct {s}")
        elif e:
            found.append(f"enum {e}")
        elif t:
            found.append(t)
    # 去重保序
    seen = set()
    out = []
    for x in found:
        if x not in seen and x not in {"struct page", "struct file", "struct inode"}:
            seen.add(x)
            out.append(x)
        elif x not in seen:
            # 常用结构仍然保留但置前
            seen.add(x)
            out.insert(0, x)
    return out


def _extract_callees(snippet: str, exclude_self: str) -> list[dict]:
    """提取函数体中调用的下游函数，按语义重要度粗分。"""
    calls: set[str] = set()
    for m in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", snippet):
        nm = m.group(1)
        # 排除控制流、类型宏、常用 trivial
        if nm in {exclude_self, "if", "for", "while", "switch", "return", "sizeof", "offsetof",
                  "container_of", "likely", "unlikely", "BUILD_BUG_ON", "BUG", "true", "false"}:
            continue
        if nm.startswith(("__builtin_", "atomic_", "READ_ONCE", "WRITE_ONCE")):
            continue
        calls.add(nm)
    # 分类：核心 / 辅助 / 宏
    core = []
    helper = []
    macro_like = []
    for c in calls:
        lc = c.lower()
        if any(k in lc for k in ("spin_lock", "spin_unlock", "mutex", "rcu", "smp_")):
            helper.append(c)
        elif any(k in lc for k in ("alloc", "free", "kzalloc", "kmalloc", "kfree", "vmalloc", "vfree",
                                    "get_zeroed", "page")):
            core.append(c)
        elif c.isupper() or (c[:1].isupper() and "_" in c):
            macro_like.append(c)
        elif any(k in lc for k in ("printk", "pr_warn", "pr_err", "pr_info", "trace_", "perf_")):
            helper.append(c)
        else:
            core.append(c)
    return [
        {"category": "核心路径调用", "items": core[:10]},
        {"category": "辅助调用", "items": helper[:10]},
        {"category": "宏 / 内联", "items": macro_like[:10]},
    ]


def _extract_callers(target_name: str, target_file: str, cfg: dict, logger: logging.Logger) -> list[dict]:
    """
    优先：同文件内 self-caller + 精选的 v4.14 通用入口 hub 文件；
    次级：按子系统遍历工作区追踪的源文件。
    """
    results: list[dict] = []
    NEEDED = int(cfg.get("min_callers_for_table", 5))

    def _scan_one_file(rel: str, src_text: str) -> None:
        if rel == target_file:
            # 自身文件内也算调用者（内部 helper 调用主函数），但标记为「同文件内」
            pass
        for idx, ln in enumerate(src_text.splitlines(), 1):
            stripped = ln.lstrip()
            if stripped.startswith(("*", "//", "#")):
                continue
            if not re.search(rf"\b{re.escape(target_name)}\s*\(", ln):
                continue
            if "EXPORT_SYMBOL" in ln:
                continue
            # 排除本文件中的函数定义行（不是调用）
            if rel == target_file:
                # 调用点：通常在函数体内，行首缩进较多；定义行通常无缩进或少缩进，且紧跟 {
                maybe_def = (not stripped[:1].isspace() or re.match(rf"[a-zA-Z_].*\s{re.escape(target_name)}\s*\(", stripped))
                if maybe_def and ("{" in stripped or not stripped.rstrip().endswith(";")):
                    continue
            scene = "一般调用路径"
            lcl = ln.lower()
            fn = rel.rsplit("/", 1)[-1]
            if any(k in lcl for k in ("sys_", "do_sys", "compat_sys")) or "sys.c" in rel:
                scene = "系统调用入口路径"
            elif "init" in fn or "_init" in lcl or "do_initcalls" in rel or "start_kernel" in src_text[:5000]:
                scene = "子系统初始化路径"
            elif any(k in lcl for k in ("fault", "page_fault", "do_page", "handle_mm_fault", "do_wp_page")):
                scene = "缺页异常处理路径"
            elif any(k in lcl for k in ("clone", "fork", "exec", "kernel_thread", "copy_process", "load_elf_binary")):
                scene = "进程创建/执行路径"
            elif any(k in lcl for k in ("read", "write", "read_iter", "write_iter", "vfs_read", "vfs_write")):
                scene = "文件 I/O 路径"
            elif rel == target_file:
                scene = "同文件内部调用链"
            results.append({
                "caller_site": ln.strip()[:120],
                "file": rel,
                "line": idx,
                "scene": scene,
            })
            return  # 每文件取首个

    # (a) 先扫目标函数所在的源文件自己（内部 helper 可能调用主函数）
    try:
        self_src = fetch_source_file(target_file, cfg, logger)
        _scan_one_file(target_file, self_src)
    except Exception:
        pass
    if len(results) >= NEEDED:
        return results

    # (b) 精选 12 个 v4.14 中调用者最密集的已知入口文件（跨子系统 hub）
    CURATED_HUB_FILES = [
        "kernel/sys.c", "kernel/signal.c", "kernel/exit.c", "kernel/fork.c",
        "kernel/kthread.c", "kernel/workqueue.c",
        "mm/memory.c", "mm/mmap.c", "mm/vmalloc.c",
        "fs/exec.c", "fs/open.c", "fs/read_write.c",
        "fs/namei.c", "fs/namespace.c", "init/main.c",
    ]
    for rel in CURATED_HUB_FILES:
        if rel == target_file:
            continue
        try:
            src = fetch_source_file(rel, cfg, logger)
        except Exception:
            continue
        _scan_one_file(rel, src)
        if len(results) >= NEEDED:
            logger.info(f"调用者检索（精选 hub）完成，共 {len(results)} 条")
            return results

    # (c) 次级：按子系统遍历工作区追踪的前 10 个文件（若还不够）
    subsys_scan = ["kernel", "mm", "fs", "init", "ipc", "lib", "block", "security", "net"]
    target_subsys = target_file.split("/")[0]
    subsys_scan = [target_subsys] + [s for s in subsys_scan if s != target_subsys]
    for sd in subsys_scan:
        files = list_subsystem_files(sd, cfg, logger)
        for fn in files[:10]:
            rel = f"{sd}/{fn}"
            if rel == target_file:
                continue
            if rel in CURATED_HUB_FILES:
                continue  # 已扫过
            try:
                src = fetch_source_file(rel, cfg, logger)
            except Exception:
                continue
            _scan_one_file(rel, src)
            if len(results) >= NEEDED:
                logger.info(f"调用者检索完成，共 {len(results)} 条")
                return results
    logger.info(f"调用者检索完成，共 {len(results)} 条（≤{NEEDED} 由扫描范围决定）")
    return results


def _build_flow_mermaid(target: dict, signature: dict, callees: list[dict]) -> str:
    """构建核心逻辑 Mermaid flowchart TD。"""
    name = target["name"]
    snippet = target["source_snippet"]
    params = signature["params"]
    # 决策点 & 分支启发：从代码中提取错误路径、关键分支
    checks = []
    if params and ("NULL" not in snippet or "!=" in snippet):
        # 常见参数合法性模式
        patterns = [
            (r"if\s*\(\s*!\s*([a-z_]+)\s*\)", "参数 {g[0]} 判空"),
            (r"if\s*\(\s*IS_ERR(_OR_NULL)?\s*\(\s*([a-z_]+)\s*\)", "指针有效性检查 {g[1]}"),
            (r"if\s*\(\s*([a-z_]+)\s*(!=|==|<|>|<=|>=)\s*([^)]+)\)", "条件判断 {g[0]} {g[1]} {g[2]}"),
            (r"goto\s+([a-z_]+)", "跳转错误处理 {g[0]}"),
            (r"return\s+-[A-Z]+;", "返回错误码"),
        ]
        for i, (pat, desc) in enumerate(patterns):
            found = set()
            for m in re.finditer(pat, snippet):
                try:
                    d = desc.format(g=m.groups())
                except Exception:
                    d = desc
                if d not in found:
                    found.add(d)
                    checks.append((d, m.group(0)[:100]))
                if len(found) >= 4:
                    break
            if len(checks) >= 5:
                break

    core_items = []
    for cg in callees:
        if cg["category"] == "核心路径调用":
            core_items = cg["items"][:5]
            break
    helper_items = []
    for cg in callees:
        if cg["category"] == "辅助调用":
            helper_items = cg["items"][:3]
            break

    lines = []
    lines.append("flowchart TD")
    lines.append(f'  A["入口：{name}<br/>返回 {signature["return"]}"] --> B{{参数合法性检查}}')
    # 参数校验分支
    lines.append('  B -->|非法| Z1["返回 -EINVAL / NULL"]')
    # 锁 / 关抢占（如存在）
    lock_step = "B -->|合法| C"
    lock_note = ""
    for it in helper_items:
        if "lock" in it.lower():
            lock_note = f"[{it} / 获取锁 / 关抢占]"
            break
    if not lock_note:
        lock_note = "[获取上下文 / 基本设置]"
    lines.append(f"  C{lock_note}")
    # 核心步骤
    node_idx = 68  # D
    current_letter = "D"
    prev = "C"
    core_count = 0
    for item in core_items:
        lines.append(f"  {prev} --> {current_letter}[核心步骤：{item}]")
        prev = current_letter
        current_letter = chr(ord(current_letter) + 1)
        core_count += 1
        if core_count >= 4:
            break
    # 决策点（若有 checks）
    for i, (desc, _raw) in enumerate(checks[:2]):
        cond_node = current_letter
        yes_letter = chr(ord(current_letter) + 1)
        no_letter = chr(ord(current_letter) + 2)
        lines.append(f"  {prev} --> {cond_node}{{{desc}}}")
        lines.append(f"  {cond_node} -->|是| {yes_letter}[分支 A]")
        lines.append(f"  {cond_node} -->|否| {no_letter}[分支 B]")
        merge = chr(ord(current_letter) + 3)
        lines.append(f"  {yes_letter} --> {merge}[汇合]")
        lines.append(f"  {no_letter} --> {merge}")
        prev = merge
        current_letter = chr(ord(current_letter) + 4)
    # 收尾：释放锁 / 返回
    unlock_step = ""
    for it in helper_items:
        if "unlock" in it.lower() or "spin_unlock" in it.lower() or "mutex_unlock" in it.lower():
            unlock_step = f" --> {current_letter}[释放锁：{it}]"
            break
    if unlock_step:
        lines.append(f"  {prev}{unlock_step}")
        prev = current_letter
    end_letter = "Z"
    lines.append(f"  {prev} --> {end_letter}[返回结果：{signature['return']}]")
    return "\n".join("    " + ln for ln in lines)


def _build_call_graph_mermaid(target: dict, callers: list[dict], callees: list[dict]) -> str:
    lines = ["flowchart LR"]
    tgt = f'{target["name"]}\\n{target["file"]}'
    # 调用者
    for i, c in enumerate(callers[:5], 1):
        call_label = f"{c['file'].split('/')[-1]}:L{c['line']}\\n{c['scene']}"
        lines.append(f'  C{i}["调用者 {i}\\n{call_label}"] --> TARGET["{tgt}"]')
    if not callers:
        lines.append(f'  C0["（未检索到外部调用者）"] --> TARGET["{tgt}"]')
    # 被调用者
    j = 1
    for cg in callees:
        for it in cg["items"][:3]:
            lines.append(f'  TARGET --> D{j}["下游 {cg["category"][:2]}\\n{it}"]')
            j += 1
            if j > 8:
                break
        if j > 8:
            break
    return "\n".join("    " + ln for ln in lines)


def _pitfall_notes(target: dict, snippet: str, signature: dict, callees: list[dict]) -> list[str]:
    """易错点 / 设计权衡 启发式条目生成。"""
    notes = []
    lc = snippet.lower()
    # 锁
    if re.search(r"spin_lock", snippet) and not re.search(r"spin_unlock", snippet[: len(snippet) // 3]):
        notes.append("使用 spin_lock 但需确认所有错误路径均已释放锁，尤其 goto 链上是否漏解锁——典型竞态窗口。")
    if re.search(r"mutex_lock", snippet):
        notes.append("采用 mutex_lock（睡眠锁）：适用场景为进程上下文、持锁时间较长；若处于 atomic context 则必须换用 spinlock。")
    # GFP mask
    gfp = re.findall(r"GFP_[A-Z0-9_]+", snippet)
    if gfp:
        uniq_gfp = list(dict.fromkeys(gfp))[:3]
        notes.append(f"内存分配 GFP mask：{'、'.join(uniq_gfp)}。需关注是否允许睡眠（GFP_KERNEL ≠ GFP_ATOMIC），以及对应 zone / node 选择。")
    # 失败回滚
    gotos = re.findall(r"goto\s+([a-z_]+)", snippet)
    if gotos:
        unique_gotos = list(dict.fromkeys(gotos))[:5]
        notes.append(f"含 goto 跳转链（{' → '.join(unique_gotos)}）：注意标签顺序必须与已分配资源反向释放，避免泄漏。")
    # 返回值 ERR_PTR
    if "ERR_PTR" in snippet or "IS_ERR" in snippet:
        notes.append("返回指针语义：内核约定错误码以 ERR_PTR(-errno) 形式编码在指针内，调用方必须用 IS_ERR / PTR_ERR 检查，不能直接 NULL 判断。")
    # 命名
    if target["name"].startswith("__") and not target["name"].startswith("___"):
        notes.append(f"函数前缀为双下划线 __，通常表示内部版本：调用方需自行持有锁或确保前置条件；误用可能导致死锁或数据竞争。")
    # RCU
    if "rcu_read_lock" in snippet.lower() or "rcu_dereference" in snippet.lower():
        notes.append("RCU 读侧临界区：禁止阻塞睡眠，必须严格 rcu_read_unlock 配对；rcu_dereference 的指针不得在临界区外继续使用。")
    # 不足填充
    default = [
        "参数中含 nodemask_t / gfp_t / 标志位类型：各 flag 的组合顺序直接影响分配策略，建议参考 include/linux/gfp.h 阅读位定义。",
        "结构体字段访问中大量使用 container_of 宏：注意 ptr-偏移 转换的类型安全，字段指针不匹配时会产生隐蔽错位。",
        "跨 NUMA 节点调用：优先在本地 node 分配，失败后走回退/紧凑型回收，性能热点需观察 zonelist 顺序。",
    ]
    for d in default:
        if len(notes) >= 5:
            break
        notes.append(d)
    return notes[:6]


def _infer_purpose(target: dict, kerneldoc: str, signature: dict) -> str:
    """基于函数命名 + kerneldoc 摘要生成中文功能作用段落。"""
    name = target["name"]
    subsys = target["subsystem"]
    ret = signature["return"]
    params = signature["params"]
    purpose = []
    # 1. 头一句：翻译英文注释开头一句，或按子系统 + 命名生成
    if kerneldoc:
        first_line = [l.strip() for l in kerneldoc.splitlines() if l.strip()][:1]
        if first_line:
            purpose.append(f"**注释直译**：{first_line[0]}")
    # 2. 按函数名前缀
    role_map = [
        ("alloc", "资源分配"),
        ("free", "资源释放"),
        ("get", "查找/获取（语义上不增加计数需谨慎）"),
        ("find", "查找（通常不改变引用计数）"),
        ("lookup", "哈希/表查询入口"),
        ("_init", f"{subsys} 子系统初始化入口，通常在内核启动阶段被 do_initcalls 按层级调用"),
        ("setup_", "数据结构/框架的预设与初始化"),
        ("register_", "向内核子系统注册（驱动/文件系统/协议）"),
        ("unregister_", "注销注册并释放对应资源"),
        ("do_", "系统调用或核心操作的真正执行体（通常 sys_* 为入口包装，do_* 为实际逻辑）"),
        ("map", "地址映射/建立映射关系"),
        ("unmap", "解除映射"),
        ("wakeup", "唤醒等待队列或内核线程"),
        ("try_to_", "尝试性操作（失败不直接报错，可能有回退路径）"),
    ]
    matched_roles = []
    for kw, desc in role_map:
        if kw in name.lower():
            matched_roles.append(desc)
    if matched_roles:
        purpose.append(f"**功能归类**：{matched_roles[0]}（从命名模式 `{name}` 推断）。")
    else:
        purpose.append(f"**功能归类**：位于 {subsys} 子系统，返回类型 `{ret}`，为子系统内部或导出的核心实现函数。")

    # 3. 参数描述
    p_list = [p.strip() for p in params.split(",") if p.strip()]
    if p_list:
        p_summary = "；".join(p_list[:5])
        purpose.append(f"**典型入参**：{p_summary}；参数包含分配掩码、节点/zone 约束、回调指针等时，决定该函数的行为变体。")

    # 4. 场景
    scene_hints = []
    if "init" in name.lower() or subsys == "init":
        scene_hints.append("内核启动阶段（start_kernel → do_initcalls 链）")
    if subsys == "mm":
        scene_hints.append("用户进程内存分配/缺页/回收等热路径")
    if subsys == "fs":
        scene_hints.append("VFS 层被具体文件系统 ext4/btrfs 等回调")
    if subsys == "kernel/sched" or subsys == "kernel":
        scene_hints.append("调度器 tick / 唤醒 / fork / exec 等进程生命周期关键节点")
    if "sys_" in name.lower() or name.lower().startswith("do_sys"):
        scene_hints.append("用户态系统调用的内核入口（由 syscall 指令陷入）")
    if not scene_hints:
        scene_hints.append("由子系统内其他导出函数间接调用")
    purpose.append(f"**主要被调场景**：{'；'.join(scene_hints)}。")
    return "\n\n".join(purpose)


def _build_data_structures(target: dict, signature: dict) -> str:
    structs = _params_to_structs(signature["params"], signature["return"])
    # 附加源码片段中出现的核心结构
    snippet = target["source_snippet"]
    for m in re.finditer(r"struct\s+([a-zA-Z_]\w+)\s*\*?\s+([a-zA-Z_]\w+)\s*[;,\){\[=]", snippet):
        full = f"struct {m.group(1)}"
        if full not in structs:
            structs.append(full)
    if not structs:
        structs = ["（未在签名内显式识别到自定义结构，参数为 C 基础类型 / 内核通用 typedef）"]
    out_lines = []
    for s in structs[:8]:
        # 查找工作区已有分析链接
        link = ""
        if s.startswith("struct "):
            sname = s[len("struct "):]
            # glob workspace: include/linux/xxx.h/struct_xxx.md 或对应子系统
            cand_paths = [f"include/linux/mm_types.h/struct_{sname}.md",
                          f"include/linux/sched.h/struct_{sname}.md",
                          f"include/linux/fs.h/struct_{sname}.md"]
            # 实际链接写入时再判断文件存在，这里先占位再修补
            for cp in cand_paths:
                full_cp = Path("/workspace") / cp
                if full_cp.exists():
                    link = f"  - 详细分析：[struct_{sname}.md](../{cp})"
                    break
        field_desc = {
            "struct page": "描述一帧物理页的核心元数据（flags、_refcount、mapping、index、lru 等），是伙伴系统/SLAB/页缓存的基础操作单位。",
            "struct vm_area_struct": "表示一个虚拟内存区域 VMA，含 start/end、vm_flags、vm_file、vm_ops；mmap、缺页、mprotect 的核心操作对象。",
            "struct mm_struct": "进程地址空间描述符，含 mmap/vma 链表、pgd、RSS 计数等，共享于同一线程组。",
            "struct task_struct": "进程描述符，包含调度实体、内存、文件、信号、命名空间等完整状态。",
            "struct file": "已打开文件描述（f_op、f_path、f_pos、f_flags），内核中每个 open fd 对应一个 file。",
            "struct inode": "磁盘文件元数据的内核内缓存：i_sb、i_op、i_mapping、i_mode、i_ino。",
            "struct dentry": "目录项缓存，将文件路径名关联到 inode；含 d_name、d_parent、d_op、d_revalidate。",
            "struct super_block": "已挂载文件系统的超级块，含文件系统类型、根 dentry、s_op、s_flags。",
            "struct zone": "NUMA 节点内的内存区域（DMA/NORMAL/HIGHMEM 等），伙伴系统以 zone 为管理单位。",
            "struct zonelist": "按优选顺序排列的 zone 列表，用于页分配时跨 zone/跨 node 回退。",
            "gfp_t": "无符号整数位图，组合 GFP_KERNEL / GFP_ATOMIC / __GFP_NOWARN 等分配策略标志。",
            "nodemask_t": "NUMA 节点集位图，控制分配允许尝试哪些节点。",
            "pgoff_t": "页粒度偏移量，用于 page cache index / VMA 内 offset。",
            "pgd_t": "页全局目录项，页表层级顶层指针类型。",
        }.get(s, "该结构/类型的完整字段请参考对应头文件，本节聚焦其在本函数中的语义角色。")
        out_lines.append(f"- `{s}`：")
        out_lines.append(f"  - 语义：{field_desc}")
        if link:
            out_lines.append(link)
    return "\n".join(out_lines)


def generate_analysis(
    target: dict,
    cfg: dict,
    logger: logging.Logger,
    date: str,
) -> tuple[str, list[dict]]:
    """返回 (full_markdown_str, callers_list)。"""
    name = target["name"]
    src = target["source_full"]
    snippet = target["source_snippet"]
    # 分析上下文
    sig = _parse_signature(src, name) if target["type"] != "struct" else {
        "signature": f"struct/enum {name}",
        "params": "",
        "return": "void",
    }
    kdoc = _summarize_func_comments(src, name) if target["type"] != "struct" else ""
    callees = _extract_callees(snippet, exclude_self=name)
    callers = _extract_callers(name, target["file"], cfg, logger)

    # 各章节
    title = f"# 每日内核源码分析：{name}"
    meta = [
        f"- **日期**：{date}",
        f"- **子系统**：{target['subsystem']}",
        f"- **源文件**：{target['file']}:{target['def_line_start']}-{target['def_line_end']}",
        f"- **类型**：{target['type']}",
    ]

    purpose = _infer_purpose(target, kdoc, sig)
    data_structs = _build_data_structures(target, sig)

    # 3. 核心逻辑流程图
    flow_mermaid = _build_flow_mermaid(target, sig, callees)
    # 解读点：从 checks 列表生成 3~6 条
    flow_notes = []
    snippet_lower = snippet.lower()
    flow_notes.append(f"**入口 A**：{name} 作为 {target['type'] == 'function' and '函数' or '结构'} 入口，接收 {len(sig['params'].split(',')) if sig['params'] else 0} 个参数，返回类型为 `{sig['return']}`。")
    if re.search(r"if\s*\(\s*!", snippet):
        flow_notes.append("**参数校验 B**：对指针类参数进行 NULL 判空并提前返回错误，遵循「快速失败」原则，避免进入核心资源分配后再回滚。")
    if "spin_lock" in snippet_lower or "mutex_lock" in snippet_lower:
        flow_notes.append("**锁节点 C**：进入核心逻辑前获取锁；锁选择（mutex vs spin）取决于调用上下文是否允许睡眠，以及持锁时间。")
    if any(cg["items"] and cg["category"] == "核心路径调用" for cg in callees):
        for cg in callees:
            if cg["category"] == "核心路径调用" and cg["items"]:
                flow_notes.append(f"**核心步骤 D+**：{'、'.join(cg['items'][:3])} 等驱动主逻辑；它们往往是子系统内进一步分层的函数（如缓存命中 → 慢速路径）。")
                break
    if "goto" in snippet_lower:
        flow_notes.append("**错误处理链**：使用 goto 跳到统一标签执行资源逆序释放，该模式是内核驱动错误路径的惯用写法。")
    flow_notes.append(f"**收尾 Z**：释放锁/递减引用计数后返回 `{sig['return']}`，成功返回正指针/0，失败返回 ERR_PTR 或负 errno。")

    # 4. 调用关系
    callers_table_rows = []
    for c in callers:
        callers_table_rows.append(
            f"| `{c['file'].split('/')[-1]}:L{c['line']}` | `{c['file']}` | {c['scene']} |"
        )
    if not callers_table_rows:
        callers_table_rows.append("| （未检索到典型调用者，可能是静态局部入口） | 同上 | / |")
    callees_sections = []
    for cg in callees:
        items = cg["items"]
        if not items:
            continue
        callees_sections.append(f"- **{cg['category']}**：`{'`、`'.join(items[:6])}`")
    if not callees_sections:
        callees_sections.append("- （未在当前片段中检测到明显下游调用，可能是轻量内联 / 宏展开）")
    call_graph_mermaid = _build_call_graph_mermaid(target, callers, callees)

    # 5. 易错点
    pitfalls = _pitfall_notes(target, snippet, sig, callees)

    # 附：源码片段（保留关键注释去冗）
    snippet_cleaned_lines = []
    for ln in snippet.splitlines():
        # 去掉过多空白行，但保留整体可读性
        if snippet_cleaned_lines and ln.strip() == "" and snippet_cleaned_lines[-1].strip() == "":
            continue
        snippet_cleaned_lines.append(ln)
    snippet_out = "\n".join(snippet_cleaned_lines[:200])

    # 汇总
    sections = [
        title,
        "",
        *meta,
        "",
        "---",
        "",
        "## 1. 功能作用",
        "",
        purpose,
        "",
        "## 2. 关键数据结构",
        "",
        data_structs,
        "",
        "## 3. 核心逻辑流程图",
        "",
        "```mermaid",
        flow_mermaid,
        "```",
        "",
        "**流程关键决策点解读**：",
        "",
        *[f"- {n}" for n in flow_notes[:6]],
        "",
        "## 4. 调用关系",
        "",
        "### 4.1 调用者（who calls me）",
        "",
        "| 调用方 | 所在文件 | 调用场景 |",
        "|--------|----------|----------|",
        *callers_table_rows,
        "",
        "### 4.2 被调用者（who I call）",
        "",
        *callees_sections,
        "",
        "### 4.3 调用关系图",
        "",
        "```mermaid",
        call_graph_mermaid,
        "```",
        "",
        "## 5. 易错点 / 边界场景 / 设计权衡",
        "",
        *[f"- {p}" for p in pitfalls],
        "",
        "## 附：核心源码片段",
        "",
        f"```c",
        f"// {target['file']}:{target['line_start']}-{target['line_end']}",
        snippet_out,
        "```",
        "",
    ]
    return "\n".join(sections), callers


# ============================================================
# 5. 双写归档与索引
# ============================================================
def _date_dirs(date: str, archive_root: Path) -> tuple[Path, Path]:
    """返回 (main_archive_dir, daily_root)。"""
    d = _dt.date.fromisoformat(date)
    daily_root = archive_root
    main_dir = daily_root / f"{d.year:04d}" / f"{d.month:02d}" / f"{date}"
    return main_dir, daily_root


def write_archives(
    target: dict,
    content: str,
    date: str,
    cfg: dict,
    logger: logging.Logger,
) -> tuple[Path, Path]:
    """返回 (主归档路径, 就地归档路径)。"""
    ws = Path(cfg["workspace_root"])
    archive_root = Path(cfg["archive_root"])
    main_dir, _ = _date_dirs(date, archive_root)
    _ensure_dir(main_dir)

    # 主归档
    main_path = main_dir / f"{target['subsystem']}_{target['name']}.md"
    main_path.write_text(content, encoding="utf-8")
    logger.info(f"[归档] 主：{main_path}")

    # 就地归档
    file_rel = target["file"]  # e.g. mm/page_alloc.c
    parts = file_rel.split("/")
    subsys = parts[0]
    srcfile = "/".join(parts[1:]) if len(parts) > 2 else parts[1]
    local_dir = ws / subsys / srcfile
    _ensure_dir(local_dir)
    local_path = local_dir / f"{target['name']}.md"
    local_path.write_text(content, encoding="utf-8")
    logger.info(f"[归档] 就地：{local_path}")

    # README.md 追加（若存在）
    readme = local_dir / "README.md"
    if readme.exists():
        summary = _first_function_summary(target, content)
        row = f"| `{target['name']}` | {summary} | [分析笔记](./{target['name']}.md) | {date} |"
        existing = readme.read_text(encoding="utf-8", errors="ignore")
        if f"[分析笔记](./{target['name']}.md)" not in existing:
            with open(readme, "a", encoding="utf-8") as f:
                f.write("\n" + row + "\n")
            logger.info(f"[归档] 已更新子系统 README：{readme}")
    return main_path, local_path


def _first_function_summary(target: dict, content: str) -> str:
    """从功能作用章节取首句作为 README 摘要。"""
    for line in content.splitlines():
        if line.startswith("**功能归类**") or line.startswith("**注释直译**"):
            s = line.split("：", 1)[-1] if "：" in line else line
            s = s.strip().rstrip("。").rstrip(".")
            return s[:60] + ("…" if len(s) > 60 else "")
    return f"{target['subsystem']} 子系统 {target['type']} 分析"


def update_indexes(
    target: dict,
    date: str,
    main_path: Path,
    cfg: dict,
    logger: logging.Logger,
    feishu_status: str = "pending",
    feishu_doc_url: str | None = None,
) -> None:
    archive_root = Path(cfg["archive_root"])
    _, daily_root = _date_dirs(date, archive_root)
    _ensure_dir(daily_root)
    main_rel_for_idx = main_path.relative_to(archive_root)

    # ===== INDEX.md =====
    idx_path = daily_root / "INDEX.md"
    header = [
        "# 每日内核学习索引",
        "",
        "| 日期 | 子系统 | 目标名称 | 类型 | 归档链接 |",
        "|------|--------|----------|------|----------|",
    ]
    row = f"| {date} | {target['subsystem']} | `{target['name']}` | {target['type']} | [{target['file']}]({main_rel_for_idx}) |"
    if idx_path.exists():
        lines = idx_path.read_text(encoding="utf-8").splitlines()
        # 找到表头分隔线之后插入新行（保持日期倒序）
        insert_at = -1
        for i, ln in enumerate(lines):
            if ln.startswith("|------"):
                insert_at = i + 1
                break
        if insert_at != -1 and row not in "\n".join(lines):
            lines.insert(insert_at, row)
            idx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            with open(idx_path, "a", encoding="utf-8") as f:
                f.write(row + "\n")
    else:
        idx_path.write_text("\n".join(header + [row, ""]), encoding="utf-8")
    logger.info(f"[索引] INDEX.md → {idx_path}")

    # ===== by-subsystem.md =====
    bysub_path = daily_root / "by-subsystem.md"
    subsys_header = f"## {target['subsystem']}"
    entry_row = f"- [{date}] `{target['name']}` @ `{target['file']}` — [笔记]({main_rel_for_idx})"
    if bysub_path.exists():
        text = bysub_path.read_text(encoding="utf-8")
        if subsys_header not in text:
            text += f"\n\n{subsys_header}\n\n{entry_row}\n"
        else:
            # 插入到对应小节末尾
            updated = re.sub(
                rf"({re.escape(subsys_header)}\n(?:.|\n)*?)(?=\n## |\Z)",
                lambda m: f"{m.group(1)}{entry_row}\n" if entry_row not in m.group(1) else m.group(1),
                text,
            )
            if updated == text:
                text += entry_row + "\n"
            else:
                text = updated
        bysub_path.write_text(text, encoding="utf-8")
    else:
        bysub_path.write_text(
            f"# 按子系统分类索引\n\n{subsys_header}\n\n{entry_row}\n",
            encoding="utf-8",
        )
    logger.info(f"[索引] by-subsystem.md → {bysub_path}")

    # ===== progress-stats.json =====
    stats_path = daily_root / "progress-stats.json"
    if stats_path.exists():
        try:
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
        except Exception:
            stats = {}
    else:
        stats = {}
    if not isinstance(stats, dict):
        stats = {}
    # 初始化字段
    stats.setdefault("by_subsystem", {})
    bss = stats["by_subsystem"]
    if not isinstance(bss, dict):
        bss = {}
        stats["by_subsystem"] = bss
    bss[target["subsystem"]] = int(bss.get(target["subsystem"], 0)) + 1
    total = sum(int(v) for v in bss.values())
    stats["total_analyzed"] = total
    stats["last_run"] = date
    # 每日条目
    stats.setdefault("daily_runs", [])
    existing_dates = [r.get("date") for r in stats["daily_runs"] if isinstance(r, dict)]
    run_entry = {
        "date": date,
        "subsystem": target["subsystem"],
        "name": target["name"],
        "file": target["file"],
        "type": target["type"],
        "main_archive": str(main_path),
        "feishu_status": feishu_status,
        "feishu_doc_url": feishu_doc_url,
    }
    if date in existing_dates:
        # 替换同日条目
        stats["daily_runs"] = [
            r if (isinstance(r, dict) and r.get("date") != date) else run_entry
            for r in stats["daily_runs"]
        ]
    else:
        stats["daily_runs"].append(run_entry)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info(f"[索引] progress-stats.json 已更新：共 {total} 条，今日状态={feishu_status}")


# ============================================================
# 6. 飞书推送（调用 lark-cli 子进程）
# ============================================================
def push_to_feishu(
    target: dict,
    content: str,
    main_md_path: Path,
    local_md_path: Path,
    date: str,
    cfg: dict,
    logger: logging.Logger,
) -> tuple[str, str | None]:
    """
    返回 (status, url_or_None)
    status ∈ {success, deferred_im, skipped_unauthorized, failed}
    """
    feishu_cfg = cfg.get("feishu", {})
    if not feishu_cfg.get("enabled", True):
        return "skipped_disabled", None
    cli = feishu_cfg.get("lark_cli_path", "lark-cli")
    # 首先检查 lark-cli 是否可用
    try:
        res = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            logger.warning("lark-cli 不可用，跳过飞书推送")
            return "skipped_unauthorized", None
    except FileNotFoundError:
        logger.warning("未找到 lark-cli")
        return "skipped_unauthorized", None

    prefer = feishu_cfg.get("prefer", "docx")
    # === 创建 Docx ===
    if prefer in {"docx", "doc"}:
        title_tpl = feishu_cfg.get("docx", {}).get(
            "title_template", "【{date} 内核每日学习】{subsystem}/{name}"
        )
        title = title_tpl.format(date=date, subsystem=target["subsystem"], name=target["name"])
        parent_pos = feishu_cfg.get("docx", {}).get("parent_position", "my_library")
        # lark-cli 要求 @file 使用 workspace 内的相对路径（或 stdin 的 -）
        # 策略：把临时 .md 写到 {archive_root}/.tmp/ 下，再以 workspace 为 cwd 执行 subprocess
        tmp_root = Path(cfg["archive_root"]) / ".tmp"
        _ensure_dir(tmp_root)
        tmp_name = f"feishu_{date}_{target['subsystem']}_{target['name']}_{os.getpid()}.md"
        tmp_path = tmp_root / tmp_name
        tmp_path.write_text(content, encoding="utf-8")
        # 相对路径（相对于 workspace_root）
        ws = Path(cfg["workspace_root"]).resolve()
        try:
            rel_for_cli = "./" + str(tmp_path.resolve().relative_to(ws))
        except ValueError:
            rel_for_cli = str(tmp_path)
        try:
            args = [
                cli, "docs", "+create",
                "--title", title,
                "--doc-format", "markdown",
                "--content", f"@{rel_for_cli}",
            ]
            if parent_pos:
                args.extend(["--parent-position", parent_pos])
            parent_token = feishu_cfg.get("docx", {}).get("parent_token", "")
            if parent_token:
                args.extend(["--parent-token", parent_token])
            logger.info(f"[飞书] 执行：cwd={ws} args={' '.join(args[:6])} ...")
            res = subprocess.run(args, capture_output=True, text=True, timeout=180, cwd=str(ws))
            # 清理临时文件
            try:
                tmp_path.unlink()
            except Exception:
                pass
            if res.returncode == 0:
                try:
                    data = json.loads(res.stdout)
                    if data.get("ok"):
                        d = data.get("data", {})
                        url = d.get("document", {}).get("url") or d.get("url") or d.get("link")
                        if not url:
                            tk = d.get("document", {}).get("document_id") or d.get("document_id")
                            if tk:
                                url = f"https://feishu.cn/docx/{tk}"
                        logger.info(f"[飞书] Docx 创建成功：{url}")
                        return "success", url
                except json.JSONDecodeError:
                    pass
                logger.warning(f"[飞书] 创建返回但解析失败：{res.stdout[:500]}")
                if res.stderr:
                    logger.warning(f"  stderr: {res.stderr[:400]}")
            else:
                logger.warning(f"[飞书] 创建 Docx 失败 rc={res.returncode}")
                if res.stdout:
                    logger.warning(f"  stdout: {res.stdout[:500]}")
                if res.stderr:
                    logger.warning(f"  stderr: {res.stderr[:500]}")
        except Exception as exc:
            logger.warning(f"[飞书] 创建 Docx 异常：{exc}")
            try:
                tmp_path.unlink()
            except Exception:
                pass

    # === 降级 IM ===
    im_cfg = feishu_cfg.get("im", {})
    user_id = im_cfg.get("user_id")
    chat_id = im_cfg.get("chat_id")
    if not user_id and not chat_id:
        return "failed", None
    # 组装 markdown 摘要
    brief_parts = [
        f"## 🔬 【{date}】内核每日学习摘要",
        "",
        f"- **目标**：`{target['name']}`（{target['type']}）",
        f"- **子系统**：{target['subsystem']}",
        f"- **源文件**：`{target['file']}:{target['def_line_start']}`",
        "",
        "**功能一句话**：" + _first_function_summary(target, content),
        "",
        f"- 📁 主归档：`{main_md_path}`",
        f"- 📁 就地归档：`{local_md_path}`",
    ]
    md_text = "\n".join(brief_parts)
    args = [cli, "im", "+messages-send"]
    if chat_id:
        args.extend(["--chat-id", chat_id])
    elif user_id:
        args.extend(["--user-id", user_id])
    args.extend(["--markdown", md_text])
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            logger.info("[飞书] IM 摘要发送成功")
            return "deferred_im", None
        else:
            logger.warning(f"[飞书] IM 发送失败 rc={res.returncode}：{res.stderr[:400]}")
    except Exception as exc:
        logger.warning(f"[飞书] IM 发送异常：{exc}")
    return "failed", None


# ============================================================
# 7. 主流程编排
# ============================================================
def _print_summary(target: dict, main_path: Path, local_path: Path,
                   feishu_status: str, feishu_url: str | None,
                   cfg: dict, date: str) -> None:
    stats_path = Path(cfg["archive_root"]) / "progress-stats.json"
    total = "?"
    by_subsys = ""
    if stats_path.exists():
        try:
            s = json.loads(stats_path.read_text(encoding="utf-8"))
            total = str(s.get("total_analyzed", "?"))
            bs = s.get("by_subsystem", {})
            if isinstance(bs, dict):
                by_subsys = "  ".join(f"{k}={v}" for k, v in sorted(bs.items()))
        except Exception:
            pass
    print("=" * 70)
    print(f"✅ [每日内核学习] {date} 执行完成")
    print(f"   分析目标：{target['file']}  →  {target['name']} ({target['type']})")
    print(f"   主归档：{main_path}")
    print(f"   就地：  {local_path}")
    print(f"   飞书：  status={feishu_status}  url={feishu_url or 'N/A'}")
    print(f"   累计进度：total={total}  by_subsys=[{by_subsys}]")
    print("=" * 70)


def run_full_pipeline(cfg: dict, logger: logging.Logger, force: bool = False,
                      seed: int | None = None, date_override: str | None = None) -> int:
    date = today_str(date_override)
    main_dir, _ = _date_dirs(date, Path(cfg["archive_root"]))
    # 幂等检查
    if main_dir.exists() and not force:
        existing_md = sorted(main_dir.glob("*.md"))
        if existing_md:
            logger.info(f"今日 {date} 已分析，直接返回已有结果（{existing_md[0]}）。如需重新执行加 --force。")
            print(f"今日已分析，直接返回结果：{existing_md[0]}")
            # 读 stats 打印 summary
            main_path = existing_md[0]
            # 从 progress 里取 target 信息
            stats_path = Path(cfg["archive_root"]) / "progress-stats.json"
            target_info = {"name": "?", "file": "?", "subsystem": "?", "type": "?"}
            fs_s = "?"
            fs_u = None
            if stats_path.exists():
                try:
                    s = json.loads(stats_path.read_text(encoding="utf-8"))
                    for r in s.get("daily_runs", []):
                        if r.get("date") == date:
                            target_info = {k: r.get(k, target_info[k]) for k in target_info}
                            fs_s = r.get("feishu_status", "?")
                            fs_u = r.get("feishu_doc_url")
                except Exception:
                    pass
            _print_summary(target_info, main_path, main_path, fs_s, fs_u, cfg, date)
            return 0
    # 正式流程
    analyzed = build_analyzed_set(cfg, logger)
    target = pick_random_target(cfg, analyzed, logger, seed=seed)
    content, _callers = generate_analysis(target, cfg, logger, date)
    main_path, local_path = write_archives(target, content, date, cfg, logger)
    # 先写一次索引（pending feishu）
    update_indexes(target, date, main_path, cfg, logger, feishu_status="pending")
    # 推送飞书
    fs_status, fs_url = push_to_feishu(target, content, main_path, local_path, date, cfg, logger)
    # 再次更新索引以写入推送状态
    update_indexes(target, date, main_path, cfg, logger, feishu_status=fs_status, feishu_doc_url=fs_url)
    _print_summary(target, main_path, local_path, fs_status, fs_url, cfg, date)
    return 0


def select_only(cfg: dict, logger: logging.Logger, seed: int | None = None) -> int:
    analyzed = build_analyzed_set(cfg, logger)
    target = pick_random_target(cfg, analyzed, logger, seed=seed)
    # 精简输出：仅保留可序列化字段
    slim = {k: v for k, v in target.items() if k not in {"source_full", "source_snippet"}}
    slim["def_lines"] = [target["def_line_start"], target["def_line_end"]]
    slim["snippet_lines"] = [target["line_start"], target["line_end"]]
    print(json.dumps(slim, ensure_ascii=False, indent=2))
    return 0


def dry_run(cfg: dict, logger: logging.Logger) -> int:
    print(f"[配置] 配置文件已加载：{DEFAULT_CONFIG_PATH}")
    analyzed = build_analyzed_set(cfg, logger)
    print(f"[配置] 已分析函数：{len(analyzed)} 个")
    # 随机选 1 个子系统做候选探测（小规模）
    subsystems = cfg["priority_subsystems"]
    pick = _weighted_choice(subsystems)
    cands = identify_core_candidates(pick["dir"], cfg, logger)
    unanalyzed = [c for c in cands if (c["name"], c["file"]) not in analyzed]
    print(f"[配置] 优先子系统加权采样 → {pick['dir']}，候选集 {len(cands)}，未分析候选集 {len(unanalyzed)}")
    # 测试抓取一个文件
    if cands:
        sample = cands[0]
        try:
            src = fetch_source_file(sample["file"], cfg, logger)
            print(f"[网络] 抓取测试 OK：{sample['file']} {len(src)} 字节")
        except Exception as exc:
            print(f"[网络] 抓取测试 FAIL：{exc}")
            return 2
    print("配置加载成功 / 已分析统计完成 / 候选集 OK / 网络抓取正常")
    return 0


# ============================================================
# CLI
# ============================================================
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kernel_daily.py", description="Linux 内核每日源码学习引擎")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件路径")
    ap.add_argument("--dry-run", action="store_true", help="仅加载配置、探测网络、打印统计，不写文件")
    ap.add_argument("--select-only", action="store_true", help="仅随机选择目标并打印 JSON，不写文件不归档")
    ap.add_argument("--force", action="store_true", help="即使今日已分析也强制重跑")
    ap.add_argument("--seed", type=int, default=None, help="随机种子（用于复现实验）")
    ap.add_argument("--date", default=None,
                    help="覆盖今日日期（ISO 格式 YYYY-MM-DD），或通过环境变量 KERNEL_DAILY_DATE_OVERRIDE 设置")
    ap.add_argument("--agent-enhance", metavar="MD_FILE", help="由外部 Agent 重写分析正文内容后再调用（预留接口）")
    args = ap.parse_args(argv)

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"ERROR: 配置文件不存在 {cfg_path}", file=sys.stderr)
        return 3
    cfg = load_config(cfg_path)
    _ensure_dir(Path(cfg["log_root"]))
    log_path = Path(cfg["log_root"]) / f"{today_str(args.date)}.log"
    logger = _setup_logger(log_path)
    logger.info("=" * 50)
    logger.info(f"启动 kernel_daily.py：dry_run={args.dry_run} select_only={args.select_only} force={args.force} date={today_str(args.date)}")

    try:
        if args.dry_run:
            return dry_run(cfg, logger)
        if args.select_only:
            return select_only(cfg, logger, seed=args.seed)
        # agent-enhance 接口：重写某个 md 文件不会改变主流程
        return run_full_pipeline(cfg, logger, force=args.force, seed=args.seed,
                                 date_override=args.date)
    except Exception as exc:
        logger.exception(f"运行失败：{exc}")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
