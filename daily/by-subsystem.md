# 每日内核源码学习 — 按子系统分类索引

> 按子系统分组的函数/结构分析索引。累计 825 条。

## fs（文件系统，含 VFS / epoll / ext4 等）

| 日期 | 源文件 | 函数/结构 | 功能摘要 | 分析笔记 |
|------|--------|-----------|----------|----------|
| 2026-08-28 | fs/eventpoll.c | `ep_insert` | epoll_ctl(EPOLL_CTL_ADD) 核心实现：分配 epitem、注册 poll 回调、插入红黑树与就绪链，处理嵌套拓扑检查与即时就绪唤醒 | [日期归档](../2026/08/2026-08-28/fs_ep_insert.md) / [就地索引](../../fs/eventpoll.c/ep_insert.md) |
| （历史条目见各子目录 README） | — | — | fs/namei.c, fs/exec.c, fs/read_write.c, fs/ext4/* 等 200+ 项 | 请见 [/workspace/fs/](../../fs/) 下各子目录 README.md |

### fs 子系统学习建议路线
1. VFS 框架 → `open.c` / `namei.c` / `inode.c` / `file_table.c` / `dcache.c` / `super.c` / `mount/namespace.c`
2. 进程映像 → `exec.c` / `binfmt_elf.c`
3. 读写路径 → `read_write.c` / `filemap.c`（页缓存） / `buffer.c` / `direct-io`
4. **IO 多路复用（本日新增区域）** → **eventpoll.c (epoll)** / select.c / aio.c
5. 管道/FIFO → pipe.c
6. 文件控制 → fcntl.c / ioctl.c / locks.c
7. 具体文件系统 → ext4 / ramfs / f2fs / fuse / proc …

---

## mm（内存管理）

mm/ 已分析 224 项，覆盖页分配器 (page_alloc.c)、slab 分配器、页表处理 (memory.c)、缺页中断、mmap/brk、vmalloc、readahead、memblock、kswapd 等。详见 [/workspace/mm/](../../mm/)。

## kernel / kernel/sched（核心与调度）

kernel/ 下已分析 80 项，sched/core.c 中进程主调度循环 `__schedule`、上下文切换、唤醒路径 `try_to_wake_up`、调度器滴答等已覆盖。workqueue、fork、kthread、pid、nsproxy、cgroup 等均有分析。详见 [/workspace/kernel/](../../kernel/)。

## include（核心头文件结构）

include/linux/ 下 182 项，覆盖 `struct page`、`struct mm_struct`、`struct vm_area_struct`、`struct task_struct` 相关字段、`struct mutex`、cpumask/nodemask、memblock 等。详见 [/workspace/include/](../../include/)。

## arch（架构相关，arm/arm64）

arm/ 及 arm64/mm 下 101 项，覆盖页表宏、fixmap、内存布局等。详见 [/workspace/arch/](../../arch/)。

## init（启动流程）

start_kernel → rest_init → kernel_init → do_initcalls 等 23 项已分析。详见 [/workspace/init/](../../init/)。

## 其余子系统（较少覆盖）
- lib/: 4 项（iov_iter.c 等） → [/workspace/lib/](../../lib/)
- ipc/: 1 项 → [/workspace/ipc/](../../ipc/)
- net/: 1 项 → [/workspace/net/](../../net/)
- block/、security/、**drivers/**：工作区已有目录布局但待大量分析，后续每日任务将优先补充。
