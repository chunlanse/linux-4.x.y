# Linux 内核源码每日学习工作流（Agent Rules）

> 本文件是 Trae 项目规则：每日触发时，Agent 必须严格按以下 Rules 执行。
> 配套 Skill：`linux-kernel-daily-study`（优先调用该 Skill，以本文件作为项目级覆盖配置）。

## 0. 触发方式

- **手动触发**：「开始今天的内核学习」/「每日内核源码分析」。
- **定时触发**：在 Trae 定时任务中配置每日 `09:00 (Asia/Shanghai)`，任务提示词固定为：
  > 读取 `.trae/rules/kernel-daily-study.md`，执行今天的 Linux 内核源码每日学习，并推送到飞书。

## 1. 配置

| 配置项 | 值 |
|--------|-----|
| `KERNEL_SRC_PATH` | `/root/linux-stable` → `/root/kernel-src/linux-4.19.325`（linux-4.19.325，4.x.y LTS） |
| 源码获取（缺失时） | `curl -L https://mirrors.tuna.tsinghua.edu.cn/kernel/v4.x/linux-4.19.325.tar.xz -o /tmp/k.tar.xz && mkdir -p /root/kernel-src && tar -xf /tmp/k.tar.xz -C /root/kernel-src && ln -sfn /root/kernel-src/linux-4.19.325 /root/linux-stable` |
| `ARCHIVE_ROOT` | `/workspace/daily/` |
| 子系统权重 | `mm/` 35%，`kernel/sched/` 30%，`drivers/` 20%，`fs/` 15% |
| 飞书推送目标 | 用户本人（`ou_f0a8c080cedb2a5b307a5b6d1e1dba15`，赵德超）；也可改为群 `--chat-id` |
| 推送幂等键 | `kernel-daily-YYYYMMDD` |

## 2. Rule 1：不重复地随机选取

1. 构建 `ANALYZED_SET`：
   - 扫描 `/workspace` 下所有 `*.md`，匹配 `{子系统}/{源文件名.c|.h}/{函数名}.md`（排除 `README.md`）；
   - 合并 `/workspace/daily/INDEX.md` 中已记录条目。
2. 从 `KERNEL_SRC_PATH` 用 `ctags -R --c-kinds=f -f /tmp/tags_<sub> <sub>` 提取函数候选；无 `ctags` 时用正则 `^[a-zA-Z_].*\bname\s*\(` 兜底。
3. 过滤：移除 `ANALYZED_SET` 中的同名函数；排除 `main/init/exit` 等样板名与 `COMPAT_SYSCALL_DEFINE*` 宏。
4. 核心度评分：非 static +3；`do_/sys_/vfs_/__alloc/__free/kthread_/…` 前缀 +3；`_alloc/_free/_map/_unmap/_init/…` 后缀 +2；长度 ≥8 +1。仅保留 score ≥5 的候选。
5. 按权重抽取子系统，再在候选池中伪随机（`random.seed(os.urandom(32))`）选 1 个目标。
6. 记录 `TARGET = {name, file, line_start, line_end, subsystem, type}`；若用户显式指定函数，则跳过随机，但需校验未分析过。

## 3. Rule 2：固定中文解读模板

输出必须包含以下章节：

1. **功能作用**：角色、解决的问题、典型调用场景。
2. **关键数据结构**：涉及的 `struct` / `enum` / 全局变量 / per-cpu 变量，给出核心字段与头文件路径。
3. **核心逻辑流程图**：Mermaid `flowchart TD` + 3~8 条决策点说明。
4. **调用关系**：4.1 调用者表（≥3~5 个，含文件:行号与场景）、4.2 被调用者分类（核心/辅助/宏内联）、4.3 Mermaid 调用图。
5. **易错点 / 边界场景 / 设计权衡**：3~6 条（锁、内存序、gfp、失败回滚、跨架构差异）。
6. **附录：核心源码片段**（去样板，保留关键注释）。

## 4. Rule 3：归档 + 推送

### 4.1 归档（双写）

- 主归档：`/workspace/daily/YYYY/MM/YYYY-MM-DD/<subsystem>_<name>.md`（子系统中的 `/` 替换为 `_`）。
- 更新：`/workspace/daily/INDEX.md`（日期倒序）、`/workspace/daily/by-subsystem.md`、`/workspace/daily/progress-stats.json`。
- 子系统副本：`/workspace/<subsystem>/<源文件名>/<name>.md`；若该目录 `README.md` 存在函数索引表，则追加一行（无表格则不改动）。

### 4.2 推送飞书

```bash
# 正文（Markdown 摘要，含目标/功能/结构/流程/调用/易错点/归档路径）
lark-cli im +messages-send --user-id ou_f0a8c080cedb2a5b307a5b6d1e1dba15 \
  --markdown @/tmp/feishu_msg.md --idempotency-key kernel-daily-$(date +%Y%m%d)

# 附件（完整 Markdown 笔记）
cd /workspace/daily/YYYY/MM/YYYY-MM-DD && \
lark-cli im +messages-send --user-id ou_f0a8c080cedb2a5b307a5b6d1e1dba15 \
  --file <subsystem>_<name>.md
```

- 推送前先 `--dry-run` 校验参数与内容。
- 推送失败时保留归档，重试 ≤3 次；仍失败则在最终回复中注明错误，不丢弃分析结果。

## 5. 异常与降级

| 异常 | 处理 |
|------|------|
| 源码缺失 | 按第 1 节命令从清华镜像拉取；失败则报告并中止 |
| 子系统候选耗尽 | 打印覆盖率，降级到下一优先级子系统；全部耗尽则改选次级函数 / Kconfig / 关键注释块 |
| 读取失败 | 跳过候选，重选 ≤3 次 |
| Mermaid 不可渲染 | 同时给出 ASCII 流程图兜底 |
| 用户要求复习旧函数 | 直接读取归档，不重复生成；深化则产出 `_v2.md` 并在 INDEX 标注 |

## 6. 每日完成标准

- [ ] 选中目标未在 `ANALYZED_SET` 中
- [ ] 六段式中文解读完整
- [ ] 主归档 + 子系统副本 + 三个索引文件已更新
- [ ] 飞书收到正文与附件（记录 `message_id`）
- [ ] 对话回复包含目标、1~2 句功能概括、归档绝对路径、流程图、累计进度
