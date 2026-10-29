# EvoTest + ACE + JitRL：框架探索、部署与接入说明

核查日期：2026-10-29。当前目标是理解与搭建框架，尚不接入 DCIM。

## 0. 这份交付的完成范围

这是经过源码审计的部署辅助包和接口教学骨架。它不包含第三方完整仓库，也不是已经完成真实模型调用的三框架集成版。

已完成：官方仓库核对、固定源代码提交、核心函数和依赖审计、EvoTest 后端地址补丁、启动前检查和基线启动脚本、组合接口与离线演示、ChipMEM 官方合成样例验证。

尚未完成：完整依赖安装、真实 Jericho + LLM 运行、真实 ACE/JitRL 嵌入 EvoTest、MemRL/ChipMEM 插件接入、论文性能复现。

本次执行环境缺少 openai、jericho、tiktoken 等依赖，shell Git 网络代理不可达。核心源码经 GitHub 连接器读取，部分源码快照用于审计；不能将其当作完整 checkout。没有使用 API 凭据或进行付费模型调用。

## 1. 官方仓库与部署形态

| 方法 | 官方仓库 | 部署形态与当前用途 |
|---|---|---|
| EvoTest | https://github.com/yf-he/EvoTest | Python 源码脚本，Jericho 环境；作为主循环 |
| ACE | https://github.com/ace-agent/ace | 源码目录 uv sync；抽取 Reflector/Curator，不再运行第二个主循环 |
| JitRL | https://github.com/liushiliushi/JitRL | Jericho / WebArena 两套研究入口；抽取动作候选、经验估计与选择 |
| MemRL | https://github.com/MemTensor/MemRL | MemoryService 与独立 benchmark runners；未来记忆效用插件 |
| ChipMEM | https://github.com/aalrabah/ChipMEM | 标准库运行核心、合成 CLI、工具反馈适配器；未来验证与统计记忆插件 |
| GEPA | https://github.com/gepa-ai/gepa | 可导入优化库；未来外层优化对照 |
| SkillOpt | https://github.com/microsoft/SkillOpt | 训练/评估脚本与可导入包；未来离线技能优化对照 |

完整 SHA 在 repos.lock.json。该文件只固定源码，不是 Python 依赖锁文件。成功安装后再保存本机 Python 版本、pip freeze 或 uv.lock、模型服务和实际模型 ID。

## 2. 先运行什么

先用 EvoTest 的 Detective/Jericho。EvoTest 与 JitRL 都有 Jericho 路径，便于对齐状态、动作、轨迹和反馈。暂不部署 WebArena 的浏览器/容器任务，也不安装 EDA。

建议使用 Ubuntu、WSL2 或 Linux 服务器。EvoTest 首轮可选 Python 3.11；ACE 仓库的 .python-version 是 3.12，先用独立环境学习其组件。无需为了远程模型 API 在本机部署大模型；本地 embedding 和各 benchmark 的额外资源另行配置。

### 2.1 获取固定源码

解压本包，进入 agent-framework-lab：

```bash
python3 scripts/bootstrap_sources.py --plan
python3 scripts/bootstrap_sources.py --only EvoTest ACE JitRL --dest upstream
```

bootstrap 只克隆和 checkout 固定提交，不安装依赖、不调用模型、不修改远程仓库。已有目录只有 origin 和 HEAD 都一致才保留；不一致会停止，避免覆盖已有工作。

### 2.2 部署 EvoTest 原始基线

```bash
cd upstream/EvoTest
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements_rag.txt
python -m pip install jericho tiktoken python-dotenv scikit-learn
python main.py --help
```

Python 3.10+ 是上游要求，3.11 是本说明的实验环境建议，并非本次已完成安装验证。Jericho 若需要本机编译，应按其安装错误补足构建工具。

