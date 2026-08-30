# 每日内核源码分析索引（按子系统分类）

本索引按内核子系统分类组织每日学习条目，便于针对特定模块查阅。

---

## kernel/sched（进程调度 / 调度器负载均衡 / CFS / RT / Deadline）

| 日期 | 函数 / 关键段 | 所在文件 | 一句话功能摘要 | 分析笔记 |
|------|----------------|----------|----------------|----------|
| 2026-08-31 | `load_balance` | kernel/sched/fair.c:8709-8981 | SMP 调度域内实际执行跨 CPU 任务迁移（pull）的核心函数，含 active_balance 强推路径 | [kernel_sched_load_balance.md](../2026/08/2026-08-31/kernel_sched_load_balance.md) |

---

## mm/（内存管理：页分配/虚拟内存/Slab/回收/高址映射等）

（子系统就地分析笔记位于 `/workspace/mm/` 下各源文件目录中，已累计 227+ 篇）

---

## fs/（文件系统：VFS/路径解析/页缓存/挂载/Exec 等）

（子系统就地分析笔记位于 `/workspace/fs/` 下各源文件目录中，已累计 209+ 篇）

---

## include/linux（核心数据结构 / API 头文件定义）

（子系统就地分析笔记位于 `/workspace/include/linux/` 下各头文件目录中，已累计 158+ 篇）

---

## kernel/（其余内核核心：fork/工作队列/pid/命名空间/参数解析 等）

（子系统就地分析笔记位于 `/workspace/kernel/` 下各源文件目录中，已累计 67+ 篇；sched 子系统独立拆分见上方表格）

---

## init/、block/、ipc/、lib/、security/、drivers/（其他子系统）

共计 29+ 篇分析笔记，详见各子系统就地目录。
