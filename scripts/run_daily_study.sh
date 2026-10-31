#!/usr/bin/env bash
# 每日内核学习工作流入口。
#
# 用法：
#   ./scripts/run_daily_study.sh prepare [子系统]   # 随机选点并打印源码位置
#   ./scripts/run_daily_study.sh finish             # 归档 + 推送飞书
#
# 两阶段之间由 Agent（Skill: linux-kernel-daily-study）读取源码并生成
# 中文分析，写入 $WORK/analysis.md；随后执行 finish 即可。
set -euo pipefail

ROOT="${KERNEL_STUDY_ROOT:-/workspace}"
WORK="${KERNEL_STUDY_WORK:-$HOME/.cache/kernel-study/daily/$(date +%F)}"
PY="$ROOT/scripts/kernel_daily_study.py"

usage() {
  sed -n '2,9p' "$0" | sed 's/^# \{0,1\}/  /'
}

case "${1:-}" in
  prepare)
    mkdir -p "$WORK"
    python3 "$PY" pick --out "$WORK/target.json" ${2:+--subsystem "$2"}
    echo
    echo "TARGET_JSON=$WORK/target.json"
    echo "ANALYSIS_MD=$WORK/analysis.md"
    echo "下一步：写入 analysis.md 后执行 $0 finish"
    ;;
  finish)
    if [[ ! -f "$WORK/target.json" || ! -f "$WORK/analysis.md" ]]; then
      echo "缺少 $WORK/target.json 或 $WORK/analysis.md，请先执行 prepare 并生成分析。" >&2
      exit 1
    fi
    python3 "$PY" archive --meta "$WORK/target.json" --analysis "$WORK/analysis.md"
    python3 "$PY" publish --meta "$WORK/target.json" --analysis "$WORK/analysis.md"
    ;;
  *)
    usage
    exit 1
    ;;
esac
