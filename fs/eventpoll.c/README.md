# fs/eventpoll.c — epoll（高效事件轮询）

Linux epoll 机制的内核实现主文件，位于 `fs/eventpoll.c`（约 2133 行，Linux 4.4）。

## 一句话介绍

把用户态感兴趣的 `(epfd, fd, events)` 三元组加入兴趣集合（红黑树索引），通过 VFS poll 框架在目标文件各等待队列上注册回调；一旦目标就绪就将条目链入就绪链表，`epoll_wait` 被唤醒后批量拷贝就绪事件回用户态。是 Nginx/Redis/Netty 等高并发服务器的核心基石。

## 文件要点速览

| 组件 | 对应代码 | 说明 |
|---|---|---|
| **主数据结构** | `struct eventpoll` (L180) / `struct epitem` (L136) / `struct eppoll_entry` (L225) | epoll 实例、被监控 fd、poll 回调包装三级结构。 |
| **三级锁模型** | `epmutex → ep->mtx → ep->lock` | 全局互斥（拓扑检查）→ 可睡眠互斥（ctl + 事件搬运）→ IRQ-safe 自旋锁（就绪链表）。 |
| **红黑树兴趣集** | `eventpoll->rbr` + `ep_rbtree_insert/ep_find` | 键 `(struct file*, fd)`，O(log n) 查找/插入/删除。 |
| **就绪双链表** | `eventpoll->rdllist` + `epi->rdllink` | 所有有事件待上报的 epitem 链。 |
| **溢出单链表** | `eventpoll->ovflist` + `epi->next` | 无锁事件搬运期间新就绪暂存，解决锁与 copy_to_user 冲突。 |
| **poll 回调注册** | `ep_ptable_queue_proc` → `add_wait_queue(func=ep_poll_callback)` | 目标就绪时被 wake_up 调用，把 epitem 入 rdllist 并唤醒 waiters。 |
| **循环/深度保护** | `ep_loop_check` + `reverse_path_check` + `ep_call_nested` + `EP_MAX_NESTS=4` | 防止嵌套 epoll 形成死循环和唤醒路径爆炸。 |

## 函数/结构索引

| 名称 | 功能一句话 | 分析笔记 | 分析日期 |
|---|---|---|---|
| `ep_insert` | epoll_ctl(EPOLL_CTL_ADD) 核心：分配 epitem、注册 poll 回调、挂红黑树、检查就绪、执行嵌套安全检查。 | [ep_insert.md](./ep_insert.md) | 2026-08-28 |
| `ep_remove` | 从兴趣集删除条目，反向清理所有 poll 回调、链表、红黑树。 | （待分析） | — |
| `ep_modify` | EPOLL_CTL_MOD：修改事件掩码、可选切换 EPOLLWAKEUP、重新做一次 poll 收集当前事件。 | （待分析） | — |
| `ep_poll_callback` | 核心回调：目标文件就绪时被 wake_up 调用，判断事件掩码→移入 rdllist→唤醒 epoll_wait/poll_wait。 | （待分析） | — |
| `ep_poll` | epoll_wait 的主体：等待就绪事件，使用 ep_scan_ready_list 拷贝到用户 buffer。 | （待分析） | — |
| `ep_scan_ready_list` | 通用就绪扫描+回调处理器（写入 ep_send_events_proc 等）；维护 ovflist 与锁释放窗口。 | （待分析） | — |
| `epoll_ctl` (syscall) | epoll_ctl(2) 系统调用三分支：ADD/MOD/DEL；full_check 与全局 epmutex。 | （待分析） | — |
| `epoll_create1` (syscall) | 创建 eventpoll 文件描述符（anon_inode）。 | （待分析） | — |
| `epoll_wait` / `epoll_pwait` (syscall) | 等待就绪事件入口，转入 ep_poll。 | （待分析） | — |
| `eventpoll_release_file` | 文件 close 未显式 DEL 时的反向安全清理路径。 | （待分析） | — |
| `ep_loop_check` / `reverse_path_check` | 嵌套回环与唤醒路径计数检查。 | （待分析） | — |
| `struct eventpoll` | epoll 实例主结构。 | （待分析） | — |
| `struct epitem` | 被监控 fd 的条目结构。 | （待分析） | — |
| `struct eppoll_entry` | poll 回调条目。 | （待分析） | — |
