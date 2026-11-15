Task Switch
========================================

ARM
----------------------------------------

### __switch_to

https://github.com/novelinux/linux-4.x.y/blob/master/arch/arm/kernel/entry-armv.S/__switch_to.md

User Nice
----------------------------------------

### set_user_nice

**[set_user_nice](./set_user_nice.md)** — 用户态 nice 值落到 CFS 权重（`se.load.weight`）的入口，按需出队/入队并触发抢占。

| 函数 | 摘要 | 分析笔记 | 日期 |
|------|------|----------|------|
| `set_user_nice` | 设置普通任务 nice 并更新 CFS 权重 | [分析笔记](./set_user_nice.md) | 2026-11-16 |
