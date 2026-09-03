Task Switch
========================================

ARM
----------------------------------------

### __switch_to

https://github.com/novelinux/linux-4.x.y/blob/master/arch/arm/kernel/entry-armv.S/__switch_to.md

----------------------------------------

## kernel/sched/core.c 已分析函数索引

| 函数名 | 一句话功能摘要 | 分析笔记 | 分析日期 |
|--------|--------------|---------|---------|
| `__schedule` | 主调度器入口函数，context switch 核心驱动 | [__schedule.md](./__schedule.md) | 已有 |
| `context_switch` | 进程切换底层：切换地址空间 + 切换寄存器/栈 | [context_switch.md](./context_switch.md) | 已有 |
| `try_to_wake_up` | 任务唤醒主路径：状态检查、选 CPU、入队并抢占 | [try_to_wake_up.md](./try_to_wake_up.md) | 已有 |
| **`check_preempt_curr`** | **抢占检查统一入口：同类委派调度类回调 + 跨类优先级链表遍历判定 + rq clock 优化** | **[check_preempt_curr.md](./check_preempt_curr.md)** | **2026-09-04** |
| `scheduler_tick` | 周期性调度 tick：更新运行时、检查时间片耗尽、触发抢占 | [scheduler_tick.md](./scheduler_tick.md) | 已有 |
| `ttwu_do_activate` | 唤醒路径：激活任务入队 + workqueue worker 通知 | [ttwu_do_activate.md](./ttwu_do_activate.md) | 已有 |
| `ttwu_activate` | 唤醒路径子步骤：activate_task + on_rq 设置 + wq worker 唤醒 | [ttwu_activate.md](./ttwu_activate.md) | 已有 |
| `ttwu_queue` | 唤醒路径：ttwu_queue_remote IPI 远程入队 | [ttwu_queue.md](./ttwu_queue.md) | 已有 |
| `wake_up_process` | 上层 API：try_to_wake_up(p, TASK_NORMAL, 0) 封装 | [wake_up_process.md](./wake_up_process.md) | 已有 |
| `sched_fork` | Fork 路径调度初始化：设置 sched_class、sched_entity、se 权重与 vruntime | [sched_fork.md](./sched_fork.md) | 已有 |
| `effective_prio` | 计算有效优先级：normal_prio ← rt_mutex 临时提权的优先级修正 | [effective_prio.md](./effective_prio.md) | 已有 |
| `set_load_weight` | 根据 task policy/nice 值设置 se 权重 load.weight / load.inv_weight | [set_load_weight.md](./set_load_weight.md) | 已有 |
