#!/usr/bin/env bash
#===============================================================================
# kernel_daily_study.sh —— Linux 内核每日源码学习入口脚本
# 用法：
#   kernel_daily_study.sh                # 正常执行（幂等：已执行同日则直接返回）
#   kernel_daily_study.sh --dry-run      # 自检：加载配置、打印统计、抓取测试、不写文件
#   kernel_daily_study.sh --select-only  # 仅随机选目标并打印 JSON，不写不归档
#   kernel_daily_study.sh --force        # 即使今日已分析也强制重跑
#
# 定时任务示例 (cron):
#   0 9 * * * /workspace/scripts/kernel_daily_study.sh >> /workspace/daily/logs/cron.log 2>&1
#===============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_ENTRY="${SCRIPT_DIR}/kernel_daily.py"
CONFIG_FILE="${SCRIPT_DIR}/.kernel-daily-config.json"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "ERROR: 未找到 python3/python 解释器" >&2
  exit 127
fi

if [ ! -f "${CONFIG_FILE}" ]; then
  echo "ERROR: 配置文件不存在：${CONFIG_FILE}" >&2
  exit 3
fi

# 确保依赖目录存在（Python 内部也会做）
WORKSPACE_ROOT="$(python3 -c "import json,sys;d=json.load(open('${CONFIG_FILE}'));print(d['workspace_root'])" 2>/dev/null || echo "/workspace")"
ARCHIVE_ROOT="${WORKSPACE_ROOT}/daily"
mkdir -p "${ARCHIVE_ROOT}/logs"

exec "${PYTHON_BIN}" "${PY_ENTRY}" --config "${CONFIG_FILE}" "$@"