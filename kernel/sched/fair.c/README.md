# kernel/sched/fair.c 分析索引

CFS（Completely Fair Scheduler）调度器实现文件。

| 函数 | 一句话功能摘要 | 分析笔记 | 日期 |
|------|----------------|----------|------|
| `pick_next_entity` | CFS 从红黑树挑选下一个运行实体，兼顾 next/last/skip 伙伴指针 | [pick_next_entity.md](./pick_next_entity.md) | 2026-09-10 |
