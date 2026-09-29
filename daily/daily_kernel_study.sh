#!/usr/bin/env bash
# daily_kernel_study.sh
# 每日 Linux 内核源码学习工作流
# 1. 从 /tmp/linux-4.19 选取未被分析的核心函数
# 2. 输出按 skill 模板的中文解读
# 3. 双写归档到 /workspace/daily 与子系统就地目录
# 4. （可选）推送摘要到飞书
#
# 用法：
#   LARK_CHAT_ID=oc_xxx ./daily_kernel_study.sh           # 完整流程（含飞书推送）
#   ./daily_kernel_study.sh --no-lark                      # 仅本地归档
#   TARGET=resched_curr ./daily_kernel_study.sh            # 指定目标函数
#   ./daily_kernel_study.sh --list                         # 查看候选项

set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
KERNEL_SRC="${KERNEL_SRC:-/tmp/linux-4.19}"
DAILY_ROOT="${DAILY_ROOT:-$WORKSPACE/daily}"
LARK_CHAT_ID="${LARK_CHAT_ID:-}"
SUBSYSTEM_HINT="${SUBSYSTEM_HINT:-}"   # kernel/sched, mm, drivers ...

DATE="$(date +%Y-%m-%d)"
YYYY="$(date +%Y)"
MM="$(date +%m)"

mkdir -p "$DAILY_ROOT/$YYYY/$MM/$DATE"

log() { printf '\033[1;34m[daily]\033[0m %s\n' "$*"; }

# ------------------------------------------------------------
# 1. 扫描已分析过的函数集合
# ------------------------------------------------------------
build_analyzed_set() {
    log "扫描已分析函数 (workspace=$WORKSPACE) ..."
    ANALYZED_FILE="$(mktemp)"
    # 模式 A：{子系统}/{源文件}/<func>.md
    find "$WORKSPACE" -type f -name '*.md' \
        \( -path '*/core.c/*.md' -o -path '*/page_alloc.c/*.md' -o \
           -path '*/sched.h/*.md' -o -path '*/fair.c/*.md' -o \
           -path '*/rt.c/*.md' -o -path '*/filemap.c/*.md' -o \
           -path '*/mmap.c/*.md' -o -path '*/vmalloc.c/*.md' -o \
           -path '*/slab.c/*.md' \) 2>/dev/null \
        | awk -F/ '{print $NF}' | sed 's/\.md$//' > "$ANALYZED_FILE" || true
    cat "$DAILY_ROOT/INDEX.md" 2>/dev/null \
        | grep -oE '`[a-zA-Z_][a-zA-Z0-9_]*`' | tr -d '`' >> "$ANALYZED_FILE" || true
    sort -u "$ANALYZED_FILE" -o "$ANALYZED_FILE"
    log "已分析函数数量: $(wc -l < "$ANALYZED_FILE")"
}

# ------------------------------------------------------------
# 2. 选取目标函数
# ------------------------------------------------------------
SUBSYSTEM_ORDER=("kernel/sched" "mm" "drivers" "fs" "kernel" "ipc" "net" "block")

pick_target() {
    if [[ -n "${TARGET:-}" ]]; then
        log "使用指定目标: $TARGET"
        echo "$TARGET"; return 0
    fi
    log "按加权优先级顺序扫描子系统候选..."
    for sub in "${SUBSYSTEM_ORDER[@]}"; do
        [[ -d "$KERNEL_SRC/$sub" ]] || continue
        # 简化版：取每个 .c 中第一个非 static 的全局函数
        candidate="$(
            for f in "$KERNEL_SRC/$sub"/*.c; do
                [[ -f "$f" ]] || continue
                grep -nE '^[a-zA-Z_][a-zA-Z0-9_ \*]+\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(' "$f" 2>/dev/null \
                    | grep -vE '^\s*[0-9]+:\s*static' \
                    | head -1
            done | shuf -n1
        )"
        [[ -n "$candidate" ]] || continue
        func_name="$(echo "$candidate" | sed -E 's/.*\s([a-zA-Z_][a-zA-Z0-9_]*)\s*\(.*/\1/')"
        if grep -qx "$func_name" "$ANALYZED_FILE"; then
            log "跳过已分析: $func_name"
            continue
        fi
        log "命中: $func_name"
        echo "$func_name"; return 0
    done
    log "所有候选均已分析，请扩展或换内核版本"
    return 1
}

