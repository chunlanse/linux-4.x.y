# 每日内核学习 — 自动化工作流设置说明

本目录是一套"每日 Linux 内核源码学习"自动化工作流的产出位置。工作流由以下组件组成：

## 一、目录结构

```
/workspace/daily/
├── daily_kernel_study.sh       # 自动化脚本（可独立运行 / 由 Agent 执行）
├── README.md                   # 本文件
├── INDEX.md                    # 按日期倒序的总索引
├── by-subsystem.md             # 按子系统分类索引
├── progress-stats.json         # 学习进度统计
├── 2026/
│   └── 09/
│       └── 2026-09-30/
│           └── sched_pick_next_task.md   # 今日完整分析
└── ...
```

子系统就地归档同步写入 `/workspace/<subsystem>/<src_file>/<func>.md`。

## 二、运行方式

### 方式 A：手动触发脚本

```bash
# 仅本地归档
bash /workspace/daily/daily_kernel_study.sh --no-lark

# 含飞书推送（需设置 LARK_CHAT_ID）
LARK_CHAT_ID=oc_xxx bash /workspace/daily/daily_kernel_study.sh

# 指定今日目标函数
TARGET=resched_curr SUBSYSTEM_HINT=kernel/sched \
    SRC_FILE=core.c bash /workspace/daily/daily_kernel_study.sh

# 查看已分析的函数清单
bash /workspace/daily/daily_kernel_study.sh --list
```

### 方式 B：在 Agent 会话中触发

直接对我说：「开始今天的内核源码学习」。我会按 linux-kernel-daily-study skill 的工作流执行：
1. 扫描已分析集合
2. 加权随机选取目标（kernel/sched 25% / mm 25% / drivers 15% / fs 15% / 其它 20%）
3. 读取源码、按模板生成中文解读
4. 双写归档
5. （可选）通过 lark-cli 推送飞书摘要

## 三、飞书推送配置

### 1. 选定 chat_id / open_id

先列出你已加入的会话：

```bash
lark-cli im +chat-list --as user --types group
```

把得到的 `chat_id`（`oc_xxx`）记下来。

### 2. 在脚本里固定目标

编辑 `daily_kernel_study.sh`，把：

```bash
LARK_CHAT_ID="${LARK_CHAT_ID:-}"
```

改为：

```bash
LARK_CHAT_ID="${LARK_CHAT_ID:-oc_xxx}"   # ← 填入你的 chat_id
```

或者直接通过环境变量传入。

### 3. 验证

```bash
LARK_CHAT_ID=oc_xxx bash daily_kernel_study.sh
# 预期：飞书收到【每日内核学习 ...】摘要卡片
```

## 四、调度（可选）

如果你希望每天自动触发（例如每天 09:00 Asia/Shanghai），可使用 Trae 的 `schedule` skill：

> 「帮我创建一个每天 09:00 自动运行 `/workspace/daily/daily_kernel_study.sh` 的定时任务，并把摘要推送到飞书 chat_id `oc_xxx`。」

Agent 会用 `Schedule` 工具注册 cron 任务。

## 五、推荐内核源码版本

- 当前默认：`linux-4.19.y`（克隆在 `/tmp/linux-4.19`，已 patch 到 4.19.325）
- 可换为：`linux-5.4.y`、`linux-5.10.y`、`linux-6.1.y` 等，只需在运行脚本前：

```bash
export KERNEL_SRC=/path/to/linux-stable
```

## 六、Skill 引用

工作流以 `linux-kernel-daily-study` skill 为模板，飞书推送用 `trae-remote-official:lark:lark-im` 的 `+messages-send`。