# kernel/sched/fair.c 分析笔记

CFS（Completely Fair Scheduler，完全公平调度器）的实现文件。

## 已分析函数索引

| 函数名 | 一句话功能摘要 | 分析笔记 | 分析日期 |
|--------|----------------|----------|----------|
| `place_entity` | 决定调度实体入队时 vruntime 初始位置（新任务赊账 + 睡眠者补偿 + max 兜底） | [place_entity.md](./place_entity.md) | 2026-09-12 |

## 待分析核心函数（CFS 核心路径）

- `update_curr` — 更新当前任务 vruntime（CFS 公平性基础）
- `enqueue_task_fair` / `dequeue_task_fair` — 任务入队/出队入口
- `pick_next_task_fair` — 选择下一个运行任务（核心调度决策）
- `check_preempt_wakeup` — 唤醒抢占检查
- `entity_tick` / `task_tick_fair` — 周期性调度 tick
- `pick_next_entity` / `set_next_entity` / `put_prev_entity` — 实体切换
