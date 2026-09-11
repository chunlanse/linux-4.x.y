# 每日内核源码分析 - 按子系统索引

## kernel/sched（进程调度）

| 日期 | 函数 / 结构 | 源文件 | 一句话摘要 | 链接 |
|------|-------------|--------|------------|------|
| 2026-09-12 | `place_entity` | kernel/sched/fair.c | CFS 调度实体入队时 vruntime 初始位置计算（新任务赊账 + 睡眠者补偿） | [笔记](../2026/09/2026-09-12/kernel_sched_place_entity.md) |

---

*其余子系统（mm/、fs/、kernel/ 等）的历史分析见 workspace 对应子系统目录。*
