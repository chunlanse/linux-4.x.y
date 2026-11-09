# Linux 内核每日源码分析索引

> 由 `daily/tools/kernel_daily.py` 自动维护，按日期倒序。

| 日期 | 子系统 | 函数 | 源文件:行号 | 摘要 | 飞书 |
|------|--------|------|-------------|------|------|
| 2026-11-10 | kernel/sched | [preempt_notifier_unregister](2026/11/2026-11-10/kernel-sched__preempt_notifier_unregister.md) | `kernel/sched/core.c:2635-2638` | KVM vCPU 线程退出时从 current 的抢占通知器链表摘除节点，使后续调度不再回调 sched_in/sched_out；依赖调用方关抢占且不可在回调内调用。 | [文档](https://my.feishu.cn/docx/H9DWd2FE0o6yUMxRSuNcsAP2nXe) |