EvoTest 没有 pyproject.toml/常规打包入口，不要对它直接运行 pip install -e .；也不存在 requirements.txt。scikit-learn 是补充依赖：evaluation.py 无条件导入 rag_agent.py，后者导入 sklearn，即使选择 our Agent 也需要它。

完整 clone 已带 jericho-games/ 下的 Detective 等 ROM。审计用的部分源码副本没有 ROM，不可用它替代完整 clone。

### 2.3 配置模型服务

原版 src/openai_helpers.py 读取 OPENAI_API_KEY，但 base_url 写死为 https://openrouter.ai/api/v1。只设置 OPENAI_BASE_URL 不起作用。

如果使用原版默认后端，OPENAI_API_KEY 应是对应 OpenRouter 服务的 key。如果要用其他 OpenAI-compatible 服务，先从本包根目录运行：

```bash
python3 scripts/patch_evotest_backend.py --repo upstream/EvoTest --dry-run
python3 scripts/patch_evotest_backend.py --repo upstream/EvoTest
```

它只将后端地址改为读取 LLM_BASE_URL，默认地址仍是 OpenRouter；保存原件且幂等。此补丁不是 Azure SDK 适配，不保证任意后端支持原仓库的所有参数。

复制本包 .env.example 到 EvoTest 的 .env，并自行填写 OPENAI_API_KEY 和必要的 LLM_BASE_URL。切勿提交实际 .env。Actor 与 Evolver 的模型 ID 由当前 shell 显式设置：

```bash
export EVOTEST_ACTOR_MODEL='填写当前服务可用的Actor模型ID'
export EVOTEST_EVOLVER_MODEL='填写当前服务可用的Evolver模型ID'
```

不要无意沿用仓库较旧的默认 Evolver 模型。服务地址、key 和模型 ID 必须属于同一个实际可用后端。若要让两个角色分别使用不同后端，需要下一步的统一模型客户端改造；本补丁仅替换共同地址。

### 2.4 检查并运行两轮短任务

回到本包根目录，保持 EvoTest venv 已激活：

```bash
python scripts/preflight_evotest.py --repo upstream/EvoTest --game detective --check-imports
bash scripts/run_evotest_baseline.sh --dry-run upstream/EvoTest
bash scripts/run_evotest_baseline.sh upstream/EvoTest
```

也可按 scripts/NOTES.md 用 EVOTEST_PYTHON 指定 venv 中 Python 的绝对路径。脚本默认两轮、每轮 20 步，并创建独立输出根目录。这只检验状态—动作—环境反馈—演化的链路，不是论文性能实验。

也可直接在 EvoTest 根目录运行：

```bash
python main.py \
  --game_name detective \
  --rom_path jericho-games \
  --agent_type our \
  --llm_model "$EVOTEST_ACTOR_MODEL" \
  --evolution_llm_model "$EVOTEST_EVOLVER_MODEL" \
  --eval_runs 2 \
  --env_step_limit 20 \
  --output_path output/baseline_001
```

每个独立实验使用新 output_path。原代码的跨轮记忆目录不含每次运行的时间戳，同一根目录可能复用此前经验。

原版状态提取器直接 exec 模型生成的 Python。首阶段应使用隔离实验环境；后续组合实现建议先固定提取器，再加入有超时的隔离执行。后端补丁不会改变这一行为。

## 3. 源码与论文必须分开记录

### 3.1 EvoTest 当前公开代码

固定提交：f92474ce83c7aec69e45c30ccfaf2b69e66823de。

- calculate_ucb 使用节点单次 score，加上按树深度、总节点数和子节点数计算的探索项；不是论文配置多次运行均值与访问次数的同一个公式。
- start_episode 从已有节点选父节点，再演化一个子节点。
- _evolve 主要返回新 prompt 和 extract_state 代码；未按论文完整结构实施每轮温度 JSON、记忆 JSON 等变更。
- 成功记忆在工具步反馈时由分数增量写入；失败记忆由循环/停滞启发式生成。
- _format_game_history 未把已保存的 reward/score 显式格式化给 Evolver，组合时应补成结构化轨迹。
- CLI seed 并未在已读 env.py 路径中显式传给底层 FrotzEnv；不能仅凭存在 seed 参数声称完全可复现。

