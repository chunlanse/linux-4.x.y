Task Switch
========================================

ARM
----------------------------------------

### __switch_to

https://github.com/novelinux/linux-4.x.y/blob/master/arch/arm/kernel/entry-armv.S/__switch_to.md

## 已分析函数索引

| 函数名 | 功能摘要 | 分析笔记 | 分析日期 |
|--------|----------|----------|----------|
| set_user_nice | 设置任务 nice 值，更新 static_prio 与 CFS 负载权重 | [分析笔记](./set_user_nice.md) | 2026-09-06 |
| __schedule | 主调度入口，选择下一个运行的任务 | [分析笔记](./__schedule.md) | - |
| context_switch | 进程上下文切换 | [分析笔记](./context_switch.md) | - |
| try_to_wake_up | 唤醒任务并加入运行队列 | [分析笔记](./try_to_wake_up.md) | - |
| wake_up_process | 唤醒指定进程 | [分析笔记](./wake_up_process.md) | - |
| scheduler_tick | 周期性调度 tick，更新任务运行时间 | [分析笔记](./scheduler_tick.md) | - |
