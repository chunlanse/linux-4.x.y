check_preempt_curr
========================================

> 调度器抢占决策总入口。判断新入队任务 `p` 是否应抢占当前运行任务 `rq->curr`。同类委托给具体调度类回调，跨类则按调度类链表优先级顺序判定。

- **日期**：2026-09-05
- **子系统**：kernel/sched
- **源文件**：kernel/sched/core.c:1023-1046
- **内核版本**：Linux 4.3
- **完整分析**：[../../../../daily/2026/09/2026-09-05/kernel_sched_check_preempt_curr.md](../../../../daily/2026/09/2026-09-05/kernel_sched_check_preempt_curr.md)

## 功能作用

每当任务入队时（唤醒、fork、迁移、类切换），调度器必须决定新任务是否抢占当前任务。`check_preempt_curr` 是这一决策的统一入口：
- **同类** → `rq->curr->sched_class->check_preempt_curr(rq, p, flags)`，由 CFS/RT/DL 各自实现。
- **跨类** → 遍历 `stop → dl → rt → fair → idle` 调度类链表，先遇到 `p` 的类则 `resched_curr` 抢占，先遇到 `curr` 的类则不抢占。

## 核心逻辑

```c
void check_preempt_curr(struct rq *rq, struct task_struct *p, int flags)
{
	const struct sched_class *class;

	if (p->sched_class == rq->curr->sched_class) {
		rq->curr->sched_class->check_preempt_curr(rq, p, flags);
	} else {
		for_each_class(class) {
			if (class == rq->curr->sched_class)
				break;
			if (class == p->sched_class) {
				resched_curr(rq);
				break;
			}
		}
	}

	if (task_on_rq_queued(rq->curr) && test_tsk_need_resched(rq->curr))
		rq_clock_skip_update(rq, true);
}
```

## 关键数据结构

- `struct rq`：每 CPU 运行队列，含 `curr`、`lock`、`clock`。
- `struct sched_class`：调度类，含 `check_preempt_curr` 回调与 `next` 指针，按优先级连成链表。
- 调度类优先级链：`stop → dl → rt → fair → idle`。

## 调用关系

**主要调用者**：
| 调用方 | 文件 | 场景 |
|--------|------|------|
| `ttwu_do_wakeup` | core.c:1711 | 任务唤醒 |
| `wake_up_new_task` | core.c:2367 | fork 新任务 |
| `move_queued_task` | core.c:1083 | 跨 CPU 迁移 |
| `attach_task` | fair.c:5795 | CFS attach |
| `switched_to_fair` | fair.c:7968 | 切换到 CFS 类 |

**下游委托（同类回调）**：`check_preempt_curr_dl` / `check_preempt_curr_rt` / `check_preempt_wakeup`(CFS) / `check_preempt_curr_idle` / `check_preempt_curr_stop`。

## 设计要点

1. 跨类比较用链表遍历顺序代替数值比较，避免不同类优先级空间不可比的问题。
2. `resched_curr` 仅设置 `TIF_NEED_RESCHED` 并发送 IPI，不立即切换；真正切换在下一个 `schedule()` 点。
3. 时钟跳过优化：若即将调度，跳过一次 `update_rq_clock`。

> 完整分析（含 Mermaid 流程图、边界场景、源码片段）见顶部链接的日期归档文件。
