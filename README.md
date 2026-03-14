# AntiScam Agent System — 智能反诈骗多 Agent 系统

> 一个面向普通用户（尤其是家中老人）的实时诈骗检测系统。通过 5 个协作 Agent 分析微信/邮件中收到的图片，自动识别诈骗内容并推送预警——还能从误判中自我学习，越用越准。

---

## 为什么不用现有框架？

目前主流的多 Agent 框架各有侧重：

| 框架 | 厂商 | 定位 | 本项目为何不用 |
|------|------|------|----------------|
| [Deer-Flow](https://github.com/bytedance/deer-flow) | 字节跳动 | 深度研究型多 Agent 编排 | 设计目标是多轮研究任务，对文件监控+图片 OCR 场景过重 |
| [AgentScope](https://github.com/modelscope/agentscope) | 阿里/ModelScope | 可视化 Agent 流程编排 | 编排抽象层与透明文件夹机制难以低成本集成 |
| [AutoGen](https://github.com/microsoft/autogen) | 微软 | 多 Agent 对话协作 | 对话驱动模式与单向流水线场景不符 |
| [LangChain](https://github.com/langchain-ai/langchain) | LangChain | Chain/Tool 抽象 | 过度封装，调试诈骗案例时每步链路不透明 |

**本项目选择直接 Python 实现**：每个 Agent 就是一个 Python 类，每步输出写入 JSON 文件，逻辑完全透明。核心依赖只有 `openai` SDK（调用 GLM-4.6V 和 Qwen）、`lancedb`（本地向量检索）、`watchdog`（文件监控）。

---

## 系统能做什么

| 能力 | 说明 |
|------|------|
| 📸 图片识别 | OCR 提取图片文字（PaddleOCR），GLM-4.6V 理解图片语义 |
| 🔍 案例检索 | LanceDB 向量库匹配历史诈骗案例，输出相似度 TOP-5 |
| 🧠 诈骗判别 | 综合意图标签、案例相似度，输出诈骗概率和判决 |
| ⚠️ 风险分级 | 基于可配置规则（`risk-rules.json`）输出高/中/低风险等级 |
| 📣 多渠道预警 | 飞书 Webhook、邮件、钉钉，支持监护人联动通知 |
| 🔄 自我迭代 | 误判触发 ReflectorAgent，反思写入记忆，下次分析自动更新规则 |
| 📁 透明中间态 | 每步 Agent 输出写入 step1.json 到 step5.json，完整链路可溯源 |

---

## 系统架构

```
微信文件夹 / 邮件收件箱
         |
         v  (watchdog 文件监控 / IMAP 轮询)
  ┌──────────────┐
  │   Monitor    │  检测新图片，去重过滤，触发分析任务
  └──────┬───────┘
         |
         v
  ┌──────────────────────────────────────────────────────────┐
  │                   Pipeline Orchestrator                   │
  │                                                          │
  │  Agent1 (预处理+OCR)   ->   Agent2 (案例检索)           │
  │  GLM-4.6V 图片理解          LanceDB 向量检索             │
  │  Qwen 意图分类              TOP-5 相似案例               │
  │          |                        |                      │
  │          └────────────┬───────────┘                      │
  │                       v                                  │
  │              Agent3 (诈骗判别)                           │
  │              fraud_probability + verdict                 │
  │                       |                                  │
  │          ┌────────────┴────────────┐                     │
  │          v                         v                     │
  │  Agent4 (风险评估)        Agent5 (干预通知)              │
  │  加载记忆规则              飞书/邮件/钉钉                │
  │  HIGH/MEDIUM/LOW          监护人联动                     │
  └──────────────────────────────────────────────────────────┘
         |
         | 用户发现误判，触发反馈
         v
  ┌──────────────────┐
  │  ReflectorAgent  │  读取完整链路 JSONL -> 根因分析 -> 写反思文件
  └────────┬─────────┘
           |
           v
  memory/capabilities.md  <-  Agent4 下次运行时读取，规则自动生效
```

---

## 快速开始

### 环境要求

- Python 3.10+
- Windows 11（PaddleOCR 测试环境；Linux 未验证）
- [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)（PaddleOCR 依赖）

### 1. 克隆仓库

```bash
git clone https://github.com/qingcaizz/mutiagent-antiscam.git
cd mutiagent-antiscam
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> **Windows 注意：** 若 PaddleOCR 安装失败，先执行 `pip install "paddleocr>=2.7.0" --no-deps`，再手动安装缺失依赖。

### 3. 配置环境变量

```bash
cp config/.env.example .env
```

**必填变量：**

| 变量 | 说明 | 获取方式 |
|------|------|----------|
| `ZHIPU_API_KEY` | 智谱 AI Key（GLM-4.6V 图片理解） | [open.bigmodel.cn](https://open.bigmodel.cn) |
| `NAU_API_KEY` | Qwen 兼容接口 Key（意图识别） | 联系 API 提供商 |
| `NAU_BASE_URL` | Qwen API Base URL | 联系 API 提供商 |

**通知渠道（至少配置一个才能收到预警）：**

| 变量 | 说明 |
|------|------|
| `GUARDIAN_FEISHU` | 飞书 Webhook URL（高风险时通知监护人） |
| `GUARDIAN_EMAIL` | 监护人邮件地址 |
| `NOTIFY_TO_EMAIL` | 普通预警接收邮件 |
| `EMAIL_USER` / `EMAIL_PASS` | 邮件监控账号 |

### 4. 初始化案例库

```bash
python -m scripts.init_lancedb
# 输出：案例库初始化成功，共 8 条记录
```

### 5. 运行测试（验证安装）

```bash
pytest tests/ -v
# 121 passed, 7 skipped — 全部通过即安装成功
# 测试使用 mock，无需真实 API Key
```

### 6. 启动监控

```bash
python -m monitor.wechat_monitor   # 微信文件夹监控
python -m monitor.email_monitor    # 邮件收件箱监控
```

### 7. 手动触发单次分析

```bash
python -c "
from pipeline.orchestrator import Orchestrator
import asyncio
orch = Orchestrator()
result = asyncio.run(orch.run('cases/raw/test.jpg'))
print(result)
"
```

---

## 目录结构

```
mutiagent-antiscam/
├── agents/
│   ├── agent1_preprocessor.py    # OCR + 意图识别（GLM-4.6V + Qwen）
│   ├── agent2_retrieval.py       # 向量检索（LanceDB TOP-5）
│   ├── agent3_discrimination.py  # 诈骗判别（fraud_probability）
│   ├── agent4_assessment.py      # 风险评估（加载记忆规则）
│   └── agent5_intervention.py   # 多渠道干预通知
├── memory/
│   ├── reflector.py              # ReflectorAgent（误判反思 + 记忆更新）
│   └── capabilities.md           # 累积记忆规则（Agent4 动态读取）
├── monitor/
│   ├── wechat_monitor.py         # 微信文件夹 watchdog 监控
│   └── email_monitor.py          # IMAP 邮件监控
├── pipeline/
│   └── orchestrator.py           # 流水线编排 + 透明文件夹写入
├── config/
│   ├── load_config.py            # 环境变量加载
│   ├── risk-rules.json           # 可配置风险规则
│   ├── intent_labels.json        # 可配置意图标签
│   └── .env.example              # 环境变量模板
├── scripts/
│   └── init_lancedb.py           # 案例库初始化（幂等）
├── cases/
│   └── sample-cases.json         # 示例诈骗案例（8 条，已匿名化）
├── tests/                        # 121 个测试用例
└── requirements.txt
```

---

## 透明文件夹：每步可查

每次分析任务的中间状态完整持久化：

```
.pipeline/tasks/{taskId}/
├── step1.json   # OCR 文本、意图标签、置信度
├── step2.json   # TOP-5 相似案例、similarity_score
├── step3.json   # 诈骗概率、判决（诈骗/可疑/正常）、推理说明
├── step4.json   # 风险等级、触发规则、requires_guardian_alert
└── step5.json   # 通知渠道、发送状态、报告路径

conversations/YYYY-MM-DD/
└── task-{id}-full.jsonl  # 完整执行链路（每步一行 JSON）
```

---

## 自我迭代：误判变经验

```bash
# 1. 触发反思
python -m memory.reflector --task-id <id> --feedback "这是正常的转账提醒，不是诈骗"

# 2. ReflectorAgent 自动完成：
#    读取链路 JSONL -> 根因分析 -> 写 memory/reflections/YYYY-MM-DD-case-{id}.md
#    -> 更新 memory/capabilities.md

# 3. 下次 Agent4 运行时自动读取新规则，评估逻辑更新
```

---

## 测试覆盖

```bash
pytest tests/ -v  # 121 passed, 7 skipped
```

| 测试文件 | 覆盖内容 |
|----------|---------|
| `test_agent1_preprocessor.py` | GLM/Qwen mock，意图标签，降级处理 |
| `test_agent2_retrieval.py` | 真实 LanceDB，相似度计算，低相关度警告 |
| `test_agent3_discrimination.py` | 输出字段格式，降级失败处理 |
| `test_agent4_assessment.py` | risk-rules.json 规则匹配（参数化），监护人标志 |
| `test_agent5_intervention.py` | mock httpx Webhook，报告生成，监护人联动 |
| `test_reflector.py` | 链路读取，反思文件写入，capabilities.md 更新 |
| `test_orchestrator_integration.py` | 透明文件夹写入，JSONL 链路完整性 |
| `test_integration_e2e.py` | 端到端方向性测试（诈骗样本 verdict 非"正常"） |
| `test_wechat_monitor.py` | 文件过滤，去重防重复 |
| `test_email_monitor.py` | IMAP mock，MIME 解析 |

---

## License

MIT

---

# AntiScam Agent System (English)

> Real-time scam detection for WeChat/email images with a self-improving memory loop. Built for non-technical users who receive scam content daily.

## Why not Deer-Flow / AgentScope / AutoGen?

| Framework | Vendor | Why not used |
|-----------|--------|--------------|
| [Deer-Flow](https://github.com/bytedance/deer-flow) | ByteDance | Designed for research tasks; too heavy for file monitoring pipelines |
| [AgentScope](https://github.com/modelscope/agentscope) | Alibaba | Visual orchestration conflicts with transparent-folder design |
| [AutoGen](https://github.com/microsoft/autogen) | Microsoft | Conversation-driven; doesn't fit one-way pipelines |
| [LangChain](https://github.com/langchain-ai/langchain) | LangChain | Over-abstracted; hard to inspect per-step agent outputs |

This project uses plain Python classes with direct API calls. Each agent writes its output to a JSON file — no framework magic, full auditability.

## Quick Start

```bash
git clone https://github.com/qingcaizz/mutiagent-antiscam.git
cd mutiagent-antiscam
pip install -r requirements.txt
cp config/.env.example .env   # Fill in ZHIPU_API_KEY, NAU_API_KEY, NAU_BASE_URL
python -m scripts.init_lancedb
pytest tests/ -v              # 121 passed = installation verified
python -m monitor.wechat_monitor
```

## Required Environment Variables

| Variable | Description |
|----------|-------------|
| `ZHIPU_API_KEY` | ZhipuAI key for GLM-4.6V vision model |
| `NAU_API_KEY` | Qwen-compatible API key for intent classification |
| `NAU_BASE_URL` | Qwen API base URL |

## Pipeline

```
Monitor -> Agent1 (OCR + Intent) -> Agent2 (Vector Search) ->
Agent3 (Discrimination) -> Agent4 (Risk Assessment) -> Agent5 (Alert)
                                        ^
                               ReflectorAgent (memory loop)
```

Each step writes a stepN.json file for full auditability.

## Self-Improvement

```bash
python -m memory.reflector --task-id <id> --feedback "reason"
# Writes reflection -> updates memory/capabilities.md -> Agent4 reads on next run
```

## License

MIT
