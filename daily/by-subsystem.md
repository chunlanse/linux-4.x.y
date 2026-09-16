# 按子系统分类索引

| 子系统 | 已分析数量 | 代表性条目 |
|--------|-----------|------------|
| mm | 230 | `__alloc_pages_nodemask`, `do_brk`, `kmem_cache_alloc` |
| fs | 221 | `do_execve`, `vfs_read`, `ext4_map_blocks` |
| kernel | — | `copy_process`, `worker_thread`, `__schedule` |
| kernel/sched | 13 | `__schedule`, `try_to_wake_up`, `context_switch` |
| arch | 127 | — |
| init | 23 | `start_kernel`, `kernel_init` |
| lib | 4 | `iov_iter_init` |
| block | 1 | — |
| drivers | 1 | `device_add` |
| ipc | 1 | `init_ipc_ns` |
| security | 2 | — |

> 详细分析见各子系统目录下的源文件同名子目录，例如 `drivers/base/core.c/device_add.md`。
