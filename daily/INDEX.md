# 每日内核源码分析 — 总索引 (INDEX)

按日期倒序组织的每日学习记录。

| 日期 | 子系统 | 函数/结构 | 一句话摘要 | 归档链接 |
|------|--------|-----------|-----------|----------|
| 2026-08-30 | kernel/sched (CFS) | `update_curr` | CFS调度器核心统计更新函数：累计当前运行实体的物理运行时间，按权重折算推进 vruntime，维护 cfs_rq 基准 min_vruntime | [2026-08-30/kernel_sched_update_curr.md](./2026/08/2026-08-30/kernel_sched_update_curr.md) |
