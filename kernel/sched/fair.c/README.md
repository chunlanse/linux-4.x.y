# kernel/sched/fair.c 分析笔记

CFS（Completely Fair Scheduler）调度器实现文件。

| 函数名 | 功能摘要 | 分析笔记 | 分析日期 |
|--------|----------|----------|----------|
| pick_next_task_fair | CFS 选取下一个可运行任务的核心入口，含组调度层级选择与带宽限流 | [pick_next_task_fair.md](./pick_next_task_fair.md) | 2026-09-11 |
