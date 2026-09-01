# Linux 内核每日源码学习自动化工作流 - 产品需求文档

## Overview
- **Summary**: 构建一个可每日运行的自动化 Agent 工作流，从 GitHub `novelinux/linux-4.x.y` 仓库中随机选取一个尚未分析过的内核核心函数（优先 mm/、kernel/sched/、drivers/ 等），进行深度中文解读（功能作用、关键数据结构、核心逻辑 Mermaid 流程图、调用关系），并将分析结果按双写策略归档后，自动推送到飞书（文档或消息）。
- **Purpose**: 系统性积累内核源码深度解读知识库，避免重复分析，每日稳步推进学习进度，最终通过飞书触达实现即时学习与团队共享。
- **Target Users**: 个人内核学习者、需要定时触发的自动化计划任务、希望将学习笔记通过飞书归档与分享的用户。

## Goals
- **G-1** 随机选择不重复：每日自动从高优先级子系统中选出 1 个未分析的核心函数/关键结构，确保无重复。
- **G-2** 深度中文解读：每次分析按固定模板输出「功能作用 + 关键数据结构 + 核心逻辑 Mermaid 流程图 + 调用关系 + 易错点」五大版块，并附源码片段。
- **G-3** 双写归档：既按日期归档到 `daily/YYYY/MM/YYYY-MM-DD/`，又就地写入 `{subsys}/{srcfile}/{func}.md` 并维护 INDEX、by-subsystem、progress-stats 索引。
- **G-4** 飞书自动推送：每次运行后自动将完整分析结果创建为飞书云文档（Docx）或发送为飞书消息，并返回可访问链接。
- **G-5** 可定时触发：将完整流程封装为可由计划任务（cron/定时触发）直接调用的入口，无需人工交互。
- **G-6** 首次运行即出结果：本项目交付时必须已成功执行首次完整分析（日期为今天 2026-09-02）。

## Non-Goals
- 不克隆完整内核仓库到本地磁盘（按需从 GitHub 原始文件 API 抓取，除非用户显式要求本地源码树）。
- 不做跨版本 diff/演进分析（聚焦 linux-4.x.y 单版本）。
- 不做自动化正确性测试（分析质量以人工审视和 rubric 评分方式验证）。
- 不构建前端 UI 或 Web 应用（以 CLI + 文件系统 + 飞书为交互面）。
- 不创建用户账户系统（面向当前 workspace 的单用户场景）。

## Background & Context
- 工作区 `/workspace` 已存在大量分析笔记：采用 `{子系统}/{源文件名.c或.h}/{函数名或结构名}.md` 模式组织，覆盖 mm/、fs/、kernel/、include/linux/、init/、ipc/、lib/、net/、security/ 等子系统。
- 已有笔记多引用 `https://github.com/novelinux/linux-4.x.y/tree/master/...` 路径，证实 `novelinux/linux-4.x.y` 为目标仓库。
- 网络访问 GitHub 返回 200，可直接使用 raw.githubusercontent.com 或 GitHub REST API 按需抓取源码。
- 当前 workspace 尚无 `daily/` 日期归档目录、`INDEX.md`、`progress-stats.json`，需要新建。
- 飞书/Lark 插件已在环境中注册，提供 `lark-doc`（云文档创建编辑）、`lark-im`（发消息）、`lark-drive`（云空间管理）等能力。
- `linux-kernel-daily-study` Skill 已定义详细的 6 步工作流（Step1 发现已分析集 → Step2 加权随机选取 → Step3 源码读取 → Step4 模板分析 → Step5 双写归档 → Step6 总结返回），本 spec 在此基础上增加「飞书推送」与「可脚本化执行」两项能力。

