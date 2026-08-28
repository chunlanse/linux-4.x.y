# 每日内核源码学习索引

> 按日期倒序排列。累计已分析 825 个核心函数/结构。

| 日期 | 子系统 | 函数/结构 | 功能摘要 | 分析笔记 |
|------|--------|-----------|----------|----------|
| 2026-08-28 | fs | `ep_insert` | epoll_ctl(EPOLL_CTL_ADD) 核心实现：分配 epitem、注册 poll 回调、插入红黑树与就绪链，处理嵌套拓扑检查与即时就绪唤醒 | [fs_ep_insert.md](./2026/08/2026-08-28/fs_ep_insert.md) |

## 统计信息

- 详细统计见 [progress-stats.json](./progress-stats.json)
- 按子系统分类索引见 [by-subsystem.md](./by-subsystem.md)
