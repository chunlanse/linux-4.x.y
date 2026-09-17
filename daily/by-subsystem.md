# 按子系统分类的学习索引

## kernel/sched（调度器）

| 函数 / 结构 | 源文件 | 一句话摘要 | 日期 | 笔记 |
|-------------|--------|------------|------|------|
| `update_curr` | kernel/sched/fair.c:803 | CFS 核心：真实时间→vruntime 加权换算 | 2026-09-18 | [笔记](./2026/09/2026-09-18/kernel_sched_update_curr.md) |

> 历史分析（工作区已有）：`__schedule`、`context_switch`、`scheduler_tick`、`try_to_wake_up`、`wake_up_process`、`sched_fork`、`effective_prio`、`set_load_weight`、`ttwu_*` 系列等，见 [kernel/sched/](../kernel/sched/)。
