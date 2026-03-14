# AntiScam Agent System — 智能反诈骗分析系统

> 基于多 Agent 架构的自动反诈骗分析系统，能自动检测诈骗内容并通过自我迭代学习持续改进判断能力。

## 项目简介

本系统通过 5 个专职 Agent 组成流水线，对微信文件夹或邮件中接收到的图片/文本进行实时诈骗检测。当系统出现误判时，ReflectorAgent 自动反思并更新记忆规则，使下次分析更准确。

## 系统架构

```
图片/文本
    │
    ▼
Agent1 (预处理+OCR)      ← GLM-4.6V 图片理解 + Qwen 意图分类
    │
    ▼
Agent2 (案例检索)        ← LanceDB 向量检索，匹配历史诈骗案例
    │
    ▼
Agent3 (诈骗判别)        ← 结合案例相似度输出诈骗概率
    │
    ▼
Agent4 (风险评估)        ← 加载记忆规则，输出分级风险等级
    │
    ▼
Agent5 (干预通知)        ← 飞书/邮件/钉钉多渠道预警
    │
    ▼
ReflectorAgent (误判反思) ← 误判触发，反思写入记忆，影响下次 Agent4
```

## 快速开始

### 环境要求

- Python 3.10+
- Windows 11（PaddleOCR 测试环境；Linux 未验证）
- Visual C++ Redistributable（PaddleOCR 依赖，[下载链接](https://aka.ms/vs/17/release/vc_redist.x64.exe)）

### 1. 克隆仓库

```bash
git clone <repo-url>
cd mutiagent_trea
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> **Windows 注意：** 若 PaddleOCR 安装失败，先执行 `pip install "paddleocr>=2.7.0" --no-deps`，再手动安装报缺失的依赖。

### 3. 配置环境变量

```bash
cp config/.env.example .env
```

编辑 `.env` 文件，填入以下变量：

#### 必需变量

| 变量名 | 说明 | 获取方式 |
|--------|------|----------|
| `ZHIPU_API_KEY` | 智谱 AI API Key（GLM-4.6V 图片理解） | [open.bigmodel.cn](https://open.bigmodel.cn) |
| `NAU_API_KEY` | Qwen 兼容接口 API Key（意图识别） | 联系 API 提供商 |
| `NAU_BASE_URL` | Qwen API Base URL | 联系 API 提供商 |

#### 可选变量（至少配置一个通知渠道才能收到预警）

| 变量名 | 说明 |
|--------|------|
| `GUARDIAN_FEISHU` | 飞书 Webhook URL（高风险时通知监护人） |
| `GUARDIAN_EMAIL` | 监护人邮件地址 |
| `EMAIL_USER` | 邮件监控账号（用于扫描收件箱） |
| `EMAIL_PASS` | 邮件监控授权码 |
| `NOTIFY_TO_EMAIL` | 预警接收邮件地址 |

其余变量（LanceDB 路径、风险阈值、日志级别）均有默认值，可按需修改。

### 4. 初始化案例库

```bash
python -m scripts.init_lancedb
```

预期输出：

```
案例库初始化成功，共 8 条记录
```

> 此命令为幂等操作：重复执行不会重复插入数据。

### 5. 运行测试

```bash
pytest tests/ -v
```

预期：全部测试通过。测试使用 mock 隔离外部 API，无需真实 API Key。

### 6. 启动监控

**微信文件夹监控（监控新接收的图片/文件）：**

```bash
python -m monitor.wechat_monitor
```

**邮件监控（需配置 `EMAIL_USER` / `EMAIL_PASS`）：**

```bash
python -m monitor.email_monitor
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

## 目录结构

```
mutiagent_trea/
├── agents/          # 5 个分析 Agent（preprocessor, retrieval, discrimination, assessment, intervention）
├── memory/          # ReflectorAgent + 记忆规则存储（reflections/, capabilities.md）
├── monitor/         # 微信文件夹监控 + 邮件监控器
├── pipeline/        # 流水线编排器（orchestrator.py）
├── config/          # 配置加载、风险规则、意图标签、.env.example
├── scripts/         # 初始化脚本（init_lancedb.py）
├── cases/           # 案例库（LanceDB 向量存储）
├── tests/           # 测试套件
├── reports/         # 分析报告输出（每次运行生成 JSON）
└── requirements.txt
```

## 误判反馈与自我迭代

当系统判断有误时，可手动触发反思循环：

```bash
python -m memory.reflector --task-id <task-id> --feedback "误判原因说明"
```

反思结果写入 `memory/reflections/`，并自动更新 `memory/capabilities.md` 中的记忆规则。下次 Agent4 运行时会加载最新规则，影响风险评分。

---

# AntiScam Agent System

> A multi-agent pipeline for automated scam detection with self-improving capabilities through reflection feedback loops.

## Overview

This system runs a 5-agent pipeline to analyze images and text received via WeChat folders or email for scam content. When a misclassification occurs, the ReflectorAgent automatically reflects and updates memory rules, improving future analysis accuracy.

## Quick Start

### Prerequisites

- Python 3.10+
- Windows 11 (PaddleOCR tested environment; Linux not validated)
- [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) (required by PaddleOCR)

### Installation

```bash
git clone <repo-url>
cd mutiagent_trea
pip install -r requirements.txt
cp config/.env.example .env
# Edit .env with your API keys (see table below)
python -m scripts.init_lancedb
pytest tests/ -v   # All tests should pass
```

### Required Environment Variables

| Variable | Description | Source |
|----------|-------------|--------|
| `ZHIPU_API_KEY` | ZhipuAI API key for GLM-4.6V vision model | [open.bigmodel.cn](https://open.bigmodel.cn) |
| `NAU_API_KEY` | Qwen-compatible API key for intent classification | Contact your API provider |
| `NAU_BASE_URL` | Qwen API base URL | Contact your API provider |

### Optional Variables (configure at least one notification channel)

| Variable | Description |
|----------|-------------|
| `GUARDIAN_FEISHU` | Feishu webhook URL for high-risk alerts |
| `GUARDIAN_EMAIL` | Guardian email address for critical alerts |
| `EMAIL_USER` | Email account for inbox monitoring |
| `EMAIL_PASS` | Email app password/token |
| `NOTIFY_TO_EMAIL` | Alert recipient email address |

### Running

```bash
# Monitor WeChat file folder for new images
python -m monitor.wechat_monitor

# Monitor email inbox (requires EMAIL_USER / EMAIL_PASS)
python -m monitor.email_monitor
```

## Architecture

5-agent pipeline:

```
Preprocessor (Agent1) → Retrieval (Agent2) → Discrimination (Agent3)
    → Assessment (Agent4) → Intervention (Agent5)
                                    ↑
                            ReflectorAgent (feedback loop)
```

- **Agent1:** OCR via GLM-4.6V, intent classification via Qwen
- **Agent2:** Vector search in LanceDB against historical scam cases
- **Agent3:** Outputs scam probability using case similarity
- **Agent4:** Loads memory rules, outputs risk level (HIGH/MEDIUM/LOW)
- **Agent5:** Sends alerts via Feishu / email / DingTalk
- **ReflectorAgent:** Triggered on misclassification, writes reflection to `memory/`, updates rules for Agent4

## Pipeline Output

Each analysis run creates a timestamped directory under `reports/` containing per-agent JSON output (`step1.json` – `step5.json`) and a full-chain JSONL log.

## Misclassification Feedback

```bash
python -m memory.reflector --task-id <task-id> --feedback "reason for misclassification"
```

Reflection results are written to `memory/reflections/` and update `memory/capabilities.md`, which Agent4 reads on its next run.

## License

MIT
