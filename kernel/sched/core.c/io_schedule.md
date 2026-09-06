# io_schedule

- **日期**：2026-09-07
- **源文件**：kernel/sched/core.c:5135-5143
- **类型**：导出函数（EXPORT_SYMBOL）

## 一句话功能

标记当前任务处于 I/O 等待状态（设置 `in_iowait`），冲刷块层 plug 请求后调用 `schedule()` 睡眠，唤醒后恢复 `in_iowait`，使 `rq->nr_iowait` 计账与块 I/O 延迟统计准确。

## 核心机制

1. `io_schedule_prepare()`：保存旧 `in_iowait`，置 1，`blk_schedule_flush_plug(current)` 提交累积的 I/O 请求。
2. `schedule()`：`__schedule` 出队时若 `prev->in_iowait` 则 `atomic_inc(&rq->nr_iowait)` + `delayacct_blkio_start()`。
3. I/O 完成，`try_to_wake_up()` 唤醒：若 `p->in_iowait` 则 `delayacct_blkio_end(p)` + `atomic_dec(&rq->nr_iowait)`。
4. `io_schedule_finish(token)`：恢复 `current->in_iowait` 旧值。

## 关键点

- 调用者必须先 `set_current_state(TASK_UNINTERRUPTIBLE)`，否则不会睡眠。
- `in_iowait` 是 `current` 私有字段，无需锁。
- token 机制支持嵌套调用，不会错误清零。

## 调用关系

- **调用者**：`wait_on_page_bit`(mm/filemap.c)、`dio_await_complete`(fs/direct-io.c)、`dm_wait_for_completion`(drivers/md/dm.c)、`mempool` 路径等 40 处。
- **被调用者**：`io_schedule_prepare` → `blk_schedule_flush_plug` → `blk_flush_plug_list`；`schedule` → `__schedule`；`io_schedule_finish`。

完整分析见日期归档：[daily/2026/09/2026-09-07/kernel_sched_io_schedule.md](../../../daily/2026/09/2026-09-07/kernel_sched_io_schedule.md)
