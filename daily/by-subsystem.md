# 每日内核源码学习 · 按子系统分类索引 by-subsystem

> 点击「分析笔记」列中的链接可直接跳转到对应分析文档。日期归档位于 `daily/YYYY/MM/YYYY-MM-DD/` 目录。

---

## 📊 kernel/sched · 进程调度子系统（14 / 120 = 12%）

**调度类优先级**：`stop_sched_class → dl_sched_class → rt_sched_class → fair_sched_class → idle_sched_class`

| 文件 | 函数 / 结构 | 功能摘要 | 日期 | 分析笔记 |
|------|-----------|---------|------|---------|
| sched.h | `struct rq` | 每 CPU 运行队列主结构 | 已有 | [sched.h/struct_rq.md](../kernel/sched/sched.h/struct_rq.md) |
| sched.h | `struct sched_class` | 调度类操作表（模块化 OOP 核心抽象） | 已有 | [sched.h/struct_sched_class.md](../kernel/sched/sched.h/struct_sched_class.md) |
| **core.c** | **`check_preempt_curr`** | **抢占检查统一入口：同类委派 + 跨类优先级链表遍历 + clock 优化** | **2026-09-04** | **[core.c/check_preempt_curr.md](../kernel/sched/core.c/check_preempt_curr.md)** |
| core.c | `__schedule` | 主调度器函数：pick_next + context_switch | 已有 | [core.c/__schedule.md](../kernel/sched/core.c/__schedule.md) |
| core.c | `context_switch` | 进程切换：switch_mm 切换地址空间 + switch_to 切换栈/寄存器 | 已有 | [core.c/context_switch.md](../kernel/sched/core.c/context_switch.md) |
| core.c | `try_to_wake_up` | 任务唤醒主入口：状态机检查 → select_task_rq → 入队 → 抢占 | 已有 | [core.c/try_to_wake_up.md](../kernel/sched/core.c/try_to_wake_up.md) |
| core.c | `scheduler_tick` | 周期性调度 tick：更新执行时间、检查时间片 | 已有 | [core.c/scheduler_tick.md](../kernel/sched/core.c/scheduler_tick.md) |
| core.c | `sched_fork` | Fork 路径调度初始化：sched_class/se/vruntime | 已有 | [core.c/sched_fork.md](../kernel/sched/core.c/sched_fork.md) |
| core.c | `ttwu_do_activate` | 唤醒子步骤：activate_task 激活入队 | 已有 | [core.c/ttwu_do_activate.md](../kernel/sched/core.c/ttwu_do_activate.md) |
| core.c | `ttwu_activate` | 唤醒子步骤：activate_task + workqueue worker 通知 | 已有 | [core.c/ttwu_activate.md](../kernel/sched/core.c/ttwu_activate.md) |
| core.c | `ttwu_queue` | 唤醒子步骤：远程 IPI 入队（SMP） | 已有 | [core.c/ttwu_queue.md](../kernel/sched/core.c/ttwu_queue.md) |
| core.c | `wake_up_process` | 上层 API：try_to_wake_up(p, TASK_NORMAL, 0) | 已有 | [core.c/wake_up_process.md](../kernel/sched/core.c/wake_up_process.md) |
| core.c | `effective_prio` | 有效优先级：normal_prio + rt_mutex 提权修正 | 已有 | [core.c/effective_prio.md](../kernel/sched/core.c/effective_prio.md) |
| core.c | `set_load_weight` | 根据 policy/nice 设置 se->load 权重 | 已有 | [core.c/set_load_weight.md](../kernel/sched/core.c/set_load_weight.md) |

**下期学习推荐（kernel/sched 未分析高优先级）**：
1. `fair.c:pick_next_entity` — CFS 选择下一个运行实体（红黑树最左节点 + buddy 优化）
2. `fair.c:update_curr` — vruntime 更新数学公式与 min_vruntime 漂移
3. `fair.c:check_preempt_tick` — tick 周期性 CFS 抢占检查（与唤醒抢占对应）
4. `load_balance.c:load_balance` — SMP 负载均衡核心算法（newidle + periodic + active balance）
5. `rt.c:pick_next_task_rt` — RT 调度类的队列选择与优先级位图

---

## 📊 mm · 内存管理（230 / 150 = 153%）

**主要覆盖**：物理页分配器（page_alloc.c ~50 个）、slab/slub 分配器、vmalloc、mmap 映射、缺页中断、文件页缓存（filemap.c）、memblock 启动期分配、readahead 预读、highmem 高端映射。

| 代表文件 | 已分析数 | 代表函数 |
|---------|---------|---------|
| page_alloc.c | 70+ | `__alloc_pages_nodemask`、`get_page_from_freelist`、`__rmqueue_smallest`、`free_one_page`、buddy 系统全套 |
| slab.c / slab_common.c | 40+ | `kmem_cache_alloc`、`__do_cache_alloc`、`cache_grow`、`slab_alloc`、`kmalloc` 链 |
| vmalloc.c | 15+ | `__vmalloc_node_range`、`get_vm_area`、`vfree`、`vmap` |
| mmap.c | 15+ | `do_mmap`、`mmap_region`、`find_vma`、`vma_merge`、`sys_brk` |
| memory.c | 7 | `handle_mm_fault`、`handle_pte_fault`、`do_wp_page`（写时复制） |
| filemap.c | 13 | `do_generic_file_read`、`filemap_fault`、`add_to_page_cache_locked`、`generic_perform_write` |
| memblock.c | 8 | `memblock_add_range`、`memblock_reserve`、`memblock_set_current_limit` |
| readahead.c | 4 | `__do_page_cache_readahead`、`ondemand_readahead`、同步/异步预读 |

---

## 📊 fs · 文件系统（217 / 300 = 72%）

**主要覆盖**：VFS 框架（namei/路径查找、open/close/read/write、dcache/目录项缓存、inode/索引节点、superblock/超级块、mount 挂载、execve 可执行加载）、文件描述符管理、binfmt_elf ELF 加载器、ext2/3/4、f2fs、fuse、sdcardfs 等。

**代表函数**：`do_filp_open`、`path_lookupat`、`link_path_walk`、`vfs_read/vfs_write`、`do_execveat_common`、`load_elf_binary`、`alloc_inode`、`mount_bdev`、`sget`、`__d_alloc`、`sys_mount`、`do_mount`...

---

## 📊 include · 公共头文件（182 / 500 = 36%）

核心数据结构与内联函数分析：

| 头文件 | 代表分析 |
|-------|---------|
| linux/sched.h | `struct task_struct`、`struct sched_entity`、`copy_thread_tls`、`union thread_union`、pid 相关 |
| linux/fs.h | `struct inode`、`struct file`、`struct super_block`、`struct address_space`、`struct kiocb` |
| linux/mm.h | `struct vm_area_struct`、`vm_unmapped_area`、`do_mmap_pgoff`、`randomize_va_space` |
| linux/gfp.h | GFP 标志位区表、`__alloc_pages` 系列 API |
| linux/pid.h | `struct pid`、`struct upid`、pid 命名空间 |
| linux/memblock.h | memblock 核心结构 |
| linux/slab_def.h | `struct kmem_cache` |
| linux/workqueue.h | workqueue_struct/work_struct |

---

## 📊 arch · 架构相关（127 / 800 = 16%）

| 架构 | 重点覆盖 |
|-----|---------|
| arm (32-bit) | 启动（head.S 页表 / MMU 开启 / FDT / atags 解析）、异常向量表（entry-armv.S）、系统调用（entry-common.S）、线程切换（__switch_to / copy_thread）、MMU 页表（pgtable-2level.h）、内存布局（memory.h / highmem.h）、DMA / dma-mapping.c |
| arm64 | 缺页中断 do_page_fault、内存管理 README |

---

## 📊 kernel · 内核核心（不含调度）（75 / 200 = 38%）

| 模块 | 已分析 | 代表 |
|-----|-------|------|
| fork.c（进程创建）| 16 | `copy_process`、`_do_fork`、`dup_task_struct`、`kernel_thread`、`mm_alloc`、`clone` |
| workqueue.c（工作队列）| 24 | `worker_thread`、`process_one_work`、`__queue_work`、`create_worker`、各类 pwq/pool/init |
| kthread.c（内核线程）| 3 | `kthreadd`、`kthread_create_on_node` |
| pid.c（PID 管理）| 8 | `alloc_pid`、`attach_pid`、`pid_task`、`init_pid_ns`、`pid_hash` |
| 其他 | 20+ | nsproxy、cgroup、params、percpu、cpu、user |

**下期高优先级未分析**：exit.c（`do_exit`、进程终止）、signal.c（信号处理）、ptrace.c（ptrace 调试）、sys.c（系统调用合集）、cred.c（凭据/权能）、printk（内核日志）

---

## 📊 init · 启动初始化（23 / 60 = 38%）

start_kernel → rest_init → kernel_init 启动链、do_mounts 根文件系统挂载、initramfs 填充、init_task 初始任务、init 版本号 uts namespace。

---

## 📊 ipc · 进程间通信（1 / 20 = 5%）

仅分析了 `msgutil.c:init_ipc_ns`（IPC 命名空间初始化）。待补：System V 消息队列 msg.c、信号量 sem.c、共享内存 shm.c 全部核心。

---

## 📊 net · 网络协议栈（1 / 500 = 0.2%）

仅分析了 trace/events/README。待补：网络设备层 dev.c、套接口层 sock.c/af_inet.c、sk_buff 管理、IPv4/TCP/UDP 核心路径。

---

## 📊 lib · 内核通用库（4 / 50 = 8%）

已分析：`iov_iter.c`（迭代器初始化/前进/原子拷贝）3 个、`xarray.c/README`。待补：rbtree（红黑树，CFS 核心数据结构）、radix-tree、idr、list_sort、cpumask、hexdump、string 等。

---

## 📊 security · 安全子系统（2 / 30 = 7%）

已分析：Credentials 凭据、SELinux 概览、keys README。待补：LSM hooks、keys/keyring、capability、integrity IMA/EVM。

---

## 📊 drivers · 设备驱动（0 / 1000 = 0%）

**⚠️ 大空白区，尚未开始任何分析**。下期高优先级：

- `drivers/base/`：设备驱动模型（core.c 设备 add/del、bus.c 总线枚举匹配、driver.c 驱动注册、class.c 设备类、platform.c 平台总线、dd.c probe 流程）
- `drivers/char/`：字符设备核心 mem.c、random.c
- `drivers/block/`：块设备核心 genhd.c、blk-core.c、request 队列
- `drivers/pci/`：PCI 枚举与驱动

---

## 📊 block · 块设备层（0 / 30 = 0%）

**⚠️ 空白区**。待补：elevator 调度器（NOOP/DEADLINE/CFQ）、blk-mq 多队列、bio/request 处理路径、ioctl。

---

## 📊 boot · 启动流程（1 / 40 = 3%）

仅分析了 x86 Boot.md。待补：arm/arm64/x86 的二级 bootloader 交互、DTB/FDT 解析、UEFI 启动、压缩内核解压缩（head.S in arch/*/boot/compressed）。
