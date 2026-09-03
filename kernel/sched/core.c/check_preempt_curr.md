# check_preempt_curr

- **日期**: 2026-09-04
- **路径**: kernel/sched/core.c:836-859（Linux v4.19）
- **主归档**: ../../../daily/2026/09/2026-09-04/kernel_sched_check_preempt_curr.md

调度器**抢占检查的统一入口函数**。当新任务 `p` 入队到某 CPU 运行队列 `rq` 时，判断当前正在运行的任务 `rq->curr` 是否应被抢占，并在需要时通过 `resched_curr` 设置 `TIF_NEED_RESCHED` 标志触发抢占。

## 1. 功能作用

核心职责分两条路径：

### 1.1 同调度类场景（`p->sched_class == curr->sched_class`）

委派给具体调度类的 `check_preempt_curr` 回调，策略由各调度类自行实现：

| 调度类 | 回调实现 | 判定准则 |
|-------|---------|---------|
| CFS (fair) | `check_preempt_wakeup` fair.c:6515 | vruntime 差值 与 `wakeup_gran` 比较 + buddy 提名优化 |
| RT | `check_preempt_curr_rt` rt.c:1476 | `p->prio < curr->prio`（数值越小优先级越高）+ SMP 同优先级 push/pull |
| DL (deadline) | deadline.c 对应回调 | 截止时间先后比较 |

### 1.2 跨调度类场景

使用 `for_each_class` 从**最高优先级**调度类（stop → dl → rt → fair → idle）开始沿 `next` 链表遍历：
- **先命中 p 的类** → p 优先级更高 → `resched_curr(rq)` 触发抢占
- **先命中 curr 的类** → curr 优先级更高 → 直接 break 不抢占

这种"优先级链表顺序即优先级"的设计非常优雅，无需硬编码优先级数值，支持任意扩展调度类。

### 1.3 末尾时钟跳过优化

若 `task_on_rq_queued(rq->curr) && TIF_NEED_RESCHED 已设`，调用 `rq_clock_skip_update(rq)`。因为紧接着必然会进入 `schedule()`，其内会无条件更新 rq clock，此处再更新是冗余开销。

## 2. 调用上下文（四大调用点）

| 调用方 | 场景 | flags |
|-------|------|-------|
| `ttwu_do_wakeup` core.c:1652 | **任务唤醒主路径** `try_to_wake_up → ... → ttwu_do_wakeup`（最热点，占绝大多数调用） | `WF_SYNC`、`WF_MIGRATED` 等 |
| `wake_up_new_task` core.c:2420 | **新进程 Fork 后首次启动**，do_fork 路径末尾 | `WF_FORK`（不提名 NEXT_BUDDY） |
| `move_queued_task` core.c:924 | **CPU 亲和性/热插拔迁移**，任务从源 rq 移到新 rq 后检查 | 0 |
| `__migrate_swap_task` core.c:1197 | **NUMA balancing 两任务互换 CPU** 后在目标 rq 检查 | 0 |

## 3. 关键数据结构速览

### struct rq（每CPU运行队列）
- `rq->curr`：当前运行任务（抢占判定的被比较方）
- `rq->clock` / `rq->clock_task`：rq 时钟，`rq_clock_skip_update` 作用对象
- `rq->idle`：idle 进程指针，CFS 中被非 SCHED_IDLE 任务无条件抢占

### struct sched_class（调度类操作表）
```
stop → dl → rt → fair → idle  （优先级从高到低，next 指针串联）
```
`check_preempt_curr` 回调是表中第三项操作。跨类场景下 `for_each_class` 即沿该链表顺序遍历。

### struct sched_entity（CFS 调度实体）
CFS 抢占判定比较 `vruntime`（虚拟运行时）。`wakeup_gran(se)` 使用**新任务 se 的权重**而非 curr 的权重将实时间粒度换算为虚拟时间，刻意对 lighter 任务施加更大惩罚，保证 buddy 机制不会破坏 nice 优先级预期。

### resched_curr 核心动作（core.c:453）
```c
if (cpu == smp_processor_id()) {
    set_tsk_need_resched(curr);         // TIF_NEED_RESCHED（返回用户态/中断返回检查）
    set_preempt_need_resched();         // PREEMPT bit（preempt_enable 快速路径检查）
} else {
    if (set_nr_and_not_polling(curr))
        smp_send_reschedule(cpu);       // 跨 CPU：非 polling idle 才发送 IPI
}
```

## 4. CFS 抢占判定完整流程（check_preempt_wakeup）

```
se==pse (自抢占) → return
throttled_hierarchy (CFS组被节流) → return
NEXT_BUDDY && scale && !WF_FORK → set_next_buddy(pse)
TIF_NEED_RESCHED already set → return
curr==SCHED_IDLE && p!=SCHED_IDLE → goto preempt
p!=SCHED_NORMAL || !WAKEUP_PREEMPTION → return
find_matching_se (组调度共同层级)
update_curr() → 更新 curr vruntime
wakeup_preempt_entity(se, pse) == 1?
  Yes → set_next_buddy → goto preempt
  No  → return
preempt:
  resched_curr(rq)
  se->on_rq && curr!=rq->idle && LAST_BUDDY && scale → set_last_buddy(se)
```

## 5. 易错与设计权衡

1. **同类委派取 curr 的类回调而非 p 的类**：因为回调会读取 curr 所在 rq 的热状态（buddy、update_curr），上下文属于 curr。跨类场景已由通用遍历规则处理，不存在混淆。
2. **TIF_NEED_RESCHED 只是"软标记"**：立即抢占仅在抢占点发生（中断返回、preempt_enable、显式 schedule）。若 curr 在关抢占/关中断临界区，抢占会延迟到临界区退出。
3. **SMP vs UP 的 for_each_class 起点差异**：SMP 从 stop_sched_class 开始，UP 从 dl_sched_class 开始（stop 类只为 migration stopper 存在）。手动索引优先级数组的代码会在跨内核配置时出 bug。
4. **wakeup_gran 使用 se（p）的权重而非 curr 的权重**：刻意的不对称设计，对低权重（高 nice）轻任务增加抢占门槛，抵消 NEXT_BUDDY 带来的调度偏移，维护优先级语义预期。
5. **跨 CPU resched_curr 的 polling idle IPI 抑制**：目标 CPU 正在 polling idle 时只设标志不发 IPI，节省功耗和中断开销（trace 点 `sched_wake_idle_without_ipi` 即可追踪）。
6. **rq_clock_skip_update 的前置条件**：仅当 curr 仍在队列上（`task_on_rq_queued`）时才跳过。已 dequeue 但尚未 context switch 的 curr 仍然需要 rq clock 正确更新。

## 6. 源码片段

```c
// kernel/sched/core.c:836-859  (Linux v4.19)
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
		rq_clock_skip_update(rq);
}
```

**深度解读、调用关系图、Mermaid 流程图以及 RT/Deadline 调度类的完整分析请查看主归档**。
