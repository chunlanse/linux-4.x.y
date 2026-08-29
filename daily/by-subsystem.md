# 每日内核源码分析 — 按子系统索引

按子系统分类汇总所有已分析条目，便于纵向追踪某一模块的学习进度。

---

## mm/ (内存管理，241 篇)
> 物理页分配 (page_alloc.c)、伙伴系统、SLUB/SLAB/SLOB 分配器、缺页中断 (memory.c)、虚拟地址空间 mmap、vmalloc、页缓存 (filemap.c)、页面回写、kswapd 页面回收等。

---

## fs/ (文件系统，233 篇)
> VFS 框架 (namei.c/open.c/exec.c/read_write.c/super.c/dcache.c/inode.c)、ELF 加载 (binfmt_elf.c)、ext2/ext3/ext4 深度分析、ramfs/f2fs/fuse/jbd2/sdcardfs 等。

---

## include/ (通用头文件，194 篇)
> 核心数据结构与宏：`struct task_struct`、pid / nsproxy / fs_struct 命名空间、mmzone.h (NUMA 节点与 zone 结构)、slab 分配器 API、pid 命名空间、percpu 变量定义等。

---

## kernel/ (核心子系统，100 篇)
> 进程生命周期 (fork.c)、调度器框架 (core.c/sched.h/调度类)、**CFS 调度器 fair.c**、workqueue 工作队列、内核线程 kthread、RCU/锁原语、命名空间 nsproxy、PID 管理、启动流程 init/main.c 等。

### kernel/sched 子目录条目
| 日期 | 函数 | 摘要 |
|------|------|------|
| 2026-08-30 | [update_curr](../2026/08/2026-08-30/kernel_sched_update_curr.md) | CFS 统计更新入口：delta_exec 计算、vruntime 加权推进、min_vruntime 单调推进 |

---

## init/ (启动初始化，27 篇)
> start_kernel 启动链路、initramfs 解包、do_mounts 根文件系统挂载、init_task 初始栈、uts namespace 初始化等。

---

## block/ (块层，2 篇)
> 块设备总线、IO 队列框架。

---

## security/ (安全模块，若干)
> SELinux、内核密钥管理、Credentials 凭证体系。

---

## drivers/ (设备驱动，1 篇)
> TTY 子系统 Magic SysRq 驱动入口。

---

## lib/ & ipc/ (公共库 & 进程间通信)
> XArray、iov_iter 迭代器、IPC namespace 初始化等。

---

*本索引随每日学习自动更新。*
