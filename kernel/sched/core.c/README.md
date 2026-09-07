Task Switch
========================================

ARM
----------------------------------------

### __switch_to

https://github.com/novelinux/linux-4.x.y/blob/master/arch/arm/kernel/entry-armv.S/__switch_to.md

Wakeup Preemption
----------------------------------------

### check_preempt_curr

调度器"唤醒抢占"机制的总入口。当一个任务变为 runnable 并入队后，判断它是否应抢占当前运行任务。
同类比较交给各调度类的 `check_preempt_curr` 方法；跨类比较依据调度类全局优先级链表（stop → dl → rt → fair → idle）裁决。

https://github.com/novelinux/linux-4.x.y/blob/master/kernel/sched/core.c/check_preempt_curr.md
