# EvoTest 部署辅助脚本

这些脚本帮助检查、配置和短跑**官方 EvoTest 基线**。它们没有实现 ACE、JitRL、MemRL 或 ChipMEM，也不代表组合框架已经完成。

审计版本：`yf-he/EvoTest` 的 `f92474ce83c7aec69e45c30ccfaf2b69e66823de`（2025-11-03）。

## 1. 获取上游并安装依赖

以下以 Linux / WSL 为例。在用户准备的工作目录执行：

```bash
git clone https://github.com/yf-he/EvoTest.git
cd EvoTest
git checkout f92474ce83c7aec69e45c30ccfaf2b69e66823de
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements_rag.txt
python -m pip install -r /absolute/path/to/agent-framework-lab/scripts/requirements-evotest-extra.txt
```

`python3.11` 是一个明确的示例选择；官方推荐 Python 3.10+。上游没有 `requirements.txt` 或可供 `pip install -e .` 使用的打包配置。`requirements_rag.txt` 仅包含 numpy、openai；补充文件加入 Jericho、tiktoken、python-dotenv，以及上游缺漏的 scikit-learn。

完整上游仓库含 Detective 等游戏 ROM。这里不另外分发 ROM。

## 2. 无 API 的预检

```bash
python /absolute/path/to/agent-framework-lab/scripts/preflight_evotest.py \
  --repo /absolute/path/to/EvoTest --game detective --check-imports
```

默认只检查文件、Python 语法、依赖可发现性、版本、ROM 头和 Git 提交。`--check-imports` 额外导入依赖包，但**不导入上游 Agent、不开游戏、不读取 `.env`、不读取凭据、不发模型请求**。`--json` 可获得机器可读结果；发现阻塞项退出码为 1。

此检查不下载 tiktoken 编码数据，不验证模型 ID、余额、密钥、网络或 Jericho 与某个 ROM 的完整兼容性。`ready_for_manual_api_run` 只表示这些本地检查通过。

## 3. 可选：把客户端地址改为环境变量

上游把 `base_url` 固定为 OpenRouter，读取名为 `OPENAI_API_KEY` 的密钥。设置 `OPENAI_BASE_URL` 对原始文件不起作用。

先查看精确修改：

```bash
python /absolute/path/to/agent-framework-lab/scripts/patch_evotest_backend.py \
  --repo /absolute/path/to/EvoTest --dry-run
```

应用同一个修改：

```bash
python /absolute/path/to/agent-framework-lab/scripts/patch_evotest_backend.py \
  --repo /absolute/path/to/EvoTest
```

唯一修改是：

```python
base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
```

脚本依据经审计文件的内容哈希检查，兼容 LF / CRLF；未知改动拒绝覆盖。原件保存在 `src/openai_helpers.py.before_llm_base_url`；重复运行无额外修改。补丁本身不读取环境变量或凭据。

实际执行时，可在上游项目的 `.env` 或 shell 环境中配置 `LLM_BASE_URL`、`OPENAI_API_KEY`。默认仍使用 OpenRouter；换端点后需自行选择该端点可用的模型 ID。这项修改只针对使用 OpenAI SDK 兼容协议的端点，不自动实现 Azure 等服务的专有鉴权方式。

## 4. 先预览，再执行短基线

显式指定两个角色的模型，避免静默采用上游默认 Evolver：

```bash
export EVOTEST_ACTOR_MODEL='你的服务商可用的Actor模型ID'
export EVOTEST_EVOLVER_MODEL='你的服务商可用的Evolver模型ID'
bash /absolute/path/to/agent-framework-lab/scripts/run_evotest_baseline.sh \
  --dry-run /absolute/path/to/EvoTest
```

去掉 `--dry-run` 后才会先运行导入预检，再调用上游入口：

```bash
bash /absolute/path/to/agent-framework-lab/scripts/run_evotest_baseline.sh \
  /absolute/path/to/EvoTest
```

它固定使用 **2 个 episode、每轮最多 20 步**，只用于检查执行链路。每次实际运行使用 `mktemp` 创建独立 output 根，避免上游跨运行共享 `mem.jsonl` 影响对照。实际运行会调用配置的 LLM 服务并产生其费用；预览和预检不会调用服务。不会自动运行上游 `pytest`，因为其测试可能依赖真实 LLM 服务。

可选环境变量：`EVOTEST_PYTHON`、`EVOTEST_GAME`、`EVOTEST_ROM_DIR`、`EVOTEST_OUTPUT_PARENT`。前两项默认为 `python`、`detective`。默认执行 Python 来自当前激活的环境。

## 5. 验证范围与后续修改边界

本次已在临时源文件副本上验证：补丁只替换目标字段、原件保留、重复执行幂等、未知文件拒绝、CRLF 保持、dry-run 不修改文件；同时验证 Python 语法、shell 语法、短跑命令参数与上游 parser 的一致性。原上游研究副本未被修改。

当前执行环境缺少 openai、tiktoken、python-dotenv、jericho；未运行真实游戏或任何付费 API，因此**没有完成端到端部署验证**。依赖安装也未在本环境完成。

后续组合框架需另行修改动作候选生成、统一轨迹事件、ACE 快照与版本、动作价值选择、配置评分以及记忆接口。这些辅助脚本没有改变上游的树选择算法、跨轮记忆实现、生成代码的 `exec` 方式或环境 seed 接线。

源码依据：[官方 README](https://github.com/yf-he/EvoTest/blob/f92474ce83c7aec69e45c30ccfaf2b69e66823de/README.md)、[客户端](https://github.com/yf-he/EvoTest/blob/f92474ce83c7aec69e45c30ccfaf2b69e66823de/src/openai_helpers.py)、[命令行](https://github.com/yf-he/EvoTest/blob/f92474ce83c7aec69e45c30ccfaf2b69e66823de/main.py)。
