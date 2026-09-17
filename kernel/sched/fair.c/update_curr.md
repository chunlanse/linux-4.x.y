# update_curr — CFS 运行时统计更新

- **日期**：2026-09-18
- **源文件**：kernel/sched/fair.c:803-836
- **内核版本**：Linux v4.20
- **完整归档**：[../../../../daily/2026/09/2026-09-18/kernel_sched_update_curr.md](../../../../daily/2026/09/2026-09-18/kernel_sched_update_curr.md)

## 一句话功能

`update_curr` 是 CFS 调度器的心脏——把当前运行实体的**真实运行时间**按权重换算为**虚拟运行时间 vruntime**，驱动 CFS 红黑树的公平排序。

## 核心逻辑

1. 计算 `delta_exec = now - curr->exec_start`（真实运行时长）；
2. **`curr->vruntime += calc_delta_fair(delta_exec, curr)`** —— 按权重缩放（高权重任务 vruntime 增长慢，获得更多 CPU）；
3. `update_min_vruntime` 推进 cfs_rq 的最小 vruntime（单调递增，防止休眠唤醒任务占便宜）；
4. 任务级统计（tracepoint、cgroup 计费）；
5. `account_cfs_rq_runtime` 扣减 CFS 带宽配额（cgroup CPU quota）。

## 关键数据结构

- `struct cfs_rq`：CFS 运行队列（curr、min_vruntime、tasks_timeline 红黑树、exec_clock）。
- `struct sched_entity`：可调度实体（exec_start、sum_exec_runtime、vruntime、load.weight）。
- `struct load_weight`：负荷权重（nice 0 → 1024）。

## 调用链

- 时钟节拍：`scheduler_tick` → `task_tick_fair` → `entity_tick` → `update_curr`
- 任务切换：`schedule()` → `put_prev_task_fair` → `put_prev_entity` → `update_curr`
- fork / yield / enqueue / dequeue / reweight 路径均会调用。

## 源码片段

```c
static void update_curr(struct cfs_rq *cfs_rq)
{
    struct sched_entity *curr = cfs_rq->curr;
    u64 now = rq_clock_task(rq_of(cfs_rq));
    u64 delta_exec;

    if (unlikely(!curr))
        return;

    delta_exec = now - curr->exec_start;
    if (unlikely((s64)delta_exec <= 0))
        return;

    curr->exec_start = now;

    schedstat_set(curr->statistics.exec_max,
                  max(delta_exec, curr->statistics.exec_max));

    curr->sum_exec_runtime += delta_exec;
    schedstat_add(cfs_rq->exec_clock, delta_exec);

    curr->vruntime += calc_delta_fair(delta_exec, curr);
    update_min_vruntime(cfs_rq);

    if (entity_is_task(curr)) {
        struct task_struct *curtask = task_of(curr);
        trace_sched_stat_runtime(curtask, delta_exec, curr->vruntime);
        cgroup_account_cputime(curtask, delta_exec);
        account_group_exec_runtime(curtask, delta_exec);
    }

    account_cfs_rq_runtime(cfs_rq, delta_exec);
}
```
