# 参考文献、固定源码与吸收情况

原则：实际实现参考锁定源码；论文解释机制。本文不把论文所有功能当作开源版本已提供。没有将第三方完整仓库或原始源码直接vendor进来；两个简单数值机制以项目代码重写，并列明修改。后续直接复制上游代码前必须审查并保留对应许可证和版权。

## 固定来源

完整SHA在 `repos.lock.json`。以下链接固定到该版本，避免main变化影响交接。

| 方法 / 论文 | 仓库固定实现入口 | 项目用途 |
|---|---|---|
| [EvoTest — 2510.13220](https://arxiv.org/abs/2510.13220) | [our_agent.py](https://github.com/yf-he/EvoTest/blob/f92474ce83c7aec69e45c30ccfaf2b69e66823de/src/our_agent.py) | Act/Evolve职责和外层迭代 |
| [JitRL — 2601.18510v4](https://arxiv.org/abs/2601.18510v4) | [jitrl_agent.py](https://github.com/liushiliushi/JitRL/blob/143d22185d95fbf633a0befe6861d5e8b732543b/Jericho/src/jitrl_agent.py) | 候选动作评分与历史回报 |
| [MemRL — 2601.03192v2](https://arxiv.org/abs/2601.03192v2) | [value_driven.py](https://github.com/MemTensor/MemRL/blob/c1b322ca43de36ddf64c6712f89d0095bfc35ce0/memrl/service/value_driven.py) / [memory_service.py](https://github.com/MemTensor/MemRL/blob/c1b322ca43de36ddf64c6712f89d0095bfc35ce0/memrl/service/memory_service.py) | 记忆效用与选择 |
| [ChipMEM — 2609.27067v1](https://arxiv.org/abs/2609.27067v1) | [README](https://github.com/aalrabah/ChipMEM/blob/39c22105acb5e0c18d14e0a9bf6f7ea213fc4cc3/README.md) | 工具反馈、独立验证来源 |
| [ACE — 2510.04618](https://arxiv.org/abs/2510.04618) | [playbook_utils.py](https://github.com/ace-agent/ace/blob/82709de050e1db6e6ef2f07bcb0393560b94992a/playbook_utils.py) / [curator.py](https://github.com/ace-agent/ace/blob/82709de050e1db6e6ef2f07bcb0393560b94992a/ace/core/curator.py) | 增量手册与证据条目 |
| [SkillOpt — 2605.23904](https://arxiv.org/abs/2605.23904) | [training-loop.md](https://github.com/microsoft/SkillOpt/blob/bc0a392ef0a7f92840ec673d80204d34ced169d0/docs/guide/training-loop.md) / [skill.py](https://github.com/microsoft/SkillOpt/blob/bc0a392ef0a7f92840ec673d80204d34ced169d0/skillopt/optimizer/skill.py) | 有界编辑与门控 |
| [GEPA — 2507.19457](https://arxiv.org/abs/2507.19457) | [adapter.py](https://github.com/gepa-ai/gepa/blob/80a62c879ecdeb8741faac72a844dceb1c18691f/src/gepa/core/adapter.py) | 多策略文本候选、统一执行评价接口 |

## 源码与论文边界（必须保留）

### EvoTest

锁定代码主要改prompt和状态提取代码，树选择使用节点分数、深度和子节点数；不等同于论文配置平均回报/访问次数公式。当前项目只保留外层职责，不保留游戏环境、生成Python并exec的路径或原UCB树。Session继承物理检查点是项目扩展。

### JitRL

锁定Jericho `update_scores` 使用归一化概率加归一化优势，权重随episode增加，后续取最大评分。不是论文logit加优势后softmax的逐项实现。

本项目 `policies.jit_scores` 保留这个加法与缩放方式；改变的部分明确是：state_key精确匹配、动作结构化哈希、未知Q取基线、由控制器做有种子探索。没有原先向量检索、历史动作补入、置信token抽取和轨迹LLM评分。单测验证的是该子集的数值，不声称与完整上游runner行为等价。

### MemRL

`QValueUpdater.update` 有reward + gamma*next_q项；本项目使用gamma=0的增量平均。当前本地检索只按state_key筛选，再按效用排序，**不是Two-Phase Retrieval复现**。实际注入的经验共享反馈，不代表单条因果贡献；新生成案例的复用效用从0开始。

### ChipMEM

原版程序性记忆只在独立PASS后新增，统计记忆在每次工具调用后学习，nudge是建议不是硬拦截。当前只有事件位置、来源概念和计数，尚未移植分层贝叶斯统计、完整SKILL注入或完整性封装。不能对外宣称“已集成ChipMEM算法”。

### ACE

锁定默认更新路径只实现ADD，其他操作在TODO；项目提供的replace/delete是自己的文本编辑机制。当前种子条目是规约，不是自动总结得出的成功知识。尚无调用Reflector/Curator的真实适配。

### SkillOpt

源码支持gate开关，slow update另有是否门控的配置。我们仅吸收有界patch与候选验证边界，拒绝session中途修改。`publish_mock`是合成协议测试，不包含原版优化模型、训练epoch和选择集。

### GEPA

上游adapter可以执行任意外部系统并提供轨迹/分数；Pareto主要保留不同任务实例上互补的文本配置，不自动等于版图PPA前沿。方式A（多个提议Skill生成动作，再统一选择）是项目适配。当前只有两个提议Skill种子及候选source字段。

## DCIM执行背景（尚未集成）

[OpenC2官方仓库](https://github.com/OpenC2-official/OpenC2_V1.0) 与 AutoDCIM、SynDCIM、DAMIL-DCIM 提供编译器/模板/专业布局方法的背景，不是本初始化框架的运行依赖。未来应将真实可用能力封装成有输入输出、约束及检查范围的算子，不能凭论文段落伪造函数API。

## 维护办法

每次移植记录：上游commit/路径/函数 -> 本地接口 -> 实际复用/适配/新增 -> 行为差异 -> 测试证据。仓库可运行不等于论文效果复现；对比实验固定任务、阶段、模型、信息和预算。更新上游版本应独立提交，不在同一提交混入大量算法变化。
