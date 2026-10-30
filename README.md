# evo-dcim-agents

面向 DCIM 持续设计优化的 **Codex + EDA 外层控制框架**。借鉴 EvoTest、JitRL、MemRL、ChipMEM、ACE、SkillOpt、GEPA 的现有代码机制；不是把七个完整 Agent 串起来，也不是论文复现。

**当前版本：可测试的初始化框架。** 已实现 work/session/episode 状态、压缩记忆、Mock 闭环、统计结算、session 边界文本更新、Codex 独立工作区和显式 CLI 启动接口。**没有接通真实 PDK/Cadence，没有完整复现七个算法，没有验证真实 PPA 或跨 PDK 迁移。**

## 最快运行

Python 3.11+，核心仅标准库，无需 API key、模型、PDK、EDA 或安装第三方依赖。在仓库根目录：

```bash
python -m unittest discover -s tests -v
python -m evo_dcim demo --root ./work/demo-001
python -m evo_dcim status --work ./work/demo-001
```

Demo 使用全新目录，执行三个明确标记为 synthetic 的 episode（改善、环境阻塞、设计检查失败），不调用模型或 EDA。拒绝覆盖已有 work。查看 `work/demo-001/sessions/S0001/report.md`。

## 手动配置一轮

```bash
python -m evo_dcim init --work ./work/manual-001 --config configs/work.mock.json
python -m evo_dcim session-start --work ./work/manual-001
python -m evo_dcim episode-start --work ./work/manual-001 --session S0001 --intent "测试控制闭环" --state-key floorplan/congested
python -m evo_dcim plan --work ./work/manual-001 --session S0001 --episode E0001 --candidates configs/candidates.mock.json
python -m evo_dcim mock-run --work ./work/manual-001 --session S0001 --episode E0001
python -m evo_dcim session-close --work ./work/manual-001 --session S0001
```

一份 work 配置固定 PDK、环境、评价阶段、目标和预算；初始化后不可原地修改。所有 session 共享它，经验只属于该 work。ACE/Skill 在 session 内冻结，事实和数值统计可以更新。

## 接口与配置文档

- [结构与执行逻辑](docs/ARCHITECTURE.md)
- [更新策略与评价边界](docs/UPDATE_POLICY.md)
- [环境、命令与 Codex 配置](docs/ENVIRONMENT.md)
- [参考论文、源码与当前吸收情况](docs/REFERENCES.md)
- **[开发者与后续 Agent 交接入口](docs/HANDOFF.md)**
- [实现状态和已知限制](docs/IMPLEMENTATION_STATUS.md)
- [开发记录](docs/DEVELOPMENT_LOG.md)

## 三种 Agent 指令不可混用

`AGENTS.md`（复数）是公开的**框架开发**指令；`templates/AGENTS.runtime.md` 是发布给 **DCIM 运行 worker** 的模板。`templates/AGENTS.override.local.example.md` 可由开发者复制为本地 `AGENTS.override.md`，该文件被 Git 忽略。不要把开发 override 发布到运行工作区。

Codex 适配默认只准备工作区和命令；只有显式 `codex-run --execute` 才可能消耗额度。它的报告不是物理评价，不会自动结算 episode。详细说明见环境文档。

## 升级说明

本次用新的最小主循环替代旧 Jericho 部署脚手架；旧版仍保留在 Git 历史 `c84891dcd52c6119e51693ec28b9e067b9ac2c08`。保留七仓库的固定提交清单，不沿用旧文档中的“已安装/已验证”声明。这里的新测试证据只来自本次离线运行。
