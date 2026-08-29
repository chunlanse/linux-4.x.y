# kernel/sched/fair.c — CFS 调度器核心函数分析索引

本目录汇总 Linux 4.x CFS (Completely Fair Scheduler) 核心源码的深度分析笔记。
源文件：`kernel/sched/fair.c` (Linux v4.19)

| 函数/结构名 | 一句话功能摘要 | 分析笔记 | 分析日期 |
|-------------|---------------|----------|----------|
| `update_curr` | CFS 核心统计更新函数：累计当前运行实体的物理运行时间，按权重折算推进 vruntime，维护 cfs_rq 基准 min_vruntime | [update_curr.md](./update_curr.md) | 2026-08-30 |
