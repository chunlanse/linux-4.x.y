# kernel/sched/fair.c — CFS 调度器核心实现

> Linux v4.9 - `kernel/sched/fair.c` 是 CFS（Completely Fair Scheduler）的主体实现文件，定义了 `fair_sched_class` 所使用的全部回调（`enqueue_task_fair` / `dequeue_task_fair` / `pick_next_task_fair` / `task_tick_fair` / `task_fork_fair` / `yield_task_fair` 等）以及围绕 `vruntime` 与红黑树展开的公平性算法。

## 已分析函数索引

| 函数 | 一句话功能摘要 | 笔记 | 日期 |
|------|----------------|------|------|
| `update_curr` | CFS 心跳函数：结算当前 sched_entity 的物理 / 虚拟运行时间，更新 min_vruntime，是所有调度决策前的前置记账。 | [update_curr.md](./update_curr.md) | 2026-09-16 |
