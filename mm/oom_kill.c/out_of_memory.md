# out_of_memory

- **日期**：2026-09-03
- **子系统**：mm / OOM Killer
- **源文件**：mm/oom_kill.c:1064-1135
- **主归档**：[../../daily/2026/09/2026-09-03/mm_out_of_memory.md](../../daily/2026/09/2026-09-03/mm_out_of_memory.md)

## 一句话摘要

Linux 内核 OOM Killer 的总入口；当全局或 memcg 内存分配穷尽回收手段仍失败时，按约束类型 + `oom_badness` 评分算法选择"最坏"进程（或直接杀分配触发者）发送 SIGKILL，通过 `oom_reaper` 异步收割页表释放内存，防止系统死锁。

## 完整分析

完整的功能作用 / 关键数据结构（`struct oom_control`、`enum oom_constraint`、`TIF_MEMDIE/MMF_OOM_VICTIM`、sysctl）/ 核心逻辑 Mermaid 流程图（含 8 个关键决策点解读）/ 调用关系图（page_alloc.c、memcontrol.c、slab.c 三条触发路径，下游 `select_bad_process → oom_badness` 评分链与 `oom_kill_process` 杀进程链）/ 6 条易错点与设计权衡（`__GFP_FS` 假成功、`oom_lock` 串行化、将死进程快速路径、`(void*)-1UL` 哨位、归一化保底 1 分、Memcg vs Global OOM 差异），请打开上方**主归档**链接阅读。

## 附：函数签名

```c
// include/linux/oom.h:105
extern bool out_of_memory(struct oom_control *oc);

// mm/oom_kill.c:1064 实现
bool out_of_memory(struct oom_control *oc);
```
