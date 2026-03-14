# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-14)

**Core value:** 自动检测诈骗 + 自我迭代学习——误判反馈触发反思，下次避免同类错误
**Current focus:** Phase 5 - 透明文件夹与集成 — COMPLETE（2/2 plans done）

## Current Position

Phase: 6 of 7 (自我迭代验证) — In Progress
Plan: 1 of 5 in current phase — COMPLETE
Status: In Progress
Last activity: 2026-03-14 — 完成 06-01: ReflectorAgent TDD 测试套件 4 tests passed（REFLECT-01/02/03）

Progress: [█████████░] 82% (12/14 plans total)

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: 3.4 minutes
- Total execution time: 0.27 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-基础环境 | 2 | 11 min | 5.5 min |
| 02-监控层验证 | 2 | 5 min | 2.5 min |
| 03-Agent1-2验证 | 2 | ~5 min | ~2.5 min |
| 04-Agent3-5验证 | 3 | ~15 min | ~5 min |
| 05-透明文件夹与集成 | 2/2 | 10 min | 5 min |

**Recent Trend:**
- Last 5 plans: 02-02 (2 min), 03-01 (2.5 min), 03-02 (2.5 min), 04-03 (5 min), 05-01 (5 min)
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Init]: 项目为棕地——20个文件已完成，路线图聚焦"测试验证"而非"从零构建"
- [Arch]: 直接 Python 实现，不用 Deer-Flow/AgentScope，使用 anthropic SDK + LanceDB
- [01-01]: agentscope 从 requirements.txt 移除，确认不使用该框架
- [01-01]: paddleocr 在 Windows 以 pytest.skip() 处理，不阻塞 CI
- [01-02]: AppConfig 使用 dataclass 而非 dict，提供类型提示和属性访问
- [01-02]: init_lancedb 幂等设计：count > 0 时直接返回，不重复插入
- [01-02]: LanceDB features 占位数据从 [] 改为 ['placeholder']，修复 Arrow 类型推断 bug
- [01-02]: scripts/init_lancedb.py 需从项目根目录以 python -m scripts.init_lancedb 运行
- [02-01]: Observer() 在 WeChatMonitor.__init__ 中实例化，patch 必须包裹整个构造调用
- [02-01]: on_created 内 exists()+st_size==0 双重检查，单元测试必须写入非空真实文件
- [02-01]: patch logger 路径为 'monitor.wechat_monitor.logger'，非 'loguru.logger'
- [Phase 02-监控层验证]: 直接注入 mock connection，比 patch IMAP4_SSL 更简洁
- [Phase 02-监控层验证]: Playwright 备路测试不依赖真实浏览器，验证 _create_task() 数据处理逻辑
- [03-01]: Agent1 从 anthropic SDK + PaddleOCR 迁移至 GLM-4.6V（requests）+ Qwen3.5（OpenAI SDK）
- [03-01]: intent_labels 从 config/intent_labels.json 动态读取，支持用户自定义，不再硬编码
- [03-01]: Qwen 返回非法 intent_label 时自动回退 unknown，不抛异常
- [03-02]: LanceDBClient.search_similar() 是唯一检索方法，Agent2 旧的 search() 调用已替换
- [03-02]: similarity_score = round(max(0.0, 1.0 - _distance), 4)，归一化向量 L2→0-1 相似度
- [03-02]: low_similarity_warning 基于 avg_similarity < similarity_threshold，而非案例数量
- [03-02]: result 字典新增 cases 字段（含 similarity_score 的完整 TOP-5），供下游 Agent3 使用
- [Phase 04-Agent3-5验证]: mock 路径 agents.agent5_intervention.send_alert 在调用方拦截，无需 patch utils.notifier.send_alert
- [Phase 04-Agent3-5验证]: guardian_email 测试使用属性注入使 enabled 属性返回 True，比 patch enabled 更贴近真实场景
- [05-01]: patch 整个 Agent 类（而非实例方法），防止 Orchestrator.__init__ 触发真实 LanceDB/API 初始化
- [05-01]: make_agent_run 工厂函数通过 args[-1] 获取 step_dir，兼容所有 Agent 不同参数数量（通用模式）
- [05-01]: _write_full_chain_jsonl 已在 orchestrator.py 实现，前置检查确认后直接编写测试
- [05-02]: loguru 临时 sink 用 try/finally 确保 logger.remove，防止跨测试日志泄漏
- [05-02]: WeChatFileHandler 测试通过 capture_task 捕获回调参数，再从 pipeline_dir 断言 input.json 存在
- [05-02]: 诈骗样本复用 MOCK_STEP3/4（fraud_probability=0.91），正常样本重新定义低概率 mock
- [06-01]: patch 路径 memory.reflector.anthropic.Anthropic 在调用方拦截，不调用真实 Claude API
- [06-01]: ReflectorAgent 通过三个独立路径参数实现完全 tmp_path 隔离

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3 开始需要真实 Anthropic API Key 才能运行集成测试（可用 mock 绕过）
- PaddleOCR 在 Windows 需要 Visual C++ Redistributable（已确认，测试中用 skip 处理）

## Session Continuity

Last session: 2026-03-14
Stopped at: 完成 06-01-PLAN.md 执行，ReflectorAgent TDD 测试套件 4 tests passed（REFLECT-01/02/03），提交 de3ec77
Resume file: None
