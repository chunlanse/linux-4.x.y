#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/kernel_daily.py"
STATE="$DIR/.state"

prepare() {
  "$DIR/prepare_source.sh"
  python3 "$PY" select
}

agent() {
  local prompt="$STATE/current-prompt.md"
  local report
  report="$(jq -r '.report_path' "$STATE/current-target.json")"
  if [ -z "${KERNEL_DAILY_AGENT_CMD:-}" ]; then
    cat >&2 <<EOF
未配置 KERNEL_DAILY_AGENT_CMD，已停在“分析前”阶段。
请由 Agent 读取：
  $prompt
并把完整分析写入：
  $report
随后运行：
  $DIR/run_daily.sh finish
EOF
    exit 2
  fi
  mkdir -p "$(dirname "$report")"
  KERNEL_DAILY_PROMPT="$prompt" KERNEL_DAILY_REPORT="$report" \
    bash -lc "$KERNEL_DAILY_AGENT_CMD" < "$prompt" > "$report"
  [ -s "$report" ] || { echo "Agent 未生成报告：$report" >&2; exit 3; }
}

finish() {
  local report
  report="$(jq -r '.report_path' "$STATE/current-target.json")"
  python3 "$PY" archive --report "$report"
  python3 "$PY" publish --report "$report"
}

case "${1:-run}" in
  prepare) prepare ;;
  agent) agent ;;
  finish) finish ;;
  publish)
    report="$(jq -r '.report_path' "$STATE/current-target.json")"
    python3 "$PY" publish --report "$report"
    ;;
  run)
    prepare
    agent
    finish
    ;;
  status)
    python3 "$PY" status
    ;;
  source)
    "$DIR/prepare_source.sh"
    ;;
  *)
    echo "usage: $0 {prepare|agent|finish|publish|run|status|source}" >&2
    exit 1
    ;;
esac