## Functional Requirements
- **FR-1 已学习索引构建**：运行伊始，递归扫描 `/workspace` 所有 `*.md`，从路径模式 `{subsys}/{srcfile}/{func}.md` 及潜在的 `README.md` 函数条目表中提取 (函数名, 源文件相对路径) 二元组，构建 `ANALYZED_SET`，保证后续选择不重复。
- **FR-2 加权子系统随机选取**：按优先级列表 `mm/`(25%)、`kernel/sched/`(25%)、`drivers/`(15%)、`fs/`(15%)、其余(`kernel/`、`ipc/`、`net/`、`block/`、`security/`、`lib/`) 共 20%，进行加权随机；最高优先级子系统已覆盖率 ≥70% 时自动降级到下一子系统；在选中子系统中按「核心函数判定标准」（全局导出/static ≥3 调用点/命名前缀 do_|sys_|__do_|vfs_|*_init|*_alloc|*_free|*_map|*_unmap，以及关键 struct/enum）识别候选。
- **FR-3 源码抓取与定位**：从 `https://raw.githubusercontent.com/novelinux/linux-4.x.y/master/{file}` 抓取源文件，支持通过函数名/结构名正则定位行号，并向前后扩展 20 行上下文作为分析片段。
- **FR-4 中文模板化分析**：按固定章节输出：
  1. 元信息头（日期/子系统/源文件行号/类型）
  2. 功能作用
  3. 关键数据结构
  4. 核心逻辑 Mermaid `flowchart TD` 流程图 + 3~8 条决策点解读
  5. 调用关系（调用者表格 ≥3、被调用者分类、Mermaid `flowchart LR` 调用图）
  6. 易错点/边界场景/设计权衡（3~6 条）
  7. 核心源码片段（保留关键注释）
- **FR-5 双写归档与索引维护**：
  - 主归档：写入 `/workspace/daily/YYYY/MM/YYYY-MM-DD/{subsys}_{name}.md`
  - 子系统就地归档：写入 `/workspace/{subsys}/{srcfile}/{name}.md`（完整内容）；若目录存在 `README.md` 则在其中追加索引行
  - 索引更新：新增或更新 `/workspace/daily/INDEX.md`（日期倒序）、`/workspace/daily/by-subsystem.md`（按子系统分类）、`/workspace/daily/progress-stats.json`（各子系统累计分析数 JSON）
- **FR-6 飞书推送**：
  - 首选路径：将完整分析结果创建为飞书云文档 Docx，放置在用户可见「我的空间」或指定知识库（可配置），返回云文档 URL
  - 降级路径：若创建 Docx 失败，则通过飞书 IM 向当前用户发送 1 条精简摘要 + 2 条归档文件绝对路径 + Mermaid 说明
  - 推送日志：在 `progress-stats.json` 的每日条目中记录推送状态与目标链接
- **FR-7 统一可执行入口**：提供 `/workspace/scripts/kernel_daily_study.sh`（或等价的 Node/Python 启动脚本）作为 `cron`/计划任务的单一入口，执行：构建索引 → 选函数 → 读源码 → 分析 → 归档 → 推飞书 → 打印摘要；脚本返回 0 表示成功、非 0 表示失败并打印原因。
- **FR-8 异常处理**：
  - GitHub 抓取失败 ≤3 次重试，仍失败则放弃本次、输出日志并返回错误码
  - 所有子系统核心候选已覆盖时，自动降级至次级函数（static、调用点少、Kconfig、TODO）
  - 飞书权限缺失或未授权：写入归档后打印「飞书推送跳过原因：未授权」并返回 0（归档成功但推送降级为本地）

## Non-Functional Requirements
- **NFR-1 性能**：单次完整运行（含网络抓取、分析写入、飞书推送）在无人工阻塞下 ≤ 10 分钟完成，其中网络抓取阶段 ≤ 2 分钟。
- **NFR-2 幂等性**：同一天多次执行入口脚本不重复创建分析文档；通过 `daily/YYYY/MM/YYYY-MM-DD/` 目录存在性实现幂等（已存在则直接返回已有链接）。
- **NFR-3 可维护性**：所有核心配置项（子系统权重、GitHub 仓库 owner/name/branch、飞书文档父目录、归档根目录）集中在 `/workspace/scripts/.kernel-daily-config.json` 单一 JSON 文件中，修改无需改代码。
- **NFR-4 可观察性**：每次运行生成可读日志到 `/workspace/daily/logs/YYYY-MM-DD.log`，包含：候选集大小、选定目标、抓取耗时、归档路径、飞书推送状态与返回码。
- **NFR-5 中文一致性**：所有面向用户的分析内容、日志错误信息、飞书文档标题与正文均使用简体中文。