源码：
https://github.com/yf-he/EvoTest/blob/f92474ce83c7aec69e45c30ccfaf2b69e66823de/src/our_agent.py
https://github.com/yf-he/EvoTest/blob/f92474ce83c7aec69e45c30ccfaf2b69e66823de/src/evaluation.py
https://github.com/yf-he/EvoTest/blob/f92474ce83c7aec69e45c30ccfaf2b69e66823de/src/env.py

先保留 upstream_tree 作为基线；以后实现 paper_bandit 时独立命名、独立对照。

### 3.2 JitRL 当前公开代码

固定提交：143d22185d95fbf633a0befe6861d5e8b732543b。

- README 提 OPENROUTER_API_KEY，Jericho 对话代码实际读 OPENAI_API_KEY，base_url 固定 OpenRouter。
- retrieve_similar 当前强制向量检索，依赖 faiss-cpu。
- embedding helper 读取 OPENAI_API_KEY2，直连 OpenAI embedding；它和对话后端不是同一个配置入口。
- verbalized 模式仍传 top_logprobs，helper 启用 logprobs=True；要兼容无 logprobs 后端，应只在 logit 模式请求它。
- upstream_score 实际做 normalized_prob + weighted_normalized_advantage。logit 模式先 exp(logprob)，并非直接在原始 logit 上做论文公式。
- 若实现 paper_logit，应将先验表示为真正的 logits 或 log probabilities；口头置信分先归一化并取 log，再加 beta * advantage。它是组合工程的适配模式，不冒充原仓库算法完全复现。
- 接入时关闭其 update_guiding_prompt；避免与 EvoTest/ACE 多方改写策略。
- use_valid_actions 默认开启，与 EvoTest 对照时必须保证双方获得相同动作信息。

源码：
https://github.com/liushiliushi/JitRL/blob/143d22185d95fbf633a0befe6861d5e8b732543b/Jericho/src/jitrl_agent.py
https://github.com/liushiliushi/JitRL/blob/143d22185d95fbf633a0befe6861d5e8b732543b/Jericho/src/openai_helpers.py
https://github.com/liushiliushi/JitRL/blob/143d22185d95fbf633a0befe6861d5e8b732543b/Jericho/src/cross_episode_memory.py

## 4. 组合架构：EvoTest 是唯一主循环

这部分是工程设计建议，尚不是上游现成插件。

| 组件 | 唯一责任 | 不负责的部分 |
|---|---|---|
| EvoTest controller | episode 生命周期、局部配置演化、候选选择 | 不直接覆盖全局 ACE |
| Actor | 按配置与相关经验提出动作候选 | 不维护另一个训练/测试主循环 |
| ACE Reflector/Curator | 将轨迹经验整理为版本化全局 playbook | 不代替动作选择器 |
| JitRL ActionSelector | 用动作先验与历史回报估计选择动作 | 不同时修改主提示词 |
| MemRL（预留） | 检索与使用后记忆效用更新 | 不把记忆 Q 当作动作 Q |
| ChipMEM（预留） | 工具结果统计、独立验证通过后的技能提炼 | 不用模型自评替代验证 |

### 4.1 总 ACE 应怎样维护

“总”是统一管理，而非无条件把所有轨迹塞进每次上下文。

- 分为通用策略、任务家族策略、任务特定经验；检索/注入要带 scope。
- 只有 Curator 提交全局规则更新；Evolver 和其他模块提出候选经验和证据。
- Actor 在一个 episode 使用不可变 snapshot；初期更建议一个候选比较批次共享同一 snapshot。
- 比较批次结束后再提交新 playbook。记录 config_id、playbook_version、selector_version、task_id、memory_snapshot_id。
- 不把上下文已经变化的配置成绩无条件混成同一个稳定 UCB 均值。

