# Linux 4.x.y 每日内核学习自动化工作流

每天从 `linux-4.9.y` 的 `mm/`、`kernel/sched/`、`drivers/` 等优先子系统中，加权随机选取一个**尚未分析过**的核心函数，生成中文深度解读，归档并推送到飞书。

## 目录

```text
automation/kernel-daily/
├── config.json          # 源码、归档、飞书、子系统权重
├── prepare_source.sh    # 稀疏克隆/更新 linux-4.9.y
├── kernel_daily.py      # 索引、选题、调用关系、归档、推送
├── run_daily.sh         # 每日编排入口
└── .state/              # 当前选题、prompt、消息草稿（gitignore）
```

分析结果同时写入：

- 主归档：`daily/YYYY/MM/YYYY-MM-DD/<subsystem>_<func>.md`
- 子系统就地归档：`<subsystem>/<source-file>/<func>.md`
- 索引：`daily/INDEX.md`、`daily/by-subsystem.md`
- 统计：`daily/progress-stats.json`

## 快速开始

```bash
cd /workspace
automation/kernel-daily/run_daily.sh source   # 首次执行会稀疏克隆内核源码
automation/kernel-daily/run_daily.sh prepare  # 选题 + 生成 prompt
# Agent 读取 .state/current-prompt.md，写入 .state/current-target.json 中的 report_path
automation/kernel-daily/run_daily.sh finish   # 归档 + 推送飞书
```

一次性完成（需要可读取 stdin、把报告写到 stdout 的 Agent CLI）：

```bash
KERNEL_DAILY_AGENT_CMD='your-agent-cli --print' \
  automation/kernel-daily/run_daily.sh run
```

`prepare` 会生成 `.state/current-prompt.md`，其中包含目标函数的源码上下文、已解析的调用者、直接调用的函数和固定输出模板。语义分析由 Agent 完成，确定性工作全部由脚本完成。

## 每日调度

工作流本身不依赖常驻进程。任选一种外部调度方式，每天 09:00 执行：

Trae 定时任务 / 其他 Agent 调度器：

```text
执行 /workspace/automation/kernel-daily/run_daily.sh prepare；
读取 /workspace/automation/kernel-daily/.state/current-prompt.md 完成分析，
写入 current-target.json 的 report_path；
执行 /workspace/automation/kernel-daily/run_daily.sh finish。
```

已有 Agent CLI 的 cron：

```cron
0 9 * * * cd /workspace && KERNEL_DAILY_AGENT_CMD='your-agent-cli --print' automation/kernel-daily/run_daily.sh run >> daily/.state/cron.log 2>&1
```

> 当前沙箱内没有运行中的 cron/systemd，`run_daily.sh` 只提供可被外部调度器调用的入口；在上述环境里需要由 Trae 定时任务或宿主机 cron 触发。

## 选题与去重

`kernel_daily.py` 会扫描 workspace 下已有的 `*.md` 笔记和 README 链接，建立已分析集合；然后按权重 `mm 25%`、`kernel/sched 25%`、`drivers 15%`、`fs 15%`、其余 20% 选择子系统。候选函数来自 `ctags`，static 函数要求文件内调用点 ≥ 3；导出函数、核心命名前缀和热点函数会提高权重。

修改优先级、sparse checkout 目录或飞书目标，编辑 `config.json`。

## 飞书

默认以当前用户身份发送到 `config.json` 中的 `feishu.user_id`。也可设置：

```bash
export FEISHU_CHAT_ID=oc_xxx   # 优先发群
export FEISHU_USER_ID=ou_xxx   # 或发个人
```

推送使用 `lark-cli im +messages-send --markdown`，带日期幂等键，重复运行不会重复发消息。

## 常用命令

```bash
python3 automation/kernel-daily/kernel_daily.py index
python3 automation/kernel-daily/kernel_daily.py status
automation/kernel-daily/run_daily.sh publish
```
