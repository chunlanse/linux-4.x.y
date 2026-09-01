# Linux 内核每日源码学习自动化工作流 - 实施计划

## Task 1: 配置文件与日志基础设施
- **Status**: `pending`
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 创建 `/workspace/scripts/.kernel-daily-config.json` 集中配置：子系统列表与权重、GitHub 仓库信息、归档根目录、飞书推送偏好、重试次数等。
  - 创建 `/workspace/daily/logs/` 日志目录并保证存在性（入口脚本启动时 mkdir -p）。
  - 定义 `ANALYZED_SET` 扫描规则的辅助说明文件（在代码内以注释与函数 docstring 形式体现）。
- **Acceptance Criteria Addressed**: AC-1、NFR-3、NFR-4
- **Test Requirements**:
  - `rule` TR-1.1: JSON 语法合法，`cat .kernel-daily-config.json | python3 -m json.tool` 退出码为 0；关键字段 `kernel_repo`、`priority_subsystems`、`archive_root`、`feishu` 均存在。Evidence: 命令输出。
  - `rule` TR-1.2: 入口脚本 `--dry-run` 成功加载配置并打印三项信息（已分析 X、候选 Y、配置 OK）。Evidence: 脚本 stdout。

## Task 2: ANALYZED_SET 构建器（已学习索引）
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 实现函数 `build_analyzed_set()`：递归扫描 `/workspace` 下所有 `*.md`（排除 `daily/` 与 `.trae/`），从路径 `{subsys}/{srcfile}/{name}.md` 中提取 `(name, subsys/srcfile)` 二元组。
  - 兼容读取已存在 `README.md` 中的函数索引表格（`| 函数名 | ... |`），将其中函数名加入集合。
  - 返回可用于查询的 Python set。
- **Acceptance Criteria Addressed**: AC-2、FR-1
- **Test Requirements**:
  - `rule` TR-2.1: 对已存在的 `mm/page_alloc.c/__alloc_pages_nodemask.md`，返回集合中必须包含键元组 `("__alloc_pages_nodemask", "mm/page_alloc.c")`。Evidence: `python3 -c "from kernel_daily import build_analyzed_set; s=build_analyzed_set(); print(('__alloc_pages_nodemask','mm/page_alloc.c') in s)"` 输出 `True`。
  - `rule` TR-2.2: 集合大小 ≥ 100（基于工作区现有丰富度）。Evidence: `len(s)` 数值输出。

## Task 3: GitHub 源码按需抓取与定位器
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 实现 `fetch_source_file(rel_path)`：从 `raw.githubusercontent.com/novelinux/linux-4.x.y/master/{rel_path}` 抓取源码，带 3 次指数退避重试；失败抛异常。
  - 实现 `locate_definition(source, name, kind='function')`：用正则匹配 `^.*\s*\**name\s*\(`（函数）或 `struct/enum name\s*\{`（结构）定位行号。
  - 实现 `extract_range(source, L, M, ctx=20)`：提取 `[L-ctx, M+ctx]` 行范围片段并记录实际起止行。
- **Acceptance Criteria Addressed**: FR-3、NFR-1
- **Test Requirements**:
  - `rule` TR-3.1: `fetch_source_file("mm/page_alloc.c")` 返回非空文本，且包含字符串 `"This is the 'heart' of the zoned buddy allocator"`。Evidence: 抓取结果 grep 布尔输出。
  - `rule` TR-3.2: `locate_definition(source, "__alloc_pages_nodemask", "function")` 返回正确行号（≥ 4000，参考 linux-4.x 版本）且为整数。Evidence: 返回值与上下文字符串。

## Task 4: 核心候选识别 + 加权随机选择引擎
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 实现 `identify_core_candidates(subdir)`：抓取该子系统目录列表（通过 GitHub API `GET /repos/{owner}/{repo}/contents/{path}`），对每个 `.c/.h` 文件：
    a. 提取 EXPORT_SYMBOL / EXPORT_SYMBOL_GPL 导出的函数名
    b. 匹配命名前缀 `do_`、`sys_`、`__do_`、`vfs_`、`*_init`、`*_alloc`、`*_free`、`*_map`、`*_unmap`
    c. 匹配 `struct <name>` / `enum <name>` 定义（对 .h 更高权重）
  - 实现 `weighted_subsystem_choice()`：按配置权重选子系统；支持子系统覆盖率 ≥70% 降级。
  - 实现 `pick_random_target()`：在候选中过滤 ANALYZED_SET 后随机选定 1 个，返回 TARGET dict（name/file/line_start/line_end/subsystem/type）。