### 4.2 复用 ACE 的组件，不嵌套 ACE.run()

官方 ACE.run() 自带 Generator 和 offline/online 循环。EvoTest Actor 可以承担 Generator 的角色。

应适配：

- ace/core/reflector.py：Reflector.reflect(...)
- ace/core/curator.py：Curator.curate(...)
- playbook_utils.py：apply_curator_operations(...)

输入映射：任务 → question；可观察轨迹 → reasoning_trace；终局结果 → predicted_answer；环境得分/错误 → environment_feedback；实际注入的规则 ID → bullets_used。无标准答案的运行时实验设置 use_ground_truth=False。

这不是要求输出模型私有思维；记录实际可获得的消息、操作与工具反馈即可。

ACE 含根目录绝对导入 utils/logger 等。不要把三个仓库根目录一起塞进 sys.path；可先用独立进程适配，或在研究分支中整理为包内导入。Reflector/Curator 接受现成 api_client，适合未来统一客户端。

### 4.3 JitRL 接入 Actor 的真实位置

EvoTest 的 generate_action 目前只生成一个最终动作。必须拆开：

1. 共享 StateAdapter 提供状态。
2. CandidateGenerator 产生候选和先验。
3. ActionSelector 检索历史回报，计算动作优势。
4. 选择一个动作并交给环境。
5. 保存真实 Transition。
6. episode 结束时计算/估计回报，写回经验。

不能把 JitRL 当作一段额外提示词，也不宜在 Actor 中嵌套整个 JitRLAgent 生命周期。

### 4.4 源码修改落点

| EvoTest 文件/函数 | 接入内容 |
|---|---|
| OurAgent.start_episode | 固定 playbook/memory scope/版本，选择本轮配置 |
| OurAgent.get_prompts | 注入当前 ACE snapshot 的相关条目 |
| OurAgent.generate_action | 候选生成、先验、JitRL selector、最终动作 |
| evaluation.run_game_episode 的 env.step 后 | 统一 Transition/ToolOutcome 事件 |
| OurAgent.end_episode | 汇总轨迹，更新动作经验，未来更新使用过的记忆效用 |
| OurAgent._evolve | 局部策略更新，并向 ACE 提交经验提案 |
| CrossEpisodeMemory | 逐步替换成有 scope/版本/来源的存储接口 |

## 5. 后续接口预留

integration/contracts.py 与 offline_contract_demo.py 是纯标准库教学骨架。运行：

```bash
python3 integration/offline_contract_demo.py
```

它只展示快照固定、候选评分和提交新版本。候选/回报由演示代码给定，无模型调用，不是三框架集成成功或性能提升的证据。

MemRL 预留 MemorySelector 和使用反馈接口。相似度负责相关性，memory_utility_q 表示记忆被使用后的效用，action_q 表示动作价值，node/config score 表示配置运行成绩。四种数值单独保存。

实际参与效用更新的是已注入/使用的记忆 ID，不是全部被召回候选。接原仓库时注意：

- experiment.enable_value_driven 默认 false。
- update_values 的布尔化逻辑不适合直接传连续 reward；使用明确接收数值的 update_value 或自己的适配。
- retrieve_query 和 retrieve_value_aware 是不同代码路径，应固定一种并记录版本。

ChipMEM 预留 before_tool_call / after_tool_call 和 verified_episode 接口。只在独立验证通过后提炼可复用技能。其原生 learn 需要 run_harness 产生的完整性封装 verdict，教学骨架的布尔示例不能直接冒充该凭证。before hook 的建议不能被误说成已拦截了当次操作。

## 6. 各仓库独立部署入口

### ACE

```bash
cd upstream/ACE
uv sync --python 3.12
```

不要执行 pip install ace 来替代这个研究仓库。先阅读 ace/core/reflector.py 与 curator.py；不必先初始化 AppWorld submodule。README Python 示例中的 false 应为 False。

