# Roadmap: AntiScam Agent System

## Overview

这是一个棕地项目——核心代码（20个文件，5个Agent，完整流水线）已写完，质量评分95/100。路线图的目标不是"构建系统"，而是"逐层验证系统正确运行"。从基础环境到单层测试，再到集成验证和端到端演练，最终准备开源发布。每个阶段的目标是让对应能力"经过测试且可验证"，而不是从零构建。

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: 基础环境** - 验证依赖安装、配置加载和项目结构能在 Windows 11 上正常工作
- [x] **Phase 2: 监控层验证** - 确认 WeChat 和邮件监控能正确检测新文件并防止重复触发 (completed 2026-03-14)
- [x] **Phase 3: Agent1-2 验证** - 确认预处理+意图识别和案例检索两个Agent输出符合规格 (completed 2026-03-14)
- [x] **Phase 4: Agent3-5 验证** - 确认判别、风险评估和干预通知三个Agent输出符合规格 (completed 2026-03-14)
- [x] **Phase 5: 透明文件夹与集成** - 确认完整5-Agent流水线能端到端运行并写入所有透明文件夹 (completed 2026-03-14)
- [x] **Phase 6: 自我迭代验证** - 确认误判反馈触发 ReflectorAgent 正确写入记忆并影响下次分析 (completed 2026-03-14)
- [ ] **Phase 7: 开源准备** - 确认项目可被陌生开发者克隆、安装、运行，文档完整可读

## Phase Details

### Phase 1: 基础环境
**Goal**: 任何人克隆本仓库后，能在干净的 Windows 11 Python 3.10+ 环境中一步安装依赖并加载配置
**Depends on**: 无（第一阶段）
**Requirements**: MONITOR-03, RETRIEVAL-03, OSS-02, OSS-03
**Success Criteria** (what must be TRUE):
  1. 运行 `pip install -r requirements.txt` 无报错，所有核心包（paddleocr、anthropic、lancedb、watchdog、sentence-transformers）均可导入
  2. 复制 `.env.example` 填入 API Key 后，配置加载脚本能正确读取所有必需环境变量且无 KeyError
  3. LanceDB 案例库能从 `sample-cases.json` 初始化，命令行输出"案例库初始化成功，共 N 条记录"
  4. `logs/` 目录自动创建，监控日志文件可写入
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — 修正 requirements.txt（移除 agentscope），TDD 验证所有核心包可 import
- [x] 01-02-PLAN.md — TDD 实现 config/load_config.py 和 scripts/init_lancedb.py，验证配置加载与案例库初始化

### Phase 2: 监控层验证
**Goal**: WeChat 文件夹监控和邮件 IMAP 监控能可靠检测新内容，且同一文件不触发重复分析
**Depends on**: Phase 1
**Requirements**: MONITOR-01, MONITOR-02, MONITOR-03
**Success Criteria** (what must be TRUE):
  1. 向监控的 WeChat Image 目录放入新图片后，`monitor.log` 在 5 秒内记录该文件被检测到
  2. 配置 IMAP 账号后，新邮件（含图片附件）在下一个轮询周期内被检测并记录
  3. 将同一张图片复制两次进入监控目录，日志仅显示一条触发记录（重复过滤生效）
  4. 监控层测试套件全部通过，覆盖正常路径和边界情况（空目录、非图片文件）
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — WeChat 监控 TDD 测试套件（文件类型过滤、去重防重复、logger 断言）
- [x] 02-02-PLAN.md — Email 监控 TDD 测试套件（IMAP mock 主路、MIME 解析、Playwright 备路骨架）

### Phase 3: Agent1-2 验证
**Goal**: 预处理+意图识别 Agent 和案例检索 Agent 的输出格式和内容符合下游 Agent 要求
**Depends on**: Phase 1
**Requirements**: PREPROCESS-01, PREPROCESS-02, PREPROCESS-03, RETRIEVAL-01, RETRIEVAL-02, RETRIEVAL-03
**Success Criteria** (what must be TRUE):
  1. 给定含文字的诈骗图片，Agent1 输出包含非空 `intent_label`（配置文件定义的标签之一）、`confidence`（0-1 浮点数）、`key_indicators` 列表和 `extracted_text_summary` 字符串
  2. 给定无文字的纯图标图片，Agent1 的 GLM-4.6V 路径不崩溃，正常返回结果
  3. Agent2 对任意输入能返回 TOP-5 案例列表，每条包含 `similarity_score`；当平均相似度 < 0.65 时输出包含低相关度警告标志
  4. Agent1-2 测试套件全部通过，Agent1 真实调用 GLM+Qwen API，Agent2 使用真实本地 LanceDB
**Plans**: 2 plans

Plans:
- [ ] 03-01-PLAN.md — Agent1 代码改造（anthropic→GLM+Qwen）+ config/intent_labels.json + TDD 测试套件
- [ ] 03-02-PLAN.md — Agent2 接口 bug 修复（search→search_similar）+ similarity_score 转换 + TDD 测试套件

