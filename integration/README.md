# 框架接入契约：纯离线教学骨架

本目录用 Python 标准库演示组件之间的数据与职责边界。**它没有集成或运行真实 EvoTest、ACE、JitRL、MemRL、ChipMEM，也没有连接模型服务、游戏或 EDA。**演示中的状态、价值、奖励、总结和新规则全部是手写数据，不代表任何模型效果。

## 运行

在项目根目录运行：

```bash
python3 integration/offline_contract_demo.py
```

需要 Python 3.10+，无需安装第三方依赖。输出明确包含 `model_calls: 0`、`inputs_are_scripted: true`，并展示以下事实：

1. 当前 episode 使用不可变的 playbook v1 快照。
2. 检索命中两条记忆，实际只注入一条；决策记录只标记实际使用的记忆 ID。
3. 两个候选动作带显式 `prior_logit`。用 `z' = z + beta * (Q - V)` 修正后，通过 argmax 选择一个动作，并展示对应 softmax 概率。
4. 分别输出 EpisodeContext、Transition 和结束 Event，以 episode_id 关联本轮配置；可选工具观察器接收结果。
5. EvoTest 角色只提出局部策略；ACE 角色提交全局规则增量，产生 v2。已经开始的 episode 仍读取 v1。

以上流程验证接口关系，不验证学习效果。示例没有 UCB 配置选择、未知动作探索、真正的价值估计训练、跨任务泛化或环境回合管理。

## 职责与真实源码的对应

| 本骨架 | 真实项目接入处 | 需要补充的工作 |
|---|---|---|
| `EpisodeContext`、`LocalStrategy`、`EvoTestEvolver` | EvoTest 的 `src/our_agent.py` 与 `src/evaluation.py` | 接入真实 Actor/Evolver、候选配置和 UCB；记录实际工具轨迹 |
| `ACECurator`、`PlaybookDelta`、`ACEPlaybookStore` | ACE 的 `ace/core/reflector.py`、`ace/core/curator.py`、`playbook_utils.py` | 轨迹适配；调用真实 Reflector/Curator；持久化、版本、唯一写者与提交事务 |
| `CandidateAction`、`ActionValueEstimator`、`choose_action` | JitRL 的 `Jericho/src/jitrl_agent.py` 中 `generate_action()`、`update_scores()` | 候选生成、模型先验、状态编码、回报计算、检索与探索 |
| `MemorySelector`、`MemoryItem.utility`、实际注入 ID | 将来的 MemRL adapter | 用相似度和记忆效用选择经验；只向实际使用的记忆分配反馈 |
| `ToolOutcomeObserver` | 将来的 ChipMEM adapter | 工具类型与错误类型归一化、贝叶斯统计、恢复建议、验证通过后的技能写入 |

`ACEPlaybookStore` 是单一写入职责的示例，不是安全权限系统；真实调度器需要只把提交权限交给 ACE adapter。`expected_version` 防止无意覆盖旧版本，但示例不提供多进程锁或数据库事务。`MemoryItem.utility` 与动作 `q_value` 是不同概念，禁止混用。

候选配置的统计结果还应绑定 playbook、值估计器、记忆快照和任务版本。最容易解释的起点是在一批配置比较期间冻结全局快照，批次结束再接受 ACE 更新。

## 已核查的上游版本

- EvoTest 官方仓库：<https://github.com/yf-he/EvoTest>。本骨架不复制其实现，也未接入其运行循环。
- ACE 官方研究代码：<https://github.com/ace-agent/ace>，核查提交 `82709de050e1db6e6ef2f07bcb0393560b94992a`。
- JitRL 官方研究代码：<https://github.com/liushiliushi/JitRL>，核查提交 `143d22185d95fbf633a0befe6861d5e8b732543b`。

### JitRL 数学与工程差异

当前上游 `generate_action()` 在 verbalized 模式使用 `confidence / 100`，在 logit 模式将 log-probability 用 `exp` 转成概率；`update_scores()` 再把归一化优势加到该概率上。字段虽然命名为 `corrected_logprob`，但这与论文中的原始 logit 加法并不相同。

本示例明确使用 **paper-style logit scoring**：输入必须是 logit 或 log-probability，不能直接传 0–1 概率或 0–100 置信分。示例取 argmax；它不是包含全部探索、检索与信用分配机制的 JitRL 复现。正式代码应分别保留“上游分数模式”与“论文 logit 模式”，避免混淆结果。

### 上游接入前已发现的事项

- JitRL README 使用 `OPENROUTER_API_KEY`，但 Jericho 源码实际读取 `OPENAI_API_KEY` 并固定连接 OpenRouter；embedding 则读取 `OPENAI_API_KEY2` 连接另一服务。
- 当前 JitRL `retrieve_similar()` 强制使用向量检索，需要 FAISS 和 embedding 后端，不能仅根据 README 的 Jaccard 描述配置。
- verbalized 模式仍传 `top_logprobs`，需要按后端能力修正请求。
- 接入 EvoTest 后，应关闭 JitRL 自己的提示词更新，统一由 EvoTest 负责局部策略、ACE 负责全局规则。
- ACE 顶层 `ACE.run()` 自带 Generator 和训练循环；组合时优先适配 Reflector/Curator，而非嵌套第二套完整循环。
- 上游代码包含根目录 `utils`、`logger` 等导入。正式打包需整理命名空间，或用独立进程适配，避免多仓库同名模块冲突。

## 后续实现顺序

先独立运行 EvoTest 原始基线，再接入 ACE 快照读取与 episode 后增量提交，然后接入 JitRL 候选评分。MemRL 与 ChipMEM 暂以接口保留，关闭时不得偷偷更改动作或记忆。各阶段保持同一任务集、模型和运行预算，并分别记录模型、embedding 与工具调用成本。
