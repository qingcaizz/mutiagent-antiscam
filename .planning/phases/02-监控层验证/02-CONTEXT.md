# Phase 2: 监控层验证 - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

为已有的 `monitor/wechat_monitor.py` 和 `monitor/email_monitor.py` 编写 TDD 测试套件，验证：文件检测、去重过滤、日志记录三个核心行为。
本阶段不新增监控能力，只对现有代码做测试覆盖。

</domain>

<decisions>
## Implementation Decisions

### 邮件监控测试策略
- **IMAP 为主路**：为现有 `email_monitor.py` 的 IMAP 轮询逻辑编写测试（含 mock IMAP server）
- **Playwright 为备路**：同时实现基于 Playwright MCP 的 QQ 邮箱浏览器登录监控路径
  - 用户已安装 Playwright MCP，测试可直接调用 Playwright 工具
  - 备路测试验证 Playwright 抓取到新邮件后的处理逻辑

### 去重验证方式
- **真实文件写入 tmp 目录**：用 `pytest tmp_path` 创建临时监控目录，实际复制/写入文件，让 watchdog 真实检测
- 不使用 mock watchdog 事件——贴近真实场景，去重逻辑在真实文件系统中验证

### 日志断言方式
- **单元测试**：mock loguru logger，拦截输出，不依赖文件 I/O
- **集成测试**：检查真实 monitor.log 文件内容，断言包含指定关键字
- 两种方式都要，分别用于不同测试粒度

### Windows 路径兼容性
- WeChat 监控集成测试使用 `pytest.mark.skipif(sys.platform != 'win32', reason="WeChat monitor is Windows-only")`
- 非 Windows 平台自动 skip，不阻塞 CI
- 单元测试（mock 路径）不受平台限制

### Claude's Discretion
- Playwright 备路的具体测试结构（如何封装 MCP 调用）
- IMAP mock server 选型（imaplib mock vs pytest-imap）
- log 文件路径在测试中的隔离方案

</decisions>

<specifics>
## Specific Ideas

- 邮件监控备路：用户会通过 Playwright MCP 提供浏览器 session，在浏览器内登录 QQ 邮箱，监控器从 Playwright 抓取新邮件内容

</specifics>

<deferred>
## Deferred Ideas

- 无 — 讨论范围保持在 Phase 2 测试验证边界内

</deferred>

---

*Phase: 02-监控层验证*
*Context gathered: 2026-03-14*
