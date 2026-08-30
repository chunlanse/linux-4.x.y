# kernel/sched/fair.c 分析笔记（CFS 完全公平调度器）

Linux 4.19 调度器 CFS 类 `kernel/sched/fair.c` 源码分析索引。

## 函数分析表

| 函数名 | 一句话功能摘要 | 分析笔记 | 分析日期 |
|--------|----------------|----------|----------|
| `load_balance` | SMP 调度域内真正执行跨 CPU 任务迁移（pull）的均衡核心；含两级查找、detach/attach 三段式、LBF_DST_PINNED 备选 CPU、active_balance 强推等机制 | [load_balance.md](./load_balance.md) | 2026-08-31 |

## 后续推荐（未分析的高价值候选）

- `rebalance_domains` — 按调度域层次调用 load_balance，维护 next_balance/balance_interval 退避
- `find_busiest_group` — 计算调度域各调度组平均负载与不均衡量
- `find_busiest_queue` — 在最繁忙调度组中定位最忙 CPU 运行队列
- `detach_tasks` + `attach_tasks` — 摘取与挂载均衡任务，内部含 can_migrate_task/task_hot 判定
- `entity_tick` / `place_entity` / `update_curr` — CFS 实体 vruntime 更新与红黑树位置调整
- `task_tick_fair` / `prio_changed_fair` / `task_fork_fair` — CFS 调度类核心回调钩子
- `init_sched_fair_class` — 启动时注册 fair_sched_class，初始化 CFS 带宽与软中断
- `nohz_balancer_kick` / `nohz_idle_balance` — NOHZ_FULL 场景下的值班式均衡
