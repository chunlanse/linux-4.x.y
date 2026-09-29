# pick_next_task

- **日期**：2026-09-30
- **子系统**：kernel/sched
- **源文件**：kernel/sched/core.c:3352-3391
- **完整分析**：[sched_pick_next_task.md](../../../../daily/2026/09/2026-09-30/sched_pick_next_task.md)

## 一句话作用

调度器从运行队列上挑选下一个要运行的任务，含 fast-path/slow-path 与 `RETRY_TASK` 重试协议。

## 关键点速览

- fast-path：`prev` 是 fair/idle 且 rq 全为 CFS 任务时，直接调 `fair.pick_next_task`。
- slow-path：`for_each_class` 遍历 `stop -> dl -> rt -> fair -> idle`。
- `RETRY_TASK` 触发 `again` 重试，保证高优先级类不漏选。
- 调用者：`__schedule()`；被调用：`fair/rt/dl/stop/idle.pick_next_task`。