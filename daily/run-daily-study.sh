#!/usr/bin/env bash
# 每日内核源码学习 —— 自动化前置流水线（确定性部分）
#
# 职责：
#   1. 确保 linux-4.x.y 内核源码就绪（缺省浅克隆 v4.19，只取核心子系统）；
#   2. 扫描 workspace 已分析笔记，排除重复；
#   3. 按权重随机选题并抽取源码片段，生成 daily/.state/selection-<date>.json；
#   4. 生成 daily/.state/pending-task.md，供 Agent 直接执行分析、归档与飞书推送。
#
# 定时触发（每天 09:00）：
#   0 9 * * * cd /workspace && ./daily/run-daily-study.sh >> daily/.state/cron.log 2>&1
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
KERNEL_SRC_PATH="${KERNEL_SRC_PATH:-$HOME/linux-stable}"
KERNEL_TAG="${KERNEL_TAG:-v4.19}"
DATE="${1:-$(date +%F)}"
SPARSE_DIRS="include mm kernel/sched kernel/locking drivers/tty drivers/base drivers/char drivers/iommu fs lib init virt/kvm kernel/rcu kernel/irq"

if [ ! -d "$KERNEL_SRC_PATH/mm" ]; then
  echo "[*] 未找到内核源码，开始浅克隆 $KERNEL_TAG -> $KERNEL_SRC_PATH"
  rm -rf "$KERNEL_SRC_PATH"
  git clone --depth 1 --branch "$KERNEL_TAG" --filter=blob:none --sparse \
    https://github.com/torvalds/linux.git "$KERNEL_SRC_PATH"
  # shellcheck disable=SC2086
  git -C "$KERNEL_SRC_PATH" sparse-checkout set $SPARSE_DIRS
fi

cd "$WORKSPACE"
echo "[*] 选题中（日期 $DATE）..."
KERNEL_SRC_PATH="$KERNEL_SRC_PATH" python3 daily/scripts/select_target.py --date "$DATE"

python3 - "$DATE" <<'PY'
import json
import pathlib
import sys

day = sys.argv[1]
data = json.loads(pathlib.Path(f"daily/.state/selection-{day}.json").read_text())
y, m, d = day.split("-")
src_dir = data["file"].rsplit("/", 1)[0] if "/" in data["file"] else data["subsystem"]
task = f"""# 待分析任务 {day}

- 目标：`{data['name']}`
- 位置：{data['file']}:{data['line_start']}-{data['line_end']}（定义行 {data['def_line']}）
- 子系统：{data['subsystem']}
- 导出符号：{data['exported']} / static：{data['static']} / 全仓库出现次数：{data['callers']}

## 执行要求

按 linux-kernel-daily-study 模板输出中文解读：功能作用、关键数据结构、核心逻辑流程图（Mermaid）、
调用关系（调用者/被调用者/调用关系图）、易错点与设计权衡。

归档位置：
- `daily/{y}/{m}/{day}/{data['subsystem']}_{data['name']}.md`
- `{src_dir}/{data['name']}.md`
- 更新 `daily/INDEX.md`、`daily/by-subsystem.md`、`daily/progress-stats.json`

完成后把摘要与飞书文档链接推送到飞书。

## 源码片段

```c
{data['snippet']}
```
"""
pathlib.Path("daily/.state/pending-task.md").write_text(task)
print(f"[*] 待分析任务已写入 daily/.state/pending-task.md")
PY

if [ -f daily/progress-stats.json ]; then
  python3 - <<'PY'
import json
import pathlib
s = json.loads(pathlib.Path("daily/progress-stats.json").read_text())
print(f"[*] 累计：每日分析 {s['daily_total']} 篇；workspace 笔记 {s['workspace_notes_total']} 篇")
print("[*] 子系统分布：" + ", ".join(f"{k}={v}" for k, v in s["by_subsystem"].items()))
PY
fi

echo "[*] 完成。下一步：Agent 读取 daily/.state/pending-task.md 执行分析与推送。"
