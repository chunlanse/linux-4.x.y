#!/usr/bin/env bash
# 每日内核源码分析 - 飞书推送脚本
# 用法: push_feishu.sh <分析笔记.md 的相对路径(相对 /workspace)>
# 依赖: lark-cli (用户身份, 已配置外部凭证)
set -euo pipefail

# 推送目标: 内部 P2P 会话("赵德超" 个人单聊)。
# 注意: 当前租户策略禁止用户身份向 external=true 的群聊发消息,
# 故使用内部会话; 如后续开通外部群权限, 修改此处 CHAT_ID 即可。
CHAT_ID="${KERNEL_DAILY_CHAT_ID:-oc_b6b08e4754c49d68a85f5e11326c2cad}"

WORKSPACE="/workspace"
cd "$WORKSPACE"

MD_REL="${1:?用法: $0 <分析笔记.md 相对 /workspace 的路径>}"
MD_PATH="$WORKSPACE/$MD_REL"
[ -f "$MD_PATH" ] || { echo "文件不存在: $MD_PATH" >&2; exit 1; }

# ---- 从笔记提取元信息 ----
TITLE=$(grep -m1 '^# ' "$MD_PATH" | sed 's/^# //')
DATE=$(grep -m1 '^\- \*\*日期\*\*' "$MD_PATH" | sed 's/.*：//')
SUBSYS=$(grep -m1 '^\- \*\*子系统\*\*' "$MD_PATH" | sed 's/.*：//')
SRC=$(grep -m1 '^\- \*\*源文件\*\*' "$MD_PATH" | sed 's/.*：//')
# 提取 "## 1. 功能作用" 与 "## 2." 之间的正文(去空行, 取前 6 行)
FUNC=$(awk '/^## 1\. 功能作用/{f=1;next} /^## 2\./{f=0} f' "$MD_PATH" | grep -v '^$' | head -6)

# 读取进度统计
STATS="$WORKSPACE/daily/progress-stats.json"
TOTAL=$(grep -m1 '"total"' "$STATS" 2>/dev/null | sed 's/[^0-9]//g' || echo "?")

# ---- 构造摘要消息(heredoc 带引号分隔符, 禁用 shell 扩展以保护反引号) ----
MSG=$(cat <<EOF
📚 ${TITLE}

📅 日期：${DATE}
🧩 子系统：${SUBSYS}
📄 源文件：${SRC}

【功能作用】
${FUNC}

———
📁 完整分析（含数据结构 / 流程图 / 调用关系）见随附文件
📊 累计学习：${TOTAL} 篇
EOF
)

echo ">> 发送分析摘要到飞书会话 ${CHAT_ID}"
lark-cli im +messages-send \
  --chat-id "$CHAT_ID" \
  --markdown "$MSG" \
  --idempotency-key "kernel-daily-${DATE}-$(basename "$MD_PATH" .md | tr '_/' '--')" \
  >/tmp/lark_push_summary.json

echo ">> 发送完整笔记文件附件: $MD_REL"
lark-cli im +messages-send \
  --chat-id "$CHAT_ID" \
  --file "$MD_REL" \
  >/tmp/lark_push_file.json

echo ">> 推送完成"
cat /tmp/lark_push_summary.json | head -c 400; echo
