# 每日内核源码学习 — 按子系统分类

> 由 `linux-kernel-daily-study` 工作流自动维护。

## kernel/sched

| 日期 | 函数 / 代码段 | 源文件 | 一句话功能摘要 | 笔记链接 |
|------|---------------|--------|----------------|----------|
| 2026-09-15 | `wake_up_new_task` | kernel/sched/core.c:2372 | fork 路径下让新创建的子进程第一次入队运行的核心入口，做负载初始化、CPU 选择、入队与抢占检查 | [daily](./2026/09/2026-09-15/kernel_sched_wake_up_new_task.md) / [就地](../kernel/sched/core.c/wake_up_new_task.md) |
