# 本地源码与环境配置

执行地点是 WSL Ubuntu。项目保留解压后的目录层级：
/home/hbyasts/4-dcim/agent-framework-lab/agent-framework-lab

## 本轮配置

- 七个 upstream checkout 按 repos.lock.json 固定。
- EvoTest 使用项目内 envs/evotest 的独立 Conda Python 3.11 环境。
- ChipMEM 合成运行只需 Python 标准库。
- ACE/JitRL/MemRL/GEPA/SkillOpt 尚未安装完整运行依赖。
- 用户决定模型服务稍后填写，本轮不创建真实 .env、不调用模型。

## 恢复源码

从项目根目录执行：

~~~bash
python3 scripts/bootstrap_sources.py --plan --only EvoTest ACE JitRL MemRL ChipMEM gepa SkillOpt
python3 scripts/bootstrap_sources.py --only EvoTest ACE JitRL MemRL ChipMEM gepa SkillOpt --dest upstream
~~~

已有 checkout 只有 origin 与 HEAD 一致才保留，不覆盖本地编辑。

## 恢复隔离环境

先确认当前 WSL 已有 Conda。所有命令在项目根目录运行：

~~~bash
conda env create --prefix "$PWD/envs/evotest" --file environment-evotest.yml
envs/evotest/bin/python -m pip install -r requirements-lock-evotest.txt
envs/evotest/bin/python -m pip check
envs/evotest/bin/python scripts/local_smoke.py
~~~

锁文件是成功安装后的 pip freeze，不是跨平台依赖解析保证。Python 和 Linux 条件另见 verification/local_setup.json。
环境目录已存在时先核查，不重新创建或覆盖。没有锁文件的首次配置使用 requirements-evotest.txt。

## 检查边界

local_smoke.py 检查固定源码、依赖、Jericho reset/step、手写接口演示和官方 ChipMEM 合成 fixture。
上游 CLI 导入会加载 tiktoken 编码；首次缓存公开资源可能联网下载，无模型推理或 API 计费。
检查时禁用 dotenv 加载，不调用 Actor、Evolver、ACE Reflector 或 embedding 服务。

原始日志在 runs/，精选摘要在 verification/local_setup.json。历史 verification/validation.json 不能替代本轮本机记录。
Jericho 可运行不等于 EvoTest+LLM 跑通；ChipMEM 合成结果不等于论文成绩。

## 模型服务稍后再配

先确定服务商、端点、Actor/Evolver 模型与预算，再用 .env.example 创建本地 .env。
原版 EvoTest 服务地址写死；后续在独立研究副本应用 scripts/patch_evotest_backend.py，保留 upstream 原始基线。
JitRL 的对话与 embedding 入口需分别核查。详细说明见 docs/DEPLOYMENT_REFERENCE.md。

## Git 范围

追踪说明、配置、脚本、依赖版本与验证摘要。
.gitignore 排除 upstream/、envs/、runs/、真实 .env、论文及缓存。
