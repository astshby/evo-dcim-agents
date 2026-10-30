# 项目结构与执行逻辑

## 1. 领域与设计目标

项目研究 AI agents 辅助 DCIM Macro 的结构组织、模块放置及布局布线优化。评价以整体 Macro 为对象，不以某个小模块最小代替全宏最优。专业 EDA 算法负责可执行的数值/几何优化；Codex 提议和完成有边界的工程操作。未来希望将源工艺经验有条件地迁移到另一 PDK，迁移设计意图与工作经验，而非直接复用旧工艺的坐标、规则和通过结论。

当前不具备真实 PDK/EDA。初始化目标是建立正确的数据、调度、更新边界和接口。本文中的“目标体系”不等于代码已经完成。

## 2. 自定义单位（不照搬论文同名术语）

- Work：固定规格/PPA要求、PDK、工具环境、评价标准和预算规则。一个 work 一份配置。
- Session：从选定检查点推进的一轮迭代，包含多个 episode；记忆归属于 work。Session 不复制环境配置，只记起点、使用的文本版本编号及结果。
- Episode：一次有边界的设计操作/声明的组合操作，包括决策、选定动作、执行、检查；允许原意图内的有限修复。
- Step：可观察的 Codex/工具操作。不是 token，不是模型私有推理，也不把“规划层/执行层”硬当成相同的 RL 动作。

设计变更与策略变更是两条线：前者改变电路/布局，后者改变做事方式。连续优化继承选定有效检查点，不必重造整个产品。候选变差不覆盖已有较优设计。

## 3. 主循环

```text
固定 Work 合同
  -> Start Session（冻结 ACE/Skill）
  -> Start Episode（起点 + 紧凑卡片 + 相关经验）
  -> 多策略/经验/专业函数候选
  -> 合法性检查与动作选择
  -> 执行 + step事件 + 工具恢复统计
  -> 独立评价
  -> 采用/保留分支/拒绝/阻塞/待确认
  -> episode卡片、动作记录、经验效用结算
  -> 下一个 episode 或 Close Session
  -> 三元组摘要、候选知识/Skill补丁、验证与发布
  -> 下一个 Session
```

GEPA 采用用户选择的“方式 A”：不同提议策略产生互补操作候选，不是多个 Agent 投票宣布物理正确。SkillOpt 改规程；ACE 整理知识；MemRL 选经验；JitRL 选工程动作；ChipMEM 管工具恢复及成功来源；Evo式控制器管时间边界。这是组件职责，而非七条独立主循环。

## 4. 当前代码分层

| 路径 | 当前内容 |
|---|---|
| `evo_dcim/core.py` | Work/Session/Episode 生命周期、事务、卡片、结算和 Mock 发布 |
| `evo_dcim/policies.py` | 候选合同、有限数值验证、Jit式评分子集、MemRL单步更新、评价、受限文本编辑 |
| `evo_dcim/adapters.py` | Mock执行器、失败关闭的真实EDA占位、Codex工作区/CLI边界、Protocol |
| `evo_dcim/__main__.py` | 手动调度命令与离线 demo |
| `configs/` | 一份work示例、人工候选fixture |
| `skills/` | 种子执行Skill和互补提议Skill，不是优化所得结果 |
| `templates/` | 运行指令、ACE种子、本地开发override模板 |
| `tests/` | 离线行为与边界测试 |
| `docs/` | 开发依据、对话决策、未实现事项 |

## 5. Work 内生成目录

```text
work/<id>/
  work.json                       # 唯一固定配置；变更被拒绝
  state.sqlite3                   # 权威数据，事务内一次结算
  status.json                     # 派生视图
  mem/ACE.md                      # 当前work手册，不能手工中途覆盖
  mem/index.json                  # 案例与效用视图
  mem/statistics.json              # 工具统计与动作记录
  skills/<name>/SKILL.md           # 当前work文本规程
  sessions/S0001/manifest.json
  sessions/S0001/report.md
  sessions/S0001/summary.json      # 策略—行动—效果摘要
  sessions/S0001/E0001/card.json
  sessions/S0001/E0001/context.json
  sessions/S0001/E0001/events.jsonl
  sessions/S0001/E0001/candidates.json
  sessions/S0001/E0001/ranking.json
  sessions/S0001/E0001/evaluation.json
  sessions/S0001/E0001/outcome.json
  dcim/artifacts/D0000/manifest.json
```

现在的 `dcim/artifacts` 只有合成指标清单，不含GDS/DEF。真实设计应放入隔离 sandbox，经独立评价后保留不可变制品；这需要下一阶段适配，不能将一个metadata目录称为设计检查点的完整实现。

SQLite 是单work权威状态；JSON/Markdown是可重建视图。`repair-views` 不重跑工具，也不再次奖励。运行模式是单控制器串行；虽然数据库事务串行化，文件导出尚不支持并发控制器，不能宣称分布式恢复已完成。

## 6. Episode 紧凑状态机

`READY -> PLANNED -> EXECUTING -> CHECKING -> SETTLED`。
`CHECKING -> REPAIR -> EXECUTING` 保持同一动作意图。
评价不可用可到 `BLOCKED` 或 `PENDING`。前者不惩罚物理动作，后者等待更多证据。

卡片只放：意图、起止检查点、选定动作、检查/效果摘要和证据引用。完整日志不默认输入下一轮。当前用固定数量上限（近期3张、相关记忆2条），不是严格token分词预算；后续补 tokenizer/按需展开，不把字符数冒称token数。

动作身份由 `operation + parameters` 规范化哈希确定，来源不参与身份，避免多提议者对同操作重复加票。`state_key` 暂由调用者提供，必须表达当前阶段/问题，不是完整几何状态；真实空间检索尚未实现。

## 7. 最小接口与信任边界

`AgentRunner.prepare/run` 负责进程和报告；`EDAAdapter.capabilities/execute/poll/cancel/evaluate` 为未来真实环境留接口。当前没有Cadence命令封装。不能把LLM提交的报告当成 `evaluate` 的输出。

框架与运行目录分离。Runtime Codex只见批准的上下文，不获得控制器DB路径。准备器不复制PDK或密钥；指令文件与hash检查不是OS级安全隔离，真实执行必须配合权限、进程/作业管理和数据外发审核。

## 8. 继承范围

当前：继续work当前head、从已知checkpoint建立下一session、数据库重开恢复已完成记录。
待实现：中断作业poll/cancel/reconcile、设计依赖失效图、完整fresh/fork/transfer调度、多PDK案例导入。不要自动把一个中断的RUNNING作业重新提交。