- **Acceptance Criteria Addressed**: AC-2、FR-2
- **Test Requirements**:
  - `rule` TR-4.1: `identify_core_candidates("mm")` 返回列表长度 ≥ 20。Evidence: `len(list)` 输出。
  - `rule` TR-4.2: 连续调用 `pick_random_target()` 5 次，返回结果全部不属于 ANALYZED_SET。Evidence: 5 次结果与已分析集合的成员判断全部 False。

## Task 5: 中文模板化深度分析生成器
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - 实现 `generate_analysis(target, source_snippet)`：按 spec.md FR-4 规定的七大章节输出 Markdown。
  - 「功能作用」：结合源码注释和内核通用语义生成中文解释（基于函数命名模式 + 注释 + 上下文启发）。
  - 「关键数据结构」：解析函数参数类型、返回类型、内部使用的 struct 指针，引用子系统 include 中对应结构文档链接；若无则描述其作用。
  - 「核心逻辑流程图」：构建 Mermaid `flowchart TD`：入口→参数校验→锁/关抢占→核心循环/分支→资源释放→返回；至少 2 条分支路径（含错误返回）。
  - 「调用关系」：
    - 4.1 调用者表：用 GitHub 搜索或 grep 抓取调用点（≥3 条，不足则全部）
    - 4.2 被调用者：从源码片段中提取函数调用按类别分类
    - 4.3 Mermaid `flowchart LR`：3~5 调用者 → TARGET → 3~5 被调用者
  - 「易错点」：从锁使用、GFP mask、失败回滚顺序、命名歧义等维度提取 3~6 条。
  - 「核心源码片段」：去冗保留关键注释。
- **Acceptance Criteria Addressed**: AC-3、AC-7、FR-4
- **Test Requirements**:
  - `rule` TR-5.1: 生成文本包含所有 6 个 `##` 章节标题（同 AC-3 清单），且含两处 Mermaid 块（flowchart TD 与 flowchart LR）。Evidence: grep 计数 ≥ 1 每类。
  - `rubric` TR-5.2: 分析质量；维度同 AC-7；1-5；阈值 ≥ 4；Evidence: 独立审阅评分写入 review.md。

## Task 6: 双写归档与索引更新
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - 实现 `write_archives(target, content, date_str)`：
    a. 主归档：`mkdir -p daily/YYYY/MM/YYYY-MM-DD/` 并写 `{subsys}_{name}.md`
    b. 就地归档：`mkdir -p {subsys}/{srcfile}/` 并写 `{name}.md`（完整内容）
    c. 若 `{subsys}/{srcfile}/README.md` 存在，追加一行 `| 名称 | 摘要 | [笔记](./{name}.md) | YYYY-MM-DD |`
  - 实现 `update_indexes(target, date_str, main_md_relpath)`：
    a. `daily/INDEX.md`：不存在则创建表头，存在则在最上方追加一行（日期倒序，因此插入在第二行紧接表头）
    b. `daily/by-subsystem.md`：按子系统分段维护，在对应子系统段内追加
    c. `daily/progress-stats.json`：更新对应子系统计数 + 写入 `last_run`、`feishu_status`、`feishu_doc_url` 预留字段
- **Acceptance Criteria Addressed**: AC-4、FR-5
- **Test Requirements**:
  - `rule` TR-6.1: 主归档与就地归档的第一章节完全一致（`diff <(sed ...) <(sed ...)` 无差异）。Evidence: diff 退出码。
  - `rule` TR-6.2: `progress-stats.json` 经 `jq '.'` 成功，`.[target.subsystem] ≥ 1` 且 `.last_run == "2026-09-02"`。Evidence: jq 输出。
  - `rule` TR-6.3: INDEX.md 首条数据行包含 2026-09-02。Evidence: `head -10` 输出。