## Constraints
- **Technical**:
  - 内核源码来源必须为 `novelinux/linux-4.x.y` 仓库（与现有笔记引用一致），branch=`master`，通过 raw.githubusercontent.com 读取。
  - 飞书能力受限于已安装的 `lark-*` Skills，不得绕过官方 SDK；若认证失败需走 RequestAuthorization 流程。
  - 禁止将 200MB+ 的完整内核仓库 clone 到当前 workspace 磁盘（磁盘和带宽受限环境）。
- **Business**:
  - 本工作流产物不对外公开（飞书文档默认仅创建者可见），不构成任何对外发布物。
- **Dependencies**:
  - 依赖环境可访问 `api.github.com`、`raw.githubusercontent.com`。
  - 依赖飞书 Lark 插件已授权至少 `docx:document:write` 与 `im:message:send_as_bot` scope（或等价权限）；未授权时按 FR-8 降级。

## Assumptions
- **A-1** GitHub raw API 与源码 URL 在运行期间可用，限速窗口足以支持单次运行 ≤100 次 HTTP 请求（典型 5~20 次）。
- **A-2** 飞书插件已安装；若需授权，用户将在首次推送时在对话提示下完成授权流程。
- **A-3** 工作区 `/workspace` 有至少 50MB 可用磁盘用于存放分析笔记、日志、索引。
- **A-4** 计划任务（cron/systemd timer）可在执行环境中直接调用 `/workspace/scripts/kernel_daily_study.sh`。
- **A-5** 「未分析过」判定仅基于当前 workspace 已有 `.md` 文件，不追溯外部历史。

## Acceptance Criteria

### AC-1: 入口脚本存在并可独立执行
- **Type**: `rule`
- **Given**: `/workspace/scripts/kernel_daily_study.sh` 与配套配置文件已创建
- **When**: 在 shell 中执行 `bash /workspace/scripts/kernel_daily_study.sh --dry-run`
- **Then**: 脚本退出码为 0，stdout 输出「配置加载成功」「已分析 X 个函数」「候选集 Y 个」三项信息，且未产生新的归档文件
- **Pass Condition**: 退出码 0 且 stdout 同时包含三个关键词模式
- **Evidence**: `RunCommand` 捕获的退出码 + 原始 stdout

### AC-2: 随机选择不重复（ANALYZED_SET 生效）
- **Type**: `rule`
- **Given**: 工作区已有若干分析笔记（如 `mm/page_alloc.c/__alloc_pages_nodemask.md`）
- **When**: 运行脚本的「只选择不写入」模式：`kernel_daily_study.sh --select-only`
- **Then**: 输出的 TARGET.name 与 TARGET.file 二元组不在已分析集合中（可通过 grep 已存在 md 文件名验证）
- **Pass Condition**: 对随机运行 5 次，全部不重复命中已存在函数
- **Evidence**: 连续 5 次 `--select-only` 的 stdout 列表 + workspace 已有文件列表对比结果

### AC-3: 分析产物覆盖六大章节并含 Mermaid
- **Type**: `rule`
- **Given**: 已成功执行一次完整运行（日期 2026-09-02）
- **When**: 读取 `/workspace/daily/2026/09/2026-09-02/*.md` 主归档文件
- **Then**: 文件同时包含以下章节标题（Markdown `##` 级别）：
  1. `## 1. 功能作用`
  2. `## 2. 关键数据结构`
  3. `## 3. 核心逻辑流程图` 且内嵌 ` ```mermaid ` 代码块，其首句为 `flowchart TD`
  4. `## 4. 调用关系` 且存在 `### 4.1`、`### 4.2`、`### 4.3` 三小节，4.3 内含 `flowchart LR` Mermaid
  5. `## 5. 易错点 / 边界场景 / 设计权衡`
  6. `## 附：核心源码片段`
- **Pass Condition**: 六个章节标题全部存在，且两个 Mermaid 代码块类型正确
- **Evidence**: 文件全文 grep 结果与行号列表

