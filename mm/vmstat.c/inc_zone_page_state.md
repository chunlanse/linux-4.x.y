# inc_zone_page_state

- **日期**：2026-11-02
- **源文件**：`mm/vmstat.c:524-528`
- **子系统**：mm

## 功能摘要

`inc_zone_page_state()` 通过 `page_zone(page)` 定位 zone，把某个 `zone_stat_item` 的增量先写入当前 CPU 的 per-CPU 差分 `pageset->vm_stat_diff[item]`；当差分超过 `stat_threshold` 时，按“半阈值过冲”策略批量合并到 `zone->vm_stat[]` 与全局 `vm_zone_stat[]`。其目的，是把高频跨 CPU 的全局原子操作，压缩为少得多的批量原子操作。

## 关键点

- `vm_stat_diff[]` 与 `stat_threshold` 均为 `s8`，阈值上限被钳制为 125。
- `inc` 溢出时 `z = n + t/2`、`n = -t/2`，形成滞回，避免阈值附近抖动。
- x86（`CONFIG_HAVE_CMPXCHG_LOCAL`）使用 `this_cpu_cmpxchg` 重试；其他 SMP 架构用 `local_irq_save/restore`。
- 读侧 `zone_page_state()` 只是 zone 已合并值，可能滞后；“漂移”由 `zone_page_state_snapshot()` 与 `percpu_drift_mark` 兜底。
- 异步合并由 `vmstat_update()` / `refresh_cpu_vm_stats()` / `vmstat_shepherd()` 完成。

## 主要调用者

- `pgtable_page_ctor()`（`include/linux/mm.h`）：`NR_PAGETABLE`
- `account_page_dirtied()` / `__test_set_page_writeback()`（`mm/page-writeback.c`）：`NR_ZONE_WRITE_PENDING`
- `alloc_zspage()`（`mm/zsmalloc.c`）：`NR_ZSPAGES`
- `__blk_queue_bounce()`（`block/bounce.c`）：`NR_BOUNCE`

完整分析（含流程图与源码片段）：[mm_inc_zone_page_state.md](../../daily/2026/11/2026-11-02/mm_inc_zone_page_state.md)
