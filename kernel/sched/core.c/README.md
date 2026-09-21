Task Switch
========================================

ARM
----------------------------------------

### __switch_to

https://github.com/novelinux/linux-4.x.y/blob/master/arch/arm/kernel/entry-armv.S/__switch_to.md

Pick Next Task
----------------------------------------

### pick_next_task

在给定 CPU 的运行队列上，按调度类优先级（stop → dl → rt → fair → idle）选出下一个运行的任务。
包含 CFS 快速路径优化与 RETRY_TASK 重入机制。

https://github.com/novelinux/linux-4.x.y/blob/master/kernel/sched/core.c/pick_next_task.md
