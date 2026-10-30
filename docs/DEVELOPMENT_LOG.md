# 开发记录

## 2026-10-30 — 初始化整合 0.1.0

### 输入与迁移

从用户公开仓库 `astshby/evo-dcim-agents` 的 `main`（基点 `c84891dcd52c6119e51693ec28b9e067b9ac2c08`）检查早期Jericho部署/研究脚手架。按用户授权替换为统一work/session/episode初始化框架，旧内容保留在Git历史，不将旧verification文件视为本次测试证据。保留七个上游固定SHA，新增代码路径与行为差异说明。

### 完成内容

- 固定work合同；session边界文本冻结；episode紧凑状态与设计采用逻辑。
- SQLite权威状态、派生JSON/Markdown、重复结算保护、延迟结果分支处理。
- JitRL公开评分方式的显式子集与MemRL单步效用更新。
- Mock执行/评价、环境失败与设计失败区分、来源隔离和预算检查。
- Codex工作区准备和显式CLI运行接口；开发与运行AGENTS/Skill隔离。
- 受限文本编辑与仅用于测试的Mock发布门。
- 中文README、架构、更新策略、配置、参考来源、状态和完整交接。

### 实际验证（初始化执行环境，不是用户本机）

Python **3.13.5**。下列命令实际执行：

```bash
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m evo_dcim demo --root <new-isolated-directory>
python -m evo_dcim status --work <same-directory>
python -m evo_dcim --help
python scripts/fetch_sources.py --only JitRL MemRL
python -m compileall -q evo_dcim tests scripts
```

结果：**27项unittest通过**；离线demo包含改善/阻塞/设计失败三个episode，最终session关闭、head=D0001、release=0。真实模型调用=0；真实EDA调用=0。测试中假的Codex可执行文件只输出fixture JSON事件，不是模型联调。

测试包括：无覆盖初始化、固定配置、单active session、文本冻结、预算、非法候选、数值边界、成功/失败分类、重复结算、重复step完成、待定结果、迟到旧策略结果不污染新统计、Mock/Real隔离、Mock发布哈希与门控、Runtime/Development指令隔离、未知Codex、固定命令不执行manifest任意argv、数据库重开与视图恢复。

### 发现并修复

初次测试发现Python 3.13 sqlite连接的ResourceWarning；显式关闭连接后重测通过。补充发布后的迟到旧策略结果测试，防止已清空的当前统计再次被旧结果污染。候选输入增加4096字节上限，避免所谓压缩卡片携带无限文本；这不等于精确token预算。

### 没有执行

真实Codex/API/EDA、PDK导入、向量数据库、七仓库完整集成、论文benchmark、真实Skill优化/验证和跨PDK迁移。Shell网络DNS不可用，未能clone远端；源码与仓库核查通过GitHub连接器，源码下载脚本只测试了计划输出。

### 下一可验收目标

先代码审查并增加失败恢复测试；再由开发者在明确授权的环境中完成一次真实Codex上下文/Skill加载与JSON报告验证。真实EDA和发布门另立阶段。具体交接见HANDOFF.md，不要从旧部署脚本继续推断本版能力。
