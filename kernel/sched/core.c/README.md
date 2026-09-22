Task Switch
========================================

ARM
----------------------------------------

### __switch_to

https://github.com/novelinux/linux-4.x.y/blob/master/arch/arm/kernel/entry-armv.S/__switch_to.md

函数分析索引
----------------------------------------

| 函数 | 一句话功能 | 分析笔记 | 日期 |
|------|-----------|----------|------|
| `__cond_resched_softirq` | 软中断禁用上下文中的自愿重新调度入口，先开 bh → 调度 → 再关 bh | [__cond_resched_softirq.md](./__cond_resched_softirq.md) | 2026-09-23 |
