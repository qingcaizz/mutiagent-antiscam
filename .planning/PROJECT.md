# AntiScam Agent System

## What This Is

一个具有**自我迭代能力**的多模态诈骗识别与干预系统。监控本地微信文件夹和邮箱（图片/截图/文件），通过5个串联Agent（意图识别→案例检索→判别→风险评估→干预）自动识别诈骗内容，并在判断被证明有误时自动反思并写入专项记忆。所有会话/日志/记忆在透明文件夹结构中可见，适合开源发布。

## Core Value

**自动检测诈骗 + 自我迭代学习**——当用户告知误判时，系统能追溯完整链路、识别根因、写入记忆，下次避免同类错误。

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] 监控 WeChat 文件夹（Image/File 目录）中的新图片和文档
- [ ] 监控邮箱（IMAP）中的新邮件和附件
- [ ] Agent1：PaddleOCR 提取文字 + Claude Vision 意图识别，输出意图标签和置信度
- [ ] Agent2：LanceDB 向量相似度检索 TOP-K 案例，输出相关度分数
- [ ] Agent3：调用 Claude 判别，结合案例上下文，输出诈骗概率和可解释依据
- [ ] Agent4：加载 risk-rules.json 规则引擎，结合历史误判记忆，输出风险等级
- [ ] Agent5：飞书/钉钉 Webhook 推送预警，生成分析报告，等待用户反馈
- [ ] 透明文件夹：conversations/logs/memory/reports/.pipeline 全部可读
- [ ] 自我迭代：误判反馈触发 ReflectorAgent，写入 memory/reflections/ 并更新 capabilities.md
- [ ] 极高风险时触发监护人联动
- [ ] 开源结构：完整 Python 实现，README 中英文，社区可复用

### Out of Scope

- GUI/Web界面 — v1 以命令行 + 通知为主，Web UI 留 v2
- 实时视频/语音监控 — 超出 v1 范围
- 自动拦截/阻断消息 — 需平台API权限，v1 仅做预警
- 云端部署 — v1 本地运行，Docker 为可选

## Context

- **平台**：Windows 11，Python 3.10+，无 Docker/WSL2 依赖
- **框架**：原计划 Deer-Flow + AgentScope，经评估后改为直接 Python 实现（更简洁，无框架依赖）
- **现有代码**：已完成 20 个文件的初版实现，包含监控层（2个）、5个核心Agent、工作流编排、工具层（OCR/LanceDB/通知）、自反思系统
- **模型**：Claude claude-sonnet-4-6（通过 Anthropic API）
- **向量库**：LanceDB + sentence-transformers（paraphrase-multilingual-MiniLM-L12-v2）
- **代码质量评估**：扫描报告显示接口一致性 100%，核心逻辑完整，缺测试和输入校验

## Constraints

- **Tech Stack**: Python-only，不引入重量级框架（Deer-Flow/AgentScope 评估后放弃），直接使用 anthropic SDK
- **Windows 兼容**: 所有路径使用 pathlib，监控使用 watchdog（跨平台）
- **Token 成本**: 使用 claude-sonnet-4-6（成本/性能均衡），工具层用 haiku 的 sub-agent
- **开源约束**: 代码不能包含真实用户数据，案例数据需匿名化

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 直接 Python 实现，不用 Deer-Flow | 框架依赖复杂，Windows 部署困难，直接实现更透明 | — Pending |
| LanceDB 作为向量库 | 本地文件型，无服务器依赖，Python 原生 | — Pending |
| Claude claude-sonnet-4-6 全链路 | 多模态能力强，API 稳定，支持 Vision | — Pending |
| 透明文件夹设计 | 所有中间状态可见，利于调试和开源展示 | — Pending |
| 5 Agent 固定串联 | 职责清晰，每步可单独测试和迭代 | — Pending |

---
*Last updated: 2026-03-14 after initialization*
