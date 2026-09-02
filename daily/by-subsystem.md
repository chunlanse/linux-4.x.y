# 按子系统分类索引 by-subsystem

将每日学习条目按内核子系统归类，便于子系统内横向复习。

---

## mm（内存管理）

| 日期 | 源文件 | 函数 / 结构 | 一句话摘要 | 分析笔记 |
|------|--------|-------------|------------|----------|
| 2026-09-03 | mm/oom_kill.c | `out_of_memory` | OOM Killer 总入口；全局/memcg 内存耗尽后，基于 `oom_badness` 评分或 sysctl 快速路径选牺牲进程，唤醒 oom_reaper 异步收割。 | [../mm/oom_kill.c/out_of_memory.md](../mm/oom_kill.c/out_of_memory.md) · [主归档](../daily/2026/09/2026-09-03/mm_out_of_memory.md) |

**mm 其他已分析模块**（就地归档，未单独列入日期）：page_alloc.c（~140+）、slab.c（~50+）、vmalloc.c、slab_common.c、mmap.c、memory.c、filemap.c、readahead.c、memblock.c、highmem.c、nobootmem.c、util.c、internal.h、vmscan.c、slab.h、cma.c、bootmem.c 等。

---

## kernel（核心）

| 日期 | 源文件 | 函数 / 结构 | 一句话摘要 | 分析笔记 |
|------|--------|-------------|------------|----------|
| — | （历史条目待后续补录） | — | — | — |

**已就地分析**：fork.c、sched/core.c、workqueue.c、pid.c、kthread.c、params.c、locking/、percpu.c、smp.c、cpu.c、bounds.c、nsproxy.c、cgroup.c、user.c 等。

---

## kernel/sched（进程调度）

| 日期 | 源文件 | 函数 / 结构 | 一句话摘要 | 分析笔记 |
|------|--------|-------------|------------|----------|
| — | （历史条目待后续补录） | — | — | — |

**已就地分析**：sched/core.c（set_load_weight / try_to_wake_up / ttwu_do_activate / __schedule / ttwu_activate / scheduler_tick / context_switch / effective_prio / sched_fork / ttwu_queue / wake_up_process 等）、sched/sched.h（struct_rq / struct_sched_class）。

---

## fs（文件系统）

| 日期 | 源文件 | 函数 / 结构 | 一句话摘要 | 分析笔记 |
|------|--------|-------------|------------|----------|
| — | （历史条目待后续补录） | — | — | — |

**已就地分析**：ext4/ 系列、exec.c、namei.c、dcache.c、namespace.c、inode.c、file.c、open.c、mount.h、read_write.c、super.c、block_dev.c、file_table.c、filesystems.c、libfs.c、buffer.c、sync.c、attr.c、fuse/、ramfs/、f2fs/、jbd2/、sdcardfs/、ext2/ 等。

---

## include / headers（核心数据结构头文件）

| 日期 | 源文件 | 函数 / 结构 | 一句话摘要 | 分析笔记 |
|------|--------|-------------|------------|----------|
| — | （历史条目待后续补录） | — | — | — |

**已就地分析**：include/linux/{mmzone.h, gfp.h, sched.h, mm_types.h, pid.h, mm.h, fs.h, dcache.h, file.h, fdtable.h, slab.h, slab_def.h, vmalloc.h, memblock.h, workqueue.h, mutex.h, semaphore.h, pagemap.h, page-flags.h, pageblock-flags.h, page-flags-layout.h, nodemask.h, nsproxy.h, pid_namespace.h, ipc_namespace.h, user_namespace.h, utsname.h, mnt_namespace.h, mount.h, path.h, cpumask.h, init.h, init_task.h, syscalls.h, kernel.h, bootmem.h, percpu-defs.h, topology.h, numa.h, pfn.h, err.h, types.h, bitops.h, rculist_bl.h, irqflags.h, uio.h, binfmts.h, fs_struct.h}；include/asm-generic/；include/uapi/linux/；include/net/；include/trace/events/。

---

## init / ipc / block / security / lib（次要子系统）

| 日期 | 源文件 | 函数 / 结构 | 一句话摘要 | 分析笔记 |
|------|--------|-------------|------------|----------|
| — | （历史条目待后续补录） | — | — | — |

**已就地分析**：
- init：main.c、do_mounts.c、init_task.c、initramfs.c、version.c
- ipc：msgutil.c / init_ipc_ns
- block：bus / README
- security：credentials、keys、selinux
- lib：iov_iter.c、xarray.c

---

## drivers（设备驱动）

| 日期 | 源文件 | 函数 / 结构 | 一句话摘要 | 分析笔记 |
|------|--------|-------------|------------|----------|
| — | （尚未开始，后续优先覆盖 drivers/base/core.c / dd.c / bus.c 等驱动模型核心） | — | — | — |
