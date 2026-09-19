# 按子系统分类的学习索引

## kernel/sched（进程调度）

| 日期 | 函数 | 一句话摘要 | 链接 |
|------|------|-----------|------|
| 2026-09-20 | `check_preempt_curr` | 调度器唤醒抢占判定总入口，同类下放给 sched_class 回调，跨类按优先级链表判定并设置 TIF_NEED_RESCHED | [core.c/check_preempt_curr.md](../kernel/sched/core.c/check_preempt_curr.md) |
