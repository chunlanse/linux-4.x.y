# 每日内核源码学习 - 按子系统分类索引

## kernel/sched（进程调度）

| 日期 | 函数 / 结构 | 所在文件 | 摘要 | 笔记 |
|------|-------------|----------|------|------|
| 2026-09-01 | `pick_next_task_fair` | kernel/sched/fair.c:6769 | CFS 调度入口：选 vruntime 最小实体，支持组调度层级与增量优化 | [笔记](../2026/09/2026-09-01/kernel_sched_pick_next_task_fair.md) |

> 其他已就地归档的调度子系统分析见 `/workspace/kernel/sched/` 目录（core.c、sched.h 等）。

## mm（内存管理）

> 就地归档位于 `/workspace/mm/`。累计 230+ 篇分析，覆盖 page_alloc.c（伙伴系统）、slab.c（SLAB分配器）、vmalloc.c、mmap.c、memory.c（缺页）、filemap.c（页缓存）、memblock.c 等核心文件。

## fs（文件系统）

> 就地归档位于 `/workspace/fs/`。累计 220+ 篇分析，覆盖 VFS（namei.c/exec.c/open.c/dcache.c/inode.c/...）、ELF 加载（binfmt_elf.c）、ext2/ext4/f2fs/fuse 等。

## kernel（核心）

> 就地归档位于 `/workspace/kernel/`。累计 90 篇：fork.c（进程创建）、workqueue.c、pid.c、kthread.c、locking/ 等。

## init（启动初始化）

> 就地归档位于 `/workspace/init/`。23 篇：start_kernel 全流程、initcalls、rootfs 挂载等。

## include/uapi（头文件关键结构）

> 就地归档位于 `/workspace/include/linux/`。180+ 篇：struct page、struct task_struct、struct inode、struct mm_struct、gfp.h 标志位、mmzone.h 节点/zone 结构等。

## drivers（设备驱动） - TODO

优先下一步覆盖方向。待补充：drivers/block、drivers/base、drivers/char、drivers/pci 等核心驱动子系统。

## lib / ipc / block / security / net

起步阶段，后续逐步扩展。
