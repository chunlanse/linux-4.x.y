# 每日内核源码分析：__reset_isolation_suitable

- **日期**：2026-10-03
- **子系统**：mm（内存管理）
- **源文件**：mm/compaction.c:244-270
- **类型**：函数

---

## 1. 功能作用

`__reset_isolation_suitable()` 是 Linux 内存管理子系统中 **内存压缩（memory compaction）** 机制的关键辅助函数，用于**清除 pageblock 的跳过标记**，使得之前被标记为"不适合隔离"的页块重新参与内存压缩扫描。

在内存压缩过程中，内核会扫描 zone 内的 pageblock，尝试将可迁移页移动到 zone 的一端，从而腾出连续的空闲页以满足大页分配请求。如果某个 pageblock 在此次压缩中未能隔离出任何可迁移页，它会被标记为 `PG_migrate_skip`，后续压缩扫描将跳过它以提高效率。

该函数的典型触发场景：
- 当某次完整的内存压缩结束后（`compact_blockskip_flush` 被置位）。
- 当压缩被延迟（deferred）后重新开始时。

---

## 2. 关键数据结构

- `struct zone`：内存区域描述符，包含 `compact_blockskip_flush`、`compact_cached_migrate_pfn[2]`、`compact_cached_free_pfn` 等压缩相关字段。
- `struct compact_control`：单次内存压缩的上下文控制结构，记录扫描位置、gfp_mask、order 等信息。
- `pageblock_nr_pages`：pageblock 的页数（通常 1024 页 = 4MB）。

---

## 3. 核心逻辑流程

```
入口 __reset_isolation_suitable(zone)
  ├─ 初始化 start_pfn / end_pfn
  ├─ compact_blockskip_flush = false
  ├─ 遍历 zone 内每个 pageblock
  │   ├─ cond_resched()  // 主动让出 CPU
  │   ├─ pfn_to_online_page(pfn) 获取 page
  │   ├─ 校验 page 存在且属于当前 zone
  │   ├─ 跳过持久性大页 (pageblock_skip_persistent)
  │   └─ clear_pageblock_skip(page) 清除跳过标记
  └─ reset_cached_positions(zone) 重置扫描缓存位置
```

---

## 4. 调用关系

### 调用者
- `reset_isolation_suitable()` — 遍历节点所有 zone 时触发。
- `compact_zone()` — 压缩从 deferred 状态重启时触发。

### 被调用者
- `pfn_to_online_page()`：PFN 转在线 page。
- `clear_pageblock_skip()`：清除 pageblock 跳过标记。
- `pageblock_skip_persistent()`：判断是否为持久性跳过页块。
- `reset_cached_positions()`：重置扫描缓存位置。
- `cond_resched()`：检查调度需求。

---

## 5. 易错点 / 设计权衡

1. **批处理清除 vs 实时清除**：跳过标记采用"设置时立即标记、清除时批量重置"的策略，避免了频繁的 zone 全遍历。
2. **cond_resched 防软锁死**：在大型内存系统（TB 级）上，遍历所有 pageblock 可能耗时较长，主动让出 CPU 是必要的。
3. **复合页持久跳过**：超大 order 的 compound page（如 THP）占用的 pageblock 始终被跳过，这类页块无法通过标准压缩产生更高阶连续页。
4. **zone 边界安全**：即使通过 `zone_start_pfn` / `zone_end_pfn` 限定范围，仍对每页执行 `page_zone(page)` 校验，防范内存热插拔导致的布局变化。

---

## 附：核心源码片段

```c
static void __reset_isolation_suitable(struct zone *zone)
{
	unsigned long start_pfn = zone->zone_start_pfn;
	unsigned long end_pfn = zone_end_pfn(zone);
	unsigned long pfn;

	zone->compact_blockskip_flush = false;

	for (pfn = start_pfn; pfn < end_pfn; pfn += pageblock_nr_pages) {
		struct page *page;

		cond_resched();

		page = pfn_to_online_page(pfn);
		if (!page)
			continue;
		if (zone != page_zone(page))
			continue;
		if (pageblock_skip_persistent(page))
			continue;

		clear_pageblock_skip(page);
	}

	reset_cached_positions(zone);
}
```
