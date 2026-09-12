# 按子系统归档索引

## mm/

| 函数名 | 一句话功能 | 笔记 | 首次分析日期 |
|--------|----------|------|--------------|
| `inactive_list_is_low` | 判断 LRU inactive 链表是否过小、是否需要 active→inactive 降级 | [mm/vmscan.c/inactive_list_is_low.md](../mm/vmscan.c/inactive_list_is_low.md) | 2026-09-13 |
| `wakeup_kswapd` | 唤醒 kswapd 内核线程进行后台内存回收 | [mm/vmscan.c/wakeup_kswapd.md](../mm/vmscan.c/wakeup_kswapd.md) | （已有） |

## kernel/sched/

| 函数名 | 一句话功能 | 笔记 | 首次分析日期 |
|--------|----------|------|--------------|
| `__schedule` | 调度器主入口，选择下一个可运行任务并切换上下文 | [kernel/sched/core.c/__schedule.md](../kernel/sched/core.c/__schedule.md) | （已有） |
| `try_to_wake_up` | 唤醒一个睡眠中的任务并将其加入运行队列 | [kernel/sched/core.c/try_to_wake_up.md](../kernel/sched/core.c/try_to_wake_up.md) | （已有） |

> 仅展示本工作流新增/今日条目，其余子系统已有大量历史笔记，不在此重复列出。
