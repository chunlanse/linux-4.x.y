# Linux 内核每日学习自动化工作流

## 一、工作流概述

本工作流实现了一套从**目标选取 → 源码提取 → AI 深度分析 → 归档保存 → 飞书推送**的完整自动化流程，帮助你系统性、不重复地积累 Linux 内核核心子系统的知识。

## 二、目录结构

```
/workspace/
├── scripts/
│   ├── select_target_v2.py       # 随机选取未分析的核心函数
│   └── daily_kernel_study.sh     # 每日工作流主脚本（选目标 + 通知）
├── daily/
│   ├── INDEX.json                # 已分析函数的机器索引
│   ├── INDEX.md                  # 已分析函数的人工可读索引
│   ├── progress-stats.json       # 各子系统学习进度统计
│   ├── TARGET.json               # 当前选中的目标（临时）
│   └── 2026/10/2026-10-03/       # 按日期归档的分析笔记
│       └── mm___reset_isolation_suitable.md
├── mm/、kernel/、fs/ ...         # 子系统就地归档（与日期归档双写）
└── README_WORKFLOW.md            # 本说明文档
```

## 三、前置依赖

- **内核源码**：已自动克隆到 `~/linux-stable`（v4.19 标签）。如需其他版本，可修改 `KERNEL_SRC_PATH`。
- **飞书 CLI**：`lark-cli` 已可用，当前已绑定到用户身份。
- **ctags**：用于准确提取函数定义（已预装）。

## 四、使用方式

### 方式 A：Agent 全自动分析（推荐）

直接对我说：
> "开始今天的内核源码学习"

我将自动执行以下步骤：
1. 扫描已分析索引，避免重复。
2. 按优先级（mm 25%、kernel/sched 25%、drivers 15%...）加权随机选取目标。
3. 读取源码，进行深度分析（功能作用、数据结构、Mermaid 流程图、调用关系、易错点）。
4. 双写归档：日期归档 + 子系统就地归档。
5. 创建飞书文档并推送通知给你。

### 方式 B：脚本预选目标 + Agent 后续分析

适用于你想提前知道今日目标，或在外部定时任务中使用：

```bash
# 执行选目标和飞书通知（不含 AI 分析）
bash /workspace/scripts/daily_kernel_study.sh
```

脚本执行后，你会收到飞书消息告知今日选中的函数和文件路径。随后你可以对我说：
> "分析今天的目标"

我将读取脚本生成的 `TARGET.json` 和源码片段，完成分析并推送结果。

### 方式 C：完全定时自动化（需外部调度器）

由于当前沙箱环境**不支持内置定时任务（Schedule 工具不可用）**，你可以通过以下方式实现每日定时触发：

#### 方案 1：本地/服务器 Cron（推荐）

在你的本地机器或服务器上添加 cron 任务：

```cron
# 每天早上 9 点执行选目标脚本，并通知你
0 9 * * * cd /workspace && bash scripts/daily_kernel_study.sh >> /var/log/kernel_daily.log 2>&1
```

#### 方案 2：GitHub Actions

在 GitHub 仓库中创建 `.github/workflows/daily_kernel.yml`：

```yaml
name: Daily Kernel Study
on:
  schedule:
    - cron: '0 9 * * *'  # 每天 UTC 9:00
  workflow_dispatch:

jobs:
  study:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Select target
        run: |
          git clone --depth 1 --branch v4.19 https://github.com/torvalds/linux.git ~/linux-stable
          bash scripts/daily_kernel_study.sh
```

#### 方案 3：配合 Trae 的定时触发

如果你使用的 Trae 环境支持外部 webhook 或 API 触发 Agent 会话，可以将 `daily_kernel_study.sh` 的最后一行改为调用该 webhook，实现"选目标 + 自动触发 Agent 分析"的全无人值守。

## 五、已分析覆盖统计

当前 `/workspace` 已积累 **947** 个函数的分析笔记，主要分布：
- `mm/`：内存管理（page_alloc、slab、vmalloc、compaction 等）
- `kernel/`：进程管理、调度、工作队列、锁等
- `fs/`：VFS、ext2/4、dcache、namei、namespace 等
- `include/linux/`：关键数据结构定义

## 六、飞书推送配置

默认推送到**当前登录用户**的飞书私信。如需推送到群聊，修改脚本中的：

```bash
# 推送到群聊
lark-cli im +messages-send --chat-id "oc_xxx" --markdown "..."

# 或推送到特定用户
export FEISHU_USER_ID="ou_xxx"
```

## 七、扩展与定制

| 配置项 | 环境变量 | 默认值 |
|--------|----------|--------|
| 内核源码路径 | `KERNEL_SRC_PATH` | `~/linux-stable` |
| 归档根目录 | `ARCHIVE_ROOT` | `/workspace/daily` |
| 飞书接收者 | `FEISHU_USER_ID` | 当前登录用户 |
| 外部 AI API | `OPENAI_API_KEY` | 空（可选） |

如需调整优先子系统权重，编辑 `scripts/select_target_v2.py` 中的 `priority_subsystems` 和 `weights` 列表。

## 八、示例输出

### 今日分析摘要（2026-10-03）

- **函数**：`__reset_isolation_suitable`
- **文件**：`mm/compaction.c:244-270`
- **子系统**：mm
- **一句话功能**：内存压缩过程中批量清除 pageblock 的跳过标记，让曾被判定为"不适合隔离"的页块重新参与扫描。

📎 **飞书文档**：[点击查看](https://my.feishu.cn/docx/UaK4dOMLQoZwVoxcMqfcTKFxnud)

---

> **设计原则**：每天一个点、可追溯、不重复、面向积累。即使单次分析体量不大，坚持 3~6 个月也将形成一个覆盖核心子系统的个人内核知识库。
