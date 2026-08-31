# 每日内核源码分析：pick_next_task_fair

- **日期**：2026-09-01
- **子系统**：kernel/sched（CFS 调度器）
- **源文件**：kernel/sched/fair.c:6769-6899
- **类型**：function
- **完整归档**：[../../../../daily/2026/09/2026-09-01/kernel_sched_pick_next_task_fair.md](../../../../daily/2026/09/2026-09-01/kernel_sched_pick_next_task_fair.md)

---

## 功能摘要

`pick_next_task_fair()` 是 CFS（完全公平调度器）的核心调度入口函数。每次 `__schedule()` 发生调度切换时被调用，负责：
1. 从 CFS 红黑树（tasks_timeline）中选出 vruntime 最小的调度实体
2. 支持 CONFIG_FAIR_GROUP_SCHED 层级化任务组（cgroup）调度，自顶向下逐层下钻到叶子 task
3. 针对同 cgroup 场景做增量式 put/set 优化路径，最小化操作的 cfs_rq 数量
4. 空队列时通过 idle_balance() 从其他 CPU 拉任务并可能返回 RETRY_TASK
5. 维护 SMP MRU 链表与高精度 hrtick 调度 tick

关键设计：**红黑树最左节点 = 最小 vruntime = 理论最公平选择**，但辅以 `next/last/skip` 三个 buddy 机制在"不显著破坏公平"的前提下优化唤醒延迟和缓存热度。

## 核心要点

| 维度 | 内容 |
|------|------|
| 数据结构 | `struct cfs_rq`（CFS运行队列）、`struct sched_entity`（调度实体）、`struct rq`（per-CPU运行队列） |
| 核心算法 | 红黑树（rb_root_cached leftmost）+ Buddy 机制 + 组调度层级下钻 + LCA 公共祖先优化 |
| 关键下游 | `update_curr()`、`pick_next_entity()`、`set_next_entity()`、`put_prev_entity()`、`idle_balance()` |
| 上游调用 | `pick_next_task()` 快速路径/慢速路径 → `fair_sched_class.pick_next_task` → 本函数 |

详见主归档文件中的核心逻辑流程图、调用关系图、设计权衡分析以及完整去冗源码片段。