# ------------------------------------------------------------
# 3. 调用大模型生成中文解读（此处为占位；实际由 Agent 完成）
# ------------------------------------------------------------
generate_analysis() {
    local target="$1"
    local out="$DAILY_ROOT/$YYYY/$MM/$DATE/${SUBSYSTEM_HINT:-sched}_${target}.md"
    log "生成分析文档 → $out"
    cat > "$out" <<HEADER
# 每日内核源码分析：$target

- **日期**：$DATE
- **子系统**：${SUBSYSTEM_HINT:-kernel/sched}
- **类型**：function

## 1. 功能作用

（由 Agent 生成）

## 2. 关键数据结构

（由 Agent 生成）

## 3. 核心逻辑流程图

\`\`\`mermaid
flowchart TD
  A[入口] --> B[结束]
\`\`\`

## 4. 调用关系

（由 Agent 生成）

## 5. 易错点 / 边界场景

（由 Agent 生成）

## 附：核心源码片段

\`\`\`c
// 占位，请由 Agent 填入 $target 的源码片段
\`\`\`
HEADER
    echo "$out"
}

# ------------------------------------------------------------
# 4. 更新索引
# ------------------------------------------------------------
update_index() {
    local target="$1"
    local link="$2"
    local sub="${SUBSYSTEM_HINT:-kernel/sched}"
    log "更新 INDEX 与 by-subsystem..."
    {
        echo "| $DATE | $sub | \`$target\` | [link](./$YYYY/$MM/$DATE/${link##*/}) |"
        if [[ -f "$DAILY_ROOT/INDEX.md" ]]; then
            head -n 2 "$DAILY_ROOT/INDEX.md"
            tail -n +3 "$DAILY_ROOT/INDEX.md" | grep -v "^|$DATE\|^$"
        fi
    } > "$DAILY_ROOT/INDEX.md.tmp" && mv "$DAILY_ROOT/INDEX.md.tmp" "$DAILY_ROOT/INDEX.md"
}

# ------------------------------------------------------------
# 5. 推送飞书（如已配置）
# ------------------------------------------------------------
push_lark() {
    local target="$1"
    local link="$2"
    [[ -n "$LARK_CHAT_ID" ]] || { log "未配置 LARK_CHAT_ID，跳过推送"; return 0; }
    local body="【每日内核学习 $DATE】\n目标: $target\n子系统: ${SUBSYSTEM_HINT:-kernel/sched}\n本地归档: $link"
    log "推送飞书 → $LARK_CHAT_ID"
    lark-cli im +messages-send \
        --as bot \
        --chat-id "$LARK_CHAT_ID" \
        --msg-type text \
        --content "$(printf '%s' "$body")" \
        --markdown "$(printf '%s' "$body")" || log "飞书推送失败（请确认 LARK_CHAT_ID / 权限）"
}

# ------------------------------------------------------------
# main
# ------------------------------------------------------------
case "${1:-run}" in
    --list) build_analyzed_set; cat "$ANALYZED_FILE"; exit 0 ;;
    --help|-h) sed -n '2,15p' "$0"; exit 0 ;;
    --no-lark) LARK_CHAT_ID="" ;;
esac

build_analyzed_set
target="$(pick_target)"
[[ -n "$target" ]] || { log "未找到目标"; exit 1; }

# 就地子系统归档（subsystem 在 workspace 中的同名目录）
sub_dir="$WORKSPACE/${SUBSYSTEM_HINT:-kernel/sched}"
src_basename="${SRC_FILE:-core.c}"
mkdir -p "$sub_dir/$src_basename"
local_doc="$sub_dir/$src_basename/${target}.md"

main_doc="$(generate_analysis "$target")"
# 就地文件仅放摘要与回链
cat > "$local_doc" <<LOCAL
# $target

- **日期**：$DATE
- **子系统**：${SUBSYSTEM_HINT:-kernel/sched}
- **完整分析**：[main](${main_doc#$WORKSPACE/})

## 一句话作用

（由 Agent 补全）
LOCAL

update_index "$target" "$main_doc"
push_lark "$target" "$main_doc"

log "完成 ✓ 主归档: $main_doc"
log "完成 ✓ 子系统就地: $local_doc"