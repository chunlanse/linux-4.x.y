# 内核源码分析 · 按子系统索引

> 与本仓库子系统目录结构一致的就地归档索引。每条追加到对应子系统下。

## kernel/sched

| 函数 / 代码段 | 一句话功能 | 就地归档 | 日期 |
|--------------|-----------|---------|------|
| `__schedule` | 主调度函数，完成进程切换 | [core.c/__schedule.md](../kernel/sched/core.c/__schedule.md) | 历史归档 |
| `context_switch` | 执行上下文切换（mm 切换 + switch_to） | [core.c/context_switch.md](../kernel/sched/core.c/context_switch.md) | 历史归档 |
| `pick_next_task_fair` | CFS 选出下一个运行任务的入口，红黑树最左 + 伙伴策略 + 组层级下钻 | [fair.c/pick_next_task_fair.md](../kernel/sched/fair.c/pick_next_task_fair.md) | 2026-09-28 |
