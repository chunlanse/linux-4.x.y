Task Switch
========================================

ARM
----------------------------------------

### __switch_to

https://github.com/novelinux/linux-4.x.y/blob/master/arch/arm/kernel/entry-armv.S/__switch_to.md

Preemption
----------------------------------------

| 函数 | 一句话功能摘要 | 分析笔记 | 日期 |
|------|----------------|----------|------|
| preempt_schedule_common | 内核抢占的公共执行体，循环调用 `__schedule(true)` 直到不再需要调度 | [分析笔记](./preempt_schedule_common.md) | 2026-11-06 |
