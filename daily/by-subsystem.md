# 按子系统分类索引

## kernel/sched（调度器）

| 函数/结构 | 源文件 | 一句话功能摘要 | 分析笔记 | 日期 |
|-----------|--------|----------------|----------|------|
| `pick_next_entity` | kernel/sched/fair.c | CFS 从红黑树挑选下一个运行实体，兼顾 next/last/skip 伙伴 | [笔记](../kernel/sched/fair.c/pick_next_entity.md) | 2026-09-10 |
