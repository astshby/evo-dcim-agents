# evo-dcim-agents

逐篇理解 Agent 论文的机制与实现，再研究它们如何用于 DCIM Macro 层次化物理设计。OpenC² 是阶段性的学习、复现和验证对象。

本仓库追踪研究说明、固定源码清单、部署脚本与验证摘要。七个上游项目保存在本机 upstream/，由清单恢复，不上传第三方完整代码。

- [研究路线与逐篇验收](docs/STUDY_PLAN.md)
- [本地配置与复跑](docs/LOCAL_SETUP.md)
- [进度与证据](notes/PROGRESS.md)
- [此前部署审计说明](docs/DEPLOYMENT_REFERENCE.md)
- [源码版本清单](repos.lock.json)

## 当前范围

源码与环境配置阶段；模型服务稍后填写。EvoTest 是首个部署对象，并非已确定的最终主控制器。
ACE/JitRL/MemRL/GEPA/SkillOpt 当前先供源码阅读，不声称运行环境全部就绪。
ChipMEM 标准库合成样例可以独立运行。

configs/architecture.toml 是此前提出的组合蓝图，integration/ 是手写输入的接口演示；二者都不构成多框架集成或论文效果复现的证据。

## 本地无模型检查

在 WSL 的本项目根目录：

~~~bash
envs/evotest/bin/python scripts/local_smoke.py
~~~

安装步骤见 [配置说明](docs/LOCAL_SETUP.md)。该检查不调用 LLM；完整日志在忽略的 runs/ 下，精选结果见 verification/local_setup.json。
