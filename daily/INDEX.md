# 内核源码每日学习总索引

> 本仓库基于 [chunlanse/linux-4.x.y](https://github.com/chunlanse/linux-4.x.y) 分析仓库 + [torvalds/linux v4.19](https://github.com/torvalds/linux/tree/v4.19) 源码自动生成。
> 内核源码本体通过 `https://raw.githubusercontent.com/torvalds/linux/v4.19/<path>` 按需拉取，避免重复 clone。

## 归档结构

- 子系统就地归档：`{子系统}/{源文件名}/{函数名}.md`（如 `mm/vmscan.c/inactive_list_is_low.md`）
- 日期归档：`daily/YYYY/MM/YYYY-MM-DD/{子系统}_{函数名}.md`
- 按子系统索引：`daily/by-subsystem.md`
- 进度统计：`daily/progress-stats.json`

## 已分析条目（按日期倒序）

| 日期 | 子系统 | 函数名 | 笔记 |
|------|--------|--------|------|
| 2026-09-13 | mm | `inactive_list_is_low` | [mm/vmscan.c/inactive_list_is_low.md](../mm/vmscan.c/inactive_list_is_low.md) |

---

*最近更新：2026-09-13 by linux-kernel-daily-study skill*