### AC-4: 双写归档与索引一致性
- **Type**: `rule`
- **Given**: 完整运行已成功，主归档位于 `daily/2026/09/2026-09-02/{subsys}_{name}.md`
- **When**: 比对主归档与就地归档 + 三个索引文件
- **Then**:
  a. `/workspace/{subsys}/{srcfile}/{name}.md` 文件存在，且第一章节标题与主归档一致
  b. `/workspace/daily/INDEX.md` 存在并包含「2026-09-02」行，指向主归档相对路径
  c. `/workspace/daily/by-subsystem.md` 存在并包含本次子系统与函数名
  d. `/workspace/daily/progress-stats.json` 为合法 JSON，子系统计数 ≥ 1 且含 `last_run: "2026-09-02"` 字段
- **Pass Condition**: a~d 全部成立
- **Evidence**: 四个文件分别 Read + grep/jq 的输出

### AC-5: 飞书推送成功或优雅降级
- **Type**: `rule`
- **Given**: 完整运行已执行完毕
- **When**: 读取 `progress-stats.json` 中 `feishu_status` 字段与日志
- **Then**: 以下任一情况成立：
  - `feishu_status == "success"` 且 `feishu_doc_url` 为合法 URL（以 `https://` 开头）；或
  - `feishu_status == "deferred_im"` 且日志含「已发送 IM 摘要」；或
  - `feishu_status == "skipped_unauthorized"` 且日志含「飞书未授权，跳过推送」
- **Pass Condition**: 三选一匹配
- **Evidence**: `progress-stats.json` 的 jq 输出 + 日志文件关键行

### AC-6: 幂等性——重复运行不重复产物
- **Type**: `rule`
- **Given**: 2026-09-02 已成功执行一次
- **When**: 再次运行完整入口脚本
- **Then**: 脚本退出码 0，stdout 含「今日已分析，直接返回结果」；`/workspace/daily/2026/09/2026-09-02/` 下 `.md` 文件数量未增加（与再运行前相同）
- **Pass Condition**: 退出码 0 + 幂等提示输出 + 文件计数一致
- **Evidence**: 第二次运行前后 `ls | wc -l` + 退出码 + stdout

### AC-7: 分析质量（中文解读深度与准确性）
- **Type**: `rubric`
- **Dimension**: 分析产物的功能准确性、结构覆盖度、流程图可读性、调用关系完整度、中文表达流畅度
- **Scale**: 1-5
- **Anchors**:
  - 1 = 仅含源码粘贴，未做解读；章节缺失严重
  - 2 = 有章节框架，但功能描述含糊，数据结构未解释，流程图缺分支
  - 3 = 五大章节齐全，功能描述与源码语义基本一致，流程图覆盖主路径
  - 4 = （阈值）数据结构给出核心字段含义，流程图含关键分支与错误路径，调用者表格 ≥ 3 条且场景合理，中文流畅
  - 5 = 达到 4 之外，易错点部分准确指出了竞态窗口/锁选择/gfp mask 语义等至少 1 处真实内核设计权衡，源码片段注释取舍合理
- **Pass Threshold**: >= 4
- **Evidence**: 独立审阅者对主归档 `.md` 的逐条评分结论与理由（写入 review.md）

### AC-8: 首次运行即交付
- **Type**: `rule`
- **Given**: 本项目实现周期内
- **When**: 检查日期目录 `/workspace/daily/2026/09/2026-09-02/`
- **Then**: 目录下至少存在 1 个 `*.md` 分析文件，且 YYYY-MM-DD 元信息字段等于 `2026-09-02`
- **Pass Condition**: 文件存在且元信息匹配
- **Evidence**: `ls` + 文件头部元信息行 grep

## Open Questions
- [ ] 飞书推送的目标形式：默认是「创建独立 Docx」，用户是否需要固定发送到某个群聊或某个 Wiki 知识库节点？（当前默认：创建当前用户可见的 Docx，后续可由 `.kernel-daily-config.json` 配置覆盖）——因定时触发自动执行，采用默认值。
- [ ] 是否需要子系统就地 `README.md` 中的表格追加？（当前 FR-5 要求；若某目录无 README 则跳过并日志记录，不中断流程）