## Task 7: 飞书推送集成模块
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 6
- **Description**:
  - 实现 `push_to_feishu(target, content, date_str, main_md_path)`：
    a. **首选**：调用 lark-doc Skill 创建飞书云文档，标题格式为「【2026-09-02 内核每日学习】{子系统}/{函数名}」，正文为 content 的 Docx 适配格式（Markdown → Docx）；返回 docx URL。
    b. **降级 IM**：若创建 Docx 失败，组装精简摘要（函数、子系统、文件、功能作用 2 句、本地双写路径），通过 lark-im 发给当前用户；同时日志记录失败原因。
    c. **未授权降级**：捕获认证异常后设置 `feishu_status="skipped_unauthorized"` 并返回 None，不中断主流程。
  - 更新 `progress-stats.json` 的 `feishu_status` 与 `feishu_doc_url` 字段。
- **Acceptance Criteria Addressed**: AC-5、FR-6、FR-8
- **Test Requirements**:
  - `rule` TR-7.1: 模块返回的 `(status, url_or_none)` 二元组状态值 ∈ {success, deferred_im, skipped_unauthorized, failed}。Evidence: Python 返回值断言。
  - `rule` TR-7.2: progress-stats.json 中 `feishu_status ∈ {"success","deferred_im","skipped_unauthorized","failed"}`。Evidence: jq 结果。

## Task 8: 入口脚本与幂等逻辑（shell + Python 驱动）
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 7
- **Description**:
  - 编写 `/workspace/scripts/kernel_daily.py`：核心 Python 库，承载 Task 1~7 所有模块。
  - 编写 `/workspace/scripts/kernel_daily_study.sh`：
    a. `--dry-run`：加载配置、构建 ANALYZED_SET、打印候选统计、抓取 1 个测试文件验证网络、退出 0。
    b. `--select-only`：不写文件，仅打印 TARGET dict JSON。
    c. 默认（无参数）：检查当日目录是否已存在 → 存在则打印幂等提示 + 返回已有链接 → 不存在则按 Task 2→3→4→5→6→7 全流程执行 → 打印摘要并返回 0。
    d. 任何非预期异常：捕获、写入日志、返回非 0 退出码与原因。
  - 确保脚本可 `chmod +x` 直接被 cron 调用。
- **Acceptance Criteria Addressed**: AC-1、AC-6、FR-7、FR-8、NFR-2
- **Test Requirements**:
  - `rule` TR-8.1: `bash kernel_daily_study.sh --dry-run` 退出码 0 且输出含「配置加载成功」「已分析」「候选集」三个关键词。Evidence: stdout + $?。
  - `rule` TR-8.2: 连续两次无参数运行：第二次 stdout 包含「今日已分析，直接返回结果」，第二次退出码 0。Evidence: 两次运行的 stdout 和退出码。
  - `rule` TR-8.3: `--select-only` 连续 5 次结果均不在 ANALYZED_SET。Evidence: 5 轮 JSON 的 (name, file) 元组与 analyzed 集合对比脚本退出码 0。

## Task 9: 首次端到端运行（今天 2026-09-02）
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 8
- **Description**:
  - 执行一次完整的 `kernel_daily_study.sh`（无参数），确保所有产物落地。
  - 人工自我核查：主归档内容六大章节、两个 Mermaid 块完整、就地归档同步、INDEX/by-subsystem/progress 已更新、飞书状态合法。
  - 在本次对话中向用户输出摘要（函数名 + 文件 + 子系统 + 功能一句话 + 本地归档链接 + 飞书链接（若成功）+ 进度统计）。
- **Acceptance Criteria Addressed**: AC-8、AC-3、AC-4、AC-5、AC-7
- **Test Requirements**:
  - `rule` TR-9.1: `/workspace/daily/2026/09/2026-09-02/` 目录下存在且仅存在 1 个 `.md` 文件（首日本次），文件头元信息「日期：2026-09-02」精确匹配。Evidence: ls + grep。
  - `rule` TR-9.2: 入口脚本返回码为 0。Evidence: shell 退出码。
  - `rubric` TR-9.3: 端到端体验完整度；维度 = 流程衔接顺畅度、日志可读、摘要输出完整、异常路径兜底；1 仅完成局部步骤/严重断裂；3 跑通但关键体验缺失；5 全部衔接流畅；阈值 ≥ 4；Evidence: 自我核查记录写入 review.md。
