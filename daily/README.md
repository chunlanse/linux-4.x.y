# 每日内核源码学习工作流

每天从 Linux 4.x 源码中随机选取一个**未分析过**的核心函数/代码段，产出「功能作用 / 关键数据结构 / 核心逻辑流程图 / 调用关系」中文解读，归档并推送到飞书。

## 目录结构

```text
daily/
├── run-daily-study.sh          # 每日流水线入口（拉源码 + 去重选题 + 生成待分析任务）
├── scripts/select_target.py    # 选题器：扫描已分析索引、加权随机、抽取源码片段
├── INDEX.md                    # 按日期倒序的每日索引
├── by-subsystem.md             # 按子系统分类的索引
├── progress-stats.json         # 累计进度与子系统分布
├── .state/                     # 运行时状态（selection-<date>.json、pending-task.md）
└── YYYY/MM/YYYY-MM-DD/         # 每日分析归档
```

分析结果同时双写到对应子系统目录，例如 `kernel/sched/swait.c/prepare_to_swait_event.md`，与仓库既有的 `子系统/源文件/函数.md` 结构保持一致。

## 去重与选题规则

1. 扫描 workspace 中所有 `*.c|*.h|*.S/<函数名>.md` 笔记，构成 `ANALYZED_SET`；
2. 子系统权重：`mm` 25%、`kernel/sched` 25%、`drivers` 15%、`fs` 15%，其余（`kernel`/`ipc`/`lib`/`init`）分摊 20%；某子系统已分析比例 > 70% 时权重降为 1/4；
3. 候选函数按「导出符号 + 非 static + 通用前缀（`do_`/`sys_`/`vfs_`/`*_alloc`/`*_free`/`*_map`/`*_init`…）+ 全仓库出现次数」加权随机；
4. 日期作为随机种子，同一天重复运行结果稳定，跨天自动换题。

## 每日执行

### 方式 A：手动 / Trae 定时任务（推荐，能完成分析与推送）

对 Agent 说「开始今天的内核学习」，或把下列指令配置为 Trae 的每日定时任务：

```bash
cd /workspace && ./daily/run-daily-study.sh
# 然后让 Agent 读取 daily/.state/pending-task.md，按模板分析、归档并推送飞书
```

### 方式 B：cron 预生成任务

```bash
0 9 * * * cd /workspace && ./daily/run-daily-study.sh >> daily/.state/cron.log 2>&1
```

cron 负责拉源码、去重、选题并生成 `pending-task.md`；分析与飞书推送由 Agent 在任务触发时完成。

## 飞书推送

- 全文：`lark-cli docs +create --doc-format markdown --content @<笔记>.md --parent-position my_library`
- 摘要：`lark-cli im +messages-send --user-id <open_id> --markdown @<摘要>.md`
- Markdown 中的 `mermaid` 代码块会被导入为空画板，需用
  `lark-cli docs +whiteboard-update --whiteboard-token <token> --input_format mermaid --source @<图>.mmd --overwrite` 渲染。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WORKSPACE` | `/workspace` | 笔记根目录 |
| `KERNEL_SRC_PATH` | `~/linux-stable` | 内核源码路径，缺失时自动浅克隆 |
| `KERNEL_TAG` | `v4.19` | 内核版本标签 |