### Phase 4: Agent3-5 验证
**Goal**: 判别、风险评估和干预通知三个 Agent 能正确处理上游输入并产生规格内的输出和副作用
**Depends on**: Phase 3
**Requirements**: DISCRIM-01, DISCRIM-02, ASSESS-01, ASSESS-02, ASSESS-03, ASSESS-04, INTERV-01, INTERV-02, INTERV-03, INTERV-04
**Success Criteria** (what must be TRUE):
  1. Agent3 接受 Agent1+Agent2 的结构化输出，返回 `fraud_probability`（0-1）、`verdict`（诈骗/可疑/正常）、`reasoning` 文本
  2. Agent4 加载 risk-rules.json 后对高风险关键词命中的输入输出风险等级"高"或"极高"；极高风险时输出包含 `requires_guardian_alert: true`
  3. Agent5 在中风险及以上时向飞书/钉钉 Webhook 发送请求（可用 mock 验证），并在 `reports/` 目录生成 Markdown 报告文件
  4. Agent3-5 测试套件全部通过，含 mock Webhook 的干预测试和 risk-rules.json 规则匹配的参数化测试
**Plans**: 3 plans

Plans:
- [ ] 04-01-PLAN.md — Agent3 TDD 测试套件（mock anthropic、输出字段格式、降级失败处理）
- [ ] 04-02-PLAN.md — Agent4 TDD 测试套件（规则加载、参数化关键词匹配、风险等级、监护人标志）
- [ ] 04-03-PLAN.md — Agent5 TDD 测试套件（mock httpx Webhook、报告生成、监护人联动、反馈标志）

### Phase 5: 透明文件夹与集成
**Goal**: 完整的 5-Agent 流水线能对真实输入端到端运行，所有中间状态写入透明文件夹，且可通过文件系统检查
**Depends on**: Phase 4
**Requirements**: TRANS-01, TRANS-02, TRANS-03
**Success Criteria** (what must be TRUE):
  1. 对一张诈骗图片运行完整流水线后，`conversations/YYYY-MM-DD/` 目录包含该任务的完整 JSONL 执行链路文件
  2. `.pipeline/tasks/{taskId}/` 目录包含 step1.json 到 step5.json，每个文件含对应 Agent 的中间输出
  3. `pipeline.log` 包含该次运行的完整时间戳日志，`monitor.log` 包含文件触发记录
  4. 集成测试能用已知诈骗和已知正常样本验证流水线整体判断方向正确（诈骗样本 → verdict 非"正常"）
**Plans**: 2 plans

Plans:
- [ ] 05-01-PLAN.md — Orchestrator 集成测试（mock 五 Agent，验证 JSONL 链路和 stepN.json 写入）
- [ ] 05-02-PLAN.md — 日志写入验证（TRANS-03）+ 监控触发链路 + 判断方向性测试

### Phase 6: 自我迭代验证
**Goal**: 误判反馈流程能完整运行——从用户反馈到反思写入，再到下次分析读取更新后的规则
**Depends on**: Phase 5
**Requirements**: REFLECT-01, REFLECT-02, REFLECT-03, REFLECT-04, ASSESS-03
**Success Criteria** (what must be TRUE):
  1. 对一个已完成分析的任务触发"误判"反馈后，ReflectorAgent 能读取完整执行链路 JSONL 并生成根因分析
  2. `memory/reflections/` 目录出现新的 `YYYY-MM-DD-case-{id}.md` 反思文件，文件内容包含根因和改进建议
  3. `memory/capabilities.md` 在反思后追加新条目，条目可被 Agent4 在下次分析时读取
  4. 对同类样本再次运行分析时，Agent4 的评估逻辑能体现 capabilities.md 中的新规则（风险分数或等级有变化）
**Plans**: TBD

Plans:
- [ ] 06-01: 为 reflector.py 编写 TDD 测试（链路读取、根因识别、反思文件写入）
- [ ] 06-02: 编写迭代闭环集成测试，验证 capabilities.md 更新后影响 Agent4 评估结果

### Phase 7: 开源准备
**Goal**: 陌生开发者能通过 README 完成克隆→安装→运行全流程，项目满足开源发布标准
**Depends on**: Phase 6
**Requirements**: OSS-01, OSS-02, OSS-03, OSS-04
**Success Criteria** (what must be TRUE):
  1. README.md 包含中英文说明，按步骤可完成：克隆、安装依赖、配置 .env、初始化案例库、启动监控
  2. 按 README 步骤在干净环境执行，能成功运行系统并处理一个测试输入（端到端冒烟测试）
  3. sample-cases.json 中不含任何真实用户 PII（姓名/手机/账号/真实地址），经过匿名化审查
  4. requirements.txt 和 .env.example 文件齐全且与实际代码同步，无遗漏依赖
**Plans**: TBD

Plans:
- [ ] 07-01: 编写 README.md（中英文），撰写完整安装和使用教程
- [ ] 07-02: 审查 sample-cases.json 匿名化，执行开源前最终检查清单

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. 基础环境 | 2/2 | Complete | 2026-03-14 |
| 2. 监控层验证 | 2/2 | Complete   | 2026-03-14 |
| 3. Agent1-2 验证 | 2/2 | Complete   | 2026-03-14 |
| 4. Agent3-5 验证 | 3/3 | Complete    | 2026-03-14 |
| 5. 透明文件夹与集成 | 2/2 | Complete   | 2026-03-14 |
| 6. 自我迭代验证 | 2/2 | Complete   | 2026-03-14 |
| 7. 开源准备 | 0/2 | Not started | - |
