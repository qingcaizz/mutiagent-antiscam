---
phase: 02-监控层验证
plan: "02"
subsystem: testing
tags: [imap, email, loguru, pytest, mock, tdd, email-monitor, playwright]

# Dependency graph
requires:
  - phase: 01-基础环境
    provides: 项目基础依赖，确保 imaplib/email 标准库和 loguru 可用
  - plan: "02-01"
    provides: WeChat 监控 TDD 测试套件（brownfield TDD 模式已建立）
provides:
  - Email 监控 TDD 测试套件（24 个测试）
  - MONITOR-02 IMAP 轮询检测验证
  - Playwright 备路骨架结构
affects:
  - 03-OCR验证
  - 04-分析引擎验证

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "brownfield TDD: 先写测试验证已有 email_monitor.py，不修改源码"
    - "直接注入 mock_conn: monitor._connection = mock_conn，绕过 _connect() 完整流程"
    - "make_raw_email() 辅助函数: 用 email.mime 构造真实 RFC822 字节，支持 UTF-8/GB2312 编码主题"
    - "patch logger 路径: 'monitor.email_monitor.logger' 而非 'loguru.logger'"
    - "Playwright 备路: 不依赖浏览器，验证 _create_task() 对外部数据 dict 的处理逻辑"

key-files:
  created:
    - tests/test_email_monitor.py
    - tests/conftest.py
  modified: []

key-decisions:
  - "直接注入 mock connection (_connection = mock_conn)：比 patch IMAP4_SSL 更简洁，避免 MockIMAP.return_value 链式问题"
  - "make_raw_email() 支持 subject_charset 参数：统一测试 UTF-8 和 GB2312 编码主题"
  - "Playwright 备路设计为纯数据逻辑测试：验证 _create_task() 对任意来源 dict 的处理，不启动浏览器"
  - "conftest.py 注册 playwright mark：避免 PytestUnknownMarkWarning，为后续 Playwright 集成预留扩展点"

requirements-completed: [MONITOR-02]

# Metrics
duration: 2min
completed: 2026-03-14
---

# Phase 02 Plan 02: Email 监控 TDD 测试套件 Summary

**24 个 pytest 测试覆盖 EmailMonitor IMAP 主路（mock + 真实 MIME 构造）和 Playwright 备路骨架，MONITOR-02 全部通过，0 failed 0 error**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-14T04:15:18Z
- **Completed:** 2026-03-14T04:17:31Z
- **Tasks:** 2 (Task 1: 编写测试; Task 2: 验证联合运行)
- **Files modified:** 2

## Accomplishments

- 创建 tests/test_email_monitor.py（495 行），覆盖 MONITOR-02 IMAP 轮询检测
- 24 个测试全部通过：3 个连接测试 + 6 个 fetch 测试 + 6 个 parse 测试 + 6 个 task 测试 + 1 个 start 测试 + 2 个 Playwright 备路测试
- 创建 tests/conftest.py，注册 playwright 自定义 mark
- 联合运行 test_wechat_monitor.py + test_email_monitor.py：42 passed, 0 failed

## Task Commits

1. **Task 1+2: RED+GREEN — 编写并验证 Email 监控 TDD 测试套件** - `bab300c` (test)

## Files Created/Modified

- `tests/test_email_monitor.py` — Email 监控全套 TDD 测试，24 个测试，495 行
- `tests/conftest.py` — 注册 playwright 自定义 mark

## Decisions Made

- **直接注入 mock connection**: `monitor._connection = mock_conn` 比 `patch('imaplib.IMAP4_SSL')` 更直接。避免了 `MockIMAP.return_value` 的链式调用，测试更清晰
- **make_raw_email() 辅助函数**: 封装 `email.mime` 构造逻辑，支持 `has_image`/`subject_charset` 参数，复用于 mock 场景和集成测试场景
- **Playwright 备路不依赖浏览器**: `@pytest.mark.playwright` 测试仅验证 `_create_task()` 对数据 dict 的处理逻辑，为后续 Playwright MCP 集成预留骨架

## Deviations from Plan

None — 计划执行完全按照 PLAN.md，初次写入即 24/24 通过，无需迭代修正。

## Key Implementation Details

### IMAP mock 策略

```python
# 主路：直接注入 mock connection（无需 patch IMAP4_SSL）
mock_conn = MagicMock()
monitor._connection = mock_conn
mock_conn.search.return_value = ('OK', [b'1 2'])
mock_conn.fetch.side_effect = [fetch_result_1, fetch_result_2]
```

### RFC822 邮件构造

```python
def make_raw_email(subject, has_image=False, subject_charset=None) -> bytes:
    msg = email.mime.multipart.MIMEMultipart()
    msg['Subject'] = Header(subject, charset) if charset else subject
    msg.attach(email.mime.text.MIMEText(body, 'plain', 'utf-8'))
    if has_image:
        img_part = email.mime.image.MIMEImage(png_bytes, _subtype='png')
        img_part.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(img_part)
    return msg.as_bytes()
```

### 附件保存路径断言

```python
# save_path = attachment_save_dir / f"{msg_id}_{decoded_name}"
save_path = monitor.attachment_save_dir / '42_test.png'
assert save_path.exists()
```

## Issues Encountered

- 无生产代码问题。`email_monitor.py` 实现正确，边界处理完善
- `_fetch_new_emails()` 中 `msg_id.decode()` 正确将 bytes 转为 str，与 `_parse_email(msg, msg_id: str)` 签名匹配

## User Setup Required

无——无外部服务配置需求，所有测试使用 mock 和 tmp_path。

## Next Phase Readiness

- 邮件监控层验证完毕，MONITOR-02 需求已证明满足
- WeChat + Email 双监控路径均已 TDD 验证
- 下一步：Phase 3 OCR 验证（PaddleOCR Windows 兼容性处理已有先例）

---
*Phase: 02-监控层验证*
*Completed: 2026-03-14*

## Self-Check: PASSED

- FOUND: tests/test_email_monitor.py (495 lines, > 150 minimum)
- FOUND: tests/conftest.py (playwright mark registered)
- FOUND: commit bab300c (test(02-02): add Email monitor TDD test suite)
- FOUND: 24 tests PASSED, 0 FAILED, 0 ERROR
- FOUND: MONITOR-02 (IMAP polling) covered
- FOUND: @pytest.mark.playwright tests present and passing
