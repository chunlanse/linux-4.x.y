# ep_insert — epoll_ctl(EPOLL_CTL_ADD) 核心实现

- **日期**：2026-08-28
- **源文件**：fs/eventpoll.c:1264-1386（Linux 4.4）
- **主归档**：[../../../../daily/2026/08/2026-08-28/fs_ep_insert.md](../../../../daily/2026/08/2026-08-28/fs_ep_insert.md)

---

## 一句话功能摘要

将目标文件描述符正式加入 epoll 实例的兴趣集合：分配 epitem、通过 VFS poll 机制注册 `ep_poll_callback` 到目标文件的所有等待队列、将条目挂入红黑树（索引）和 tfile->f_ep_links（反向清理链），并在目标已就绪时立即入 rdllist 唤醒 epoll_wait 等待者；在嵌套场景下执行 reverse_path_check 防止唤醒路径爆炸。

## 核心要点速记

| 项 | 内容 |
|---|---|
| 系统调用入口 | `sys_epoll_ctl(EPOLL_CTL_ADD)` |
| 锁上下文 | 必须持 `ep->mtx`；内部使用 `ep->lock` (irqsave) 和 `tfile->f_lock` |
| 新分配结构 | `struct epitem` (epi_cache) + 若干 `struct eppoll_entry` (pwq_cache) |
| 索引结构 | 红黑树 (`eventpoll->rbr`)，键为 (struct file *, int fd) |
| 就绪钩子 | `ep_poll_callback`，由 `ep_ptable_queue_proc` 注册到各等待队列 |
| 典型错误码 | -ENOSPC(配额)、-ENOMEM(内存)、-EINVAL(reverse_path_check) |
| 特殊标志 | EPOLLWAKEUP → 创建 wakeup_source；EPOLLET/EPOLLONESHOT 在回调里生效 |

---

完整功能作用、关键数据结构逐字段解读、核心逻辑 Mermaid 流程图（含错误回滚路径）、上游/下游调用关系图、7 项设计权衡与易错点分析、以及完整去冗源码片段均收录于 **[主归档文件](../../../../daily/2026/08/2026-08-28/fs_ep_insert.md)**。