### JitRL

```bash
cd upstream/JitRL/Jericho
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install jericho openai tiktoken numpy python-dotenv faiss-cpu
```

这是依据 import 审计整理的起点，并未在本次环境完成依赖解析。正式运行前还要修正上文后端、embedding 和 logprobs 路径；不得把本段当作已验证的一键启动。

### MemRL（暂不装进主环境）

官方 README 用 Python 3.10 的独立环境安装 requirements.txt；完整依赖包含 MemoryOS、torch、transformers、ALFWorld、BrowserGym、Docker 等。未来只抽取 MemoryService 时，先审计核心 pyproject，再选择独立环境/后端适配。当前可阅读 memrl/service/memory_service.py、value_driven.py。

### ChipMEM 合成环境（可单独学习）

```bash
python3 scripts/bootstrap_sources.py --only ChipMEM --dest upstream
cd upstream/ChipMEM
python3 main.py validate --config experiments/config.example.json \
  --state-directory runs/first-state --output-directory runs/first-output
python3 main.py run --config experiments/config.example.json \
  --state-directory runs/first-state --output-directory runs/first-output
```

核心仅标准库，合成适配器不要求模型/API/EDA。使用新的输出目录。公开仓库不含论文全部原始结果、私有 agent、商业工具配置；合成成功不等于论文结果复现。

本次验证得到预期的 1 PASS、1 FAIL；只有 PASS 创建技能，随后任务检索复用；共 6 次工具结果统计更新。详见 verification/optional_audit.json。

### GEPA 与 SkillOpt（后续对照）

GEPA 在独立环境执行 pip install gepa，或固定源码后 pip install -e .。真实优化还需要反思模型和任务评价器。

SkillOpt 在独立源码环境执行：

```bash
python -m pip install -e ".[searchqa]"
python scripts/materialize_searchqa.py
python scripts/train.py --config configs/searchqa/default.yaml --out_root outputs/searchqa_first_run
```

需先配好目标/优化器模型服务。当前 main 的 Sleep 是后续扩展，和论文训练循环分别理解。首阶段不让 GEPA/SkillOpt 与 ACE 同时改写同一份规则。

## 7. 阶段顺序与验收

1. EvoTest 原始基线：能完成短 Jericho 调用链，日志含动作与环境反馈。
2. 统一事件和状态：Transition、episode result、配置/记忆版本可追溯。
3. 接 ACE：全局规则单一写入，episode/比较批次快照固定，下一轮可读取新版本。
4. 接 JitRL：候选来源、先验、动作价值、最终选择都可检查；关闭它的独立 prompt 演化。
5. 可选 MemRL：仅对实际使用记忆更新效用。
6. 可选 ChipMEM：工具事件和验证后技能提炼。
7. 框架稳定后替换 EnvironmentAdapter/Evaluator，才进入 DCIM。

每阶段独立输出目录，保持相同任务/动作信息、模型设置和运行预算。source commit、Python 依赖、配置版本与结果一起保存。

## 8. 对阅读笔记的三个术语修正

- JitRL 先产生候选，再以历史经验估计价值并选择当前动作；新轨迹在完成后提供回写经验。不要概括为“先执行当前动作，再评估并选择它”。
- MemRL 的 Q 是经验使用后的效用，相似度是另一项检索信号。
- EvoTest/ACE 的文本更新不是对底座 LLM 进行第二次权重训练；这里适应的是模型外部状态。

## 9. 文件说明

- repos.lock.json：七个源代码版本。
- scripts/：源码获取、前置检查、后端补丁、基线启动。
- integration/：接口教学骨架和无 API 演示。
- configs/architecture.toml：拟议架构配置，不是上游 CLI 可直接读取的配置。
- verification/：本次验证记录及其边界。

第三方代码需按各自仓库许可证使用。本包不分发第三方代码、ROM、用户凭据或论文实验数据。
