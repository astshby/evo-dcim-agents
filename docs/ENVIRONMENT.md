# 环境与配置

## 1. 当前支持范围

离线核心：Python 3.11+ 标准库，sqlite3、unittest，无pip依赖。初始化实际测试环境见 `DEVELOPMENT_LOG.md`。建议Linux/WSL；未声称测试过Windows。跨平台路径使用pathlib，Codex超时清理在POSIX使用进程组，其他平台只做进程级停止，不能保证远程EDA作业被取消。

真实执行另需用户已有的Codex CLI及认证、PDK/库、EDA安装和许可证。现在没有真实EDA适配；将 `mode` 改成real不会自动接通工具。禁止Mock静默回退。

## 2. 一份work配置

复制 `configs/work.mock.json` 到自己的配置文件，**初始化前**修改。work创建后，`work.json`与DB里的固定合同进行hash核对，不能原地改变工艺/目标。

字段：`mode`区分mock/replay/real；`pdk/environment`标识环境；`stage/corner`定义可比较阶段；`baseline`是声明的起点指标（不是自动验证的基线）；`objective`是主目标/方向/容差；`upper_bounds`和`required_checks`是硬条件；`limits`是调度与上下文数量上限。

当前指标只是合成数字，没有物理单位、PVT或活动率解释。真实适配前必须扩展这些合同，不能用示例值跑工业结论。新目标/新PDK新建关联work，而不是给session复制完整配置。

## 3. 分步操作

README给出完整离线命令。额外能力：

```bash
# 从现有检查点继续；不指定则沿用当前work head
python -m evo_dcim session-start --work ./work/manual-001 --checkpoint D0000
# 从DB恢复派生JSON/Markdown；不会重跑外部作业
python -m evo_dcim repair-views --work ./work/manual-001
# 查看所有命令
python -m evo_dcim --help
```

`session-close`要求所有episode已结算、阻塞或待确认，不会抹掉EXECUTING。当前没有自动远程job恢复或generic replay runner。

文本更新：先将编辑列表保存为JSON，再使用 `preview-update --work ... --session ... --edits ...` 输出候选。只支持明确target和append/replace/delete。`publish-mock` 还需要独立传入绑定candidate/base哈希的**合成**gate及 `--confirm-synthetic`；见测试中的示例。该接口不是线上可信发布服务，真实发布保持禁用。

## 4. Codex开发指令与运行指令

官方文档核查日期：2026-10-30。

- [AGENTS.md discovery](https://developers.openai.com/codex/guides/agents-md/)：同目录优先AGENTS.override.md，其次AGENTS.md；不是自动把两份都加进去。
- [Non-interactive mode](https://developers.openai.com/codex/noninteractive/)：exec、JSONL事件、output-schema、输出文件与sandbox。
- [Skills](https://developers.openai.com/codex/skills/)：项目 `.agents/skills/<name>/SKILL.md`，支持符号链接；普通根skills目录不自动等于加载入口。

本地开发可选：

```bash
cp templates/AGENTS.override.local.example.md AGENTS.override.md
```

该文件被Git忽略，必须显式保留根AGENTS.md规则。无需复制或修改你的全局 `~/.codex`。

Runtime：准备器复制 `templates/AGENTS.runtime.md` 为新目录的 `AGENTS.md`，把work当前技能快照放进 `.agents/skills/`，不复制开发技能、override、数据库或认证文件。指令文件不是权限边界；运行者仍需审查全局Codex配置和已启用工具。

## 5. 先准备，后明确执行

必须先有PLANNED episode。目标目录应不存在，位于开发仓库及work数据库之外，也不要位于其他Git工程/Agent指令父目录下。

```bash
python -m evo_dcim codex-prepare --work ./work/manual-001 --session S0001 --episode E0001 --destination ../evo-dcim-runtime/episode-001
```

只生成工作区和命令，不调用模型。要实际运行（消耗你已有认证对应的额度）：

```bash
python -m evo_dcim codex-run --workspace ../evo-dcim-runtime/episode-001 --timeout 300 --execute
```

CLI显式使用workspace-write、不自动审批请求、结构化报告；不使用danger-full-access或自动登录。它沿用你现有CLI认证/模型配置，不读取或复制auth.json。首次执行前在实际机器检查 `codex exec --help`，CLI版本变化可能要求适配。

当前这只是可执行的进程边界，不是完整Codex-EDA闭环：无设计输入时只能报告blocked；报告不会被自动写成物理评价或settle。每个workspace只允许一次启动，避免重复提交；线程ID、usage、原始事件和stderr留在本地。

**额度限制**：当前只有墙钟超时。CLI内部每次工具调用前拦截、硬token限制、账户剩余额度读取、App Server实时停止均未实现。不能承诺绝不超过某个订阅额度。进程停止也不能保证远程EDA作业已停止。

## 6. 未来EDA适配要求

见 `EDAAdapter`：能力清单、执行、作业查询/取消、独立评价。应由可信server包装固定操作；不用LLM输出直接拼接任意shell。记录设计与报告hash、工具版本、单位/阶段/角、job_id和失效依赖。

预期Cadence Innovus/Virtuoso不是当前依赖安装项。不提供未核实版本的Tcl/SKILL命令，不把开源工具自动当成等价替代。

## 7. 数据与认证

公开Git中不得出现PDK、商业库、许可证、auth.json、token、运行原始日志。默认.gitignore屏蔽work、upstream、runtime、数据库、环境和常见物理制品，但它不是防泄露系统。日志可能含敏感信息，外发前人工/程序脱敏；适配器尚无完备日志脱敏器。

不要在公开仓库CI加载Codex账户认证或真实EDA。CI只应运行离线unittest。不要从其他项目复制密钥。配置只放非秘密标识，私有路径/认证在用户受控环境维护。

## 8. 上游源码

`repos.lock.json`锁定代码版本，不是Python依赖锁。离线核心不依赖这些仓库。

```bash
python scripts/fetch_sources.py --only JitRL MemRL
python scripts/fetch_sources.py --only JitRL MemRL --fetch
```

第一条仅打印计划；第二条明确访问网络，clone并checkout固定SHA。不会pip install、启动模型或修改上游。当前交付环境没有shell DNS，未完成网络clone测试；源码核查使用GitHub连接器。
