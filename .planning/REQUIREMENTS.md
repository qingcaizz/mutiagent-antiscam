# Requirements: AntiScam Agent System

**Defined:** 2026-03-14
**Core Value:** 自动检测诈骗 + 自我迭代学习——误判反馈触发反思，下次避免同类错误

## v1 Requirements

### 监控层 (MONITOR)

- [x] **MONITOR-01**: 系统能监控指定 WeChat 文件夹（Image/File 目录），新图片或文档出现时自动触发分析
- [x] **MONITOR-02**: 系统能通过 IMAP 轮询监控邮箱新邮件及图片附件
- [x] **MONITOR-03**: 监控层防止重复触发（同一文件不重复分析），并记录监控日志

### 预处理与意图识别 (PREPROCESS)

- [x] **PREPROCESS-01**: Agent1 能用 GLM-4.6V 分析图片内容并生成图像描述（替代 PaddleOCR）
- [x] **PREPROCESS-02**: Agent1 能调用 Qwen3.5 对图像描述进行意图分类（替代 Claude Vision）
- [x] **PREPROCESS-03**: Agent1 输出意图标签（10种）、置信度、关键特征、内容摘要

### 案例检索 (RETRIEVAL)

- [x] **RETRIEVAL-01**: Agent2 能在 LanceDB 向量库中检索相似历史案例（TOP-5）
- [x] **RETRIEVAL-02**: Agent2 输出每个案例的相似度分数，并在平均相似度 < 0.65 时发出低相关度警告
- [x] **RETRIEVAL-03**: 系统能从 sample-cases.json 初始化 LanceDB 案例库

### 判别 (DISCRIMINATION)

- [ ] **DISCRIM-01**: Agent3 结合 Agent1 意图识别结果和 Agent2 检索案例，调用 Claude 判断是否为诈骗
- [ ] **DISCRIM-02**: Agent3 输出诈骗概率（0-1）、verdict（诈骗/可疑/正常）、可解释依据

### 风险评估 (ASSESSMENT)

- [ ] **ASSESS-01**: Agent4 加载 risk-rules.json 规则，基于关键词匹配调整风险分数
- [ ] **ASSESS-02**: Agent4 输出风险等级（安全/低/中/高/极高）
- [ ] **ASSESS-03**: Agent4 读取 memory/capabilities.md 中的历史学习规则，纳入评估逻辑
- [ ] **ASSESS-04**: 极高风险时标记 requires_guardian_alert=true

### 干预与通知 (INTERVENTION)

- [x] **INTERV-01**: Agent5 通过飞书或钉钉 Webhook 推送风险预警（中风险及以上）
- [x] **INTERV-02**: Agent5 生成 Markdown 分析报告，保存到 reports/ 目录
- [x] **INTERV-03**: 极高风险时触发监护人联动（发送到 GUARDIAN_FEISHU/GUARDIAN_PHONE）
- [x] **INTERV-04**: Agent5 记录用户反馈入口，等待"误判"反馈

### 透明文件夹 (TRANSPARENCY)

- [x] **TRANS-01**: 每个任务的完整 5-Agent 执行链路保存为 `conversations/YYYY-MM-DD/task-{id}-full.jsonl`
- [x] **TRANS-02**: 每个 step 的中间结果保存为 `.pipeline/tasks/{taskId}/step{N}.json`
- [x] **TRANS-03**: 系统运行日志写入 `logs/` 目录（monitor.log, pipeline.log）

### 自我迭代 (REFLECTION)

- [x] **REFLECT-01**: 用户反馈"误判"时，ReflectorAgent 读取完整执行链路，识别根因
- [x] **REFLECT-02**: ReflectorAgent 将反思结果写入 `memory/reflections/YYYY-MM-DD-case-{id}.md`
- [x] **REFLECT-03**: ReflectorAgent 更新 `memory/capabilities.md`，追加新学习规则
- [ ] **REFLECT-04**: 下次分析时，Agent4 读取 capabilities.md 中更新的规则

### 开源可用性 (OPENSOURCE)

- [ ] **OSS-01**: 项目包含 README.md（中英文），说明安装和使用方法
- [x] **OSS-02**: 提供 requirements.txt，用户可一键安装依赖
- [x] **OSS-03**: 提供 config/.env.example，用户只需复制并填入自己的 API Key
- [ ] **OSS-04**: sample-cases.json 案例数据已匿名化，可直接开源

## v2 Requirements

### Web 可视化

- **WEB-01**: AgentScope 或自实现的 Web UI，实时显示 5-Agent 执行链路状态
- **WEB-02**: Web 界面可查看历史分析报告和反思记录

### 高级监控

- **ADV-01**: 支持微信多账号监控
- **ADV-02**: 支持短信/WhatsApp 内容接入

### 模型优化

- **OPT-01**: 基于误判案例对 Agent3 判别模型进行微调
- **OPT-02**: 支持用户自定义风险规则（规则贡献社区化）

## Out of Scope

| Feature | Reason |
|---------|--------|
| GUI/Web界面（v1） | v1 以命令行 + 通知为主，降低复杂度 |
| 实时视频/语音监控 | 超出 v1 范围，需额外硬件/模型 |
| 自动拦截/阻断消息 | 需平台API权限，存在合规风险 |
| 云端部署（v1） | v1 本地运行，Docker 为可选附加 |
| 移动端App | Web优先，移动端留v2 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MONITOR-01 | Phase 2 | Complete |
| MONITOR-02 | Phase 2 | Complete |
| MONITOR-03 | Phase 1 | Complete |
| PREPROCESS-01 | Phase 3 | Complete |
| PREPROCESS-02 | Phase 3 | Complete |
| PREPROCESS-03 | Phase 3 | Complete |
| RETRIEVAL-01 | Phase 3 | Complete |
| RETRIEVAL-02 | Phase 3 | Complete |
| RETRIEVAL-03 | Phase 1 | Complete |
| DISCRIM-01 | Phase 4 | Pending |
| DISCRIM-02 | Phase 4 | Pending |
| ASSESS-01 | Phase 4 | Pending |
| ASSESS-02 | Phase 4 | Pending |
| ASSESS-03 | Phase 6 | Pending |
| ASSESS-04 | Phase 4 | Pending |
| INTERV-01 | Phase 4 | Complete |
| INTERV-02 | Phase 4 | Complete |
| INTERV-03 | Phase 4 | Complete |
| INTERV-04 | Phase 4 | Complete |
| TRANS-01 | Phase 5 | Complete |
| TRANS-02 | Phase 5 | Complete |
| TRANS-03 | Phase 5 | Complete |
| REFLECT-01 | Phase 6 | Complete |
| REFLECT-02 | Phase 6 | Complete |
| REFLECT-03 | Phase 6 | Complete |
| REFLECT-04 | Phase 6 | Pending |
| OSS-01 | Phase 7 | Pending |
| OSS-02 | Phase 1 | Complete |
| OSS-03 | Phase 1 | Complete |
| OSS-04 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-14*
*Last updated: 2026-03-14 — Phase 3 完成后同步技术选型（GLM-4.6V + Qwen3.5 替代 PaddleOCR + Claude Vision）*
