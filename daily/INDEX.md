# 每日内核源码学习索引 INDEX

按日期倒序维护。每一条目对应一次完整分析。

| 日期 | 子系统 | 函数 / 结构 | 一句话摘要 | 分析笔记 |
|------|--------|-------------|------------|----------|
| 2026-09-01 | kernel/sched | `pick_next_task_fair` | CFS 调度器核心入口：从红黑树选最小 vruntime 任务，支持组调度层级下钻与增量 put/set 优化 | [kernel_sched_pick_next_task_fair.md](./2026/09/2026-09-01/kernel_sched_pick_next_task_fair.md) |
