Task Switch
========================================

ARM
----------------------------------------

### __switch_to

https://github.com/novelinux/linux-4.x.y/blob/master/arch/arm/kernel/entry-armv.S/__switch_to.md

Function Index
----------------------------------------

| 函数 | 一句话功能摘要 | 分析笔记 | 日期 |
|------|----------------|----------|------|
| `migration_call` | 调度器的 CPU 热插拔通知回调：CPU 上线时 rq 挂入 root domain，下线时强制迁空全部任务 | [分析笔记](./migration_call.md) | 2026-11-05 |
