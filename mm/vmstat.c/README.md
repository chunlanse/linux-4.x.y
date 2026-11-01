# mm/vmstat.c

虚拟内存统计（ZVC）实现：zone/node/NUMA 计数的 per-CPU 差分、阈值合并、异步刷新与 `/proc/vmstat`。

## 函数索引

| 函数 | 一句话功能 | 分析笔记 | 日期 |
|------|------------|----------|------|
| `inc_zone_page_state` | per-CPU 差分 + 阈值批量合并的 zone 计数器递增入口 | [分析笔记](./inc_zone_page_state.md) | 2026-11-02 |
