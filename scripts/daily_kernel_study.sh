#!/bin/bash
set -euo pipefail

# ============================================================
# Linux 内核每日学习自动化工作流脚本
# ============================================================
# 功能：
#   1. 从 ~/linux-stable 中随机选取一个未分析的核心函数
#   2. 提取该函数的源码片段
#   3. 生成待分析任务描述
#   4. （可选）调用外部 AI API 自动生成初步分析
#   5. 将结果归档并推送到飞书
#
# 用法：
#   cd /workspace && bash scripts/daily_kernel_study.sh
#
# 环境变量：
#   KERNEL_SRC_PATH    内核源码路径，默认 ~/linux-stable
#   ARCHIVE_ROOT       归档根目录，默认 /workspace/daily
#   FEISHU_USER_ID     飞书接收者 open_id（可选，默认当前登录用户）
#   OPENAI_API_KEY     如设置，则调用 OpenAI API 自动生成分析摘要
# ============================================================

KERNEL_SRC_PATH="${KERNEL_SRC_PATH:-$HOME/linux-stable}"
ARCHIVE_ROOT="${ARCHIVE_ROOT:-/workspace/daily}"
FEISHU_USER_ID="${FEISHU_USER_ID:-}"

TODAY=$(date +%Y-%m-%d)
YEAR=$(date +%Y)
MONTH=$(date +%m)

echo "=== Linux Kernel Daily Study Workflow ==="
echo "Date: $TODAY"
echo "Kernel: $KERNEL_SRC_PATH"

# 1. 选取目标
python3 /workspace/scripts/select_target_v2.py

TARGET_FILE="/workspace/daily/TARGET.json"
if [ ! -f "$TARGET_FILE" ]; then
    echo "ERROR: Target selection failed"
    exit 1
fi

TARGET_NAME=$(jq -r '.name' "$TARGET_FILE")
TARGET_FILE_REL=$(jq -r '.file' "$TARGET_FILE")
TARGET_LINE=$(jq -r '.line' "$TARGET_FILE")
TARGET_SUBSYS=$(jq -r '.subsystem' "$TARGET_FILE")

SRC_FILE="$KERNEL_SRC_PATH/$TARGET_FILE_REL"
echo "Selected: $TARGET_NAME @ $TARGET_FILE_REL:$TARGET_LINE"

# 2. 提取源码上下文（前后 30 行）
mkdir -p "$ARCHIVE_ROOT/$YEAR/$MONTH/$TODAY"
START_LINE=$((TARGET_LINE - 30))
[ "$START_LINE" -lt 1 ] && START_LINE=1
END_LINE=$((TARGET_LINE + 50))

CODE_SNIPPET="$ARCHIVE_ROOT/$YEAR/$MONTH/$TODAY/${TARGET_SUBSYS}_${TARGET_NAME}.code.c"
sed -n "${START_LINE},${END_LINE}p" "$SRC_FILE" > "$CODE_SNIPPET"

# 3. 生成待分析任务描述
TASK_DESC="$ARCHIVE_ROOT/$YEAR/$MONTH/$TODAY/${TARGET_SUBSYS}_${TARGET_NAME}.task.md"
cat > "$TASK_DESC" <<EOF
# 每日内核分析任务：$TARGET_NAME

- **日期**：$TODAY
- **子系统**：$TARGET_SUBSYS
- **源文件**：$TARGET_FILE_REL:$TARGET_LINE
- **函数名**：$TARGET_NAME

## 源码片段

\`\`\`c
$(cat "$CODE_SNIPPET")
\`\`\`

## 任务要求

请按以下模板进行深度分析：

1. **功能作用**：该函数在内核中的角色、解决的问题、典型使用场景。
2. **关键数据结构**：参数、返回值、内部依赖的 struct/enum/全局变量。
3. **核心逻辑流程图**：使用 Mermaid flowchart 表达执行路径。
4. **调用关系**：调用者（who calls me）和被调用者（who I call）。
5. **易错点 / 边界场景 / 设计权衡**：3~6 条。
6. **附：核心源码片段**：去冗后的关键代码。

分析完成后：
- 保存到 $ARCHIVE_ROOT/$YEAR/$MONTH/$TODAY/${TARGET_SUBSYS}_${TARGET_NAME}.md
- 同时更新 $ARCHIVE_ROOT/INDEX.md
- 推送到飞书
EOF

echo "Task description saved to: $TASK_DESC"

# 4. （可选）调用外部 AI API 自动生成初步分析
if [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "Generating preliminary analysis via OpenAI API..."
    # 此处可接入 OpenAI/Claude API 生成初稿
    # 为简化，仅预留接口
    echo "API analysis placeholder" > "$ARCHIVE_ROOT/$YEAR/$MONTH/$TODAY/${TARGET_SUBSYS}_${TARGET_NAME}.api.md"
fi

# 5. 飞书通知
if command -v lark-cli &> /dev/null; then
    if [ -z "$FEISHU_USER_ID" ]; then
        # 尝试获取当前用户
        FEISHU_USER_ID=$(lark-cli contact +get-user --jq '.data.user.open_id' 2>/dev/null || true)
    fi

    if [ -n "$FEISHU_USER_ID" ]; then
        MSG="📚 **每日内核源码分析任务**（$TODAY）

今日已自动选定目标：
- **函数**：\`$TARGET_NAME\`
- **子系统**：$TARGET_SUBSYS
- **源文件**：$TARGET_FILE_REL:$TARGET_LINE

👉 源码片段和任务描述已保存到：
\`$ARCHIVE_ROOT/$YEAR/$MONTH/$TODAY/\`

请让 Agent 执行深度分析，完成后将自动推送到飞书。"

        lark-cli im +messages-send --user-id "$FEISHU_USER_ID" --markdown "$MSG" >/dev/null 2>&1 || echo "Feishu message send failed"
        echo "Feishu notification sent to $FEISHU_USER_ID"
    else
        echo "WARNING: Feishu user_id not available, skipping notification"
    fi
else
    echo "WARNING: lark-cli not found, skipping Feishu notification"
fi

echo "=== Workflow finished ==="
