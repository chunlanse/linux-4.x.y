# kernel/sched/fair.c 分析笔记

CFS（Completely Fair Scheduler，完全公平调度器）的核心实现文件。主要包含：

1. **CFS 实体记账**：update_curr / calc_delta_fair / min_vruntime 维护
2. **入队/出队**：enqueue_task_fair / dequeue_task_fair
3. **任务选择**：pick_next_entity / set_next_entity / put_prev_entity 以及本文件核心入口 pick_next_task_fair
4. **调度 Tick**：task_tick_fair / entity_tick 驱动周期性抢占
5. **唤醒抢占检查**：check_preempt_wakeup + wakeup_preempt_entity
6. **Buddy 机制**：next_buddy / last_buddy / skip_buddy
7. **组调度**：FAIR_GROUP_SCHED 层级 cfs_rq 与 bandwidth 节流
8. **SMP 负载均衡**：load_balance_fair / idle_balance 等

## 已分析函数索引

| 函数名 | 功能摘要 | 分析笔记 | 日期 |
|--------|---------|----------|------|
| `pick_next_task_fair` | CFS 调度类入口：从红黑树选 vruntime 最小实体，层级下钻，支持增量路径优化 | [pick_next_task_fair.md](./pick_next_task_fair.md) | 2026-09-01 |
