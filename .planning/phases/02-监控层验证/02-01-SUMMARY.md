---
phase: 02-监控层验证
plan: "01"
subsystem: testing
tags: [watchdog, loguru, pytest, mock, tdd, wechat-monitor]

# Dependency graph
requires:
  - phase: 01-基础环境
    provides: 项目基础依赖和配置加载，确保 watchdog/loguru 可用
provides:
  - WeChat 文件监控 TDD 测试套件（18 个测试）
  - MONITOR-01 文件类型过滤验证
  - MONITOR-03 去重防重复触发验证
affects:
  - 03-OCR验证
  - 04-分析引擎验证

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "brownfield TDD: 先写测试验证已有实现，不修改源码"
    - "Observer patch 时机: WeChatMonitor.__init__ 中直接调用 Observer()，patch 必须包裹实例化"
    - "单元测试用真实 tmp_path 文件 + mock callback，避免 on_created 内 exists()/st_size 检查失败"
    - "集成测试用 pytest.mark.skipif(sys.platform != 'win32') 隔离 Windows-only 功能"

key-files:
  created:
    - tests/test_wechat_monitor.py
  modified: []

key-decisions:
  - "Observer() 在 __init__ 中实例化，patch 必须包裹整个 WeChatMonitor() 构造调用"
  - "单元测试须向 tmp_path 写入真实文件（非空），因为 on_created 内有 exists() + st_size==0 双重检查"
  - "去重测试通过直接两次调用 handler.on_created(同一 event) 验证，无需等待异步事件"
  - "集成测试在 Windows 平台实际执行（不 skip），用 0.1s 轮询等待 watchdog 异步通知，最多 5 秒"

patterns-established:
  - "mock logger 路径: patch('monitor.wechat_monitor.logger') 而非 'loguru.logger'"
  - "make_handler(tmp_path) 辅助函数: 每个测试用独立 handler 避免 _processed_files 集合污染"
  - "make_event(file_path, is_directory) 辅助函数: 用 object.__setattr__ 覆盖 FileCreatedEvent.is_directory"

requirements-completed: [MONITOR-01, MONITOR-03]

# Metrics
duration: 3min
completed: 2026-03-14
---

# Phase 02 Plan 01: WeChat 监控层 TDD 测试套件 Summary

**18 个 pytest 测试验证 WeChatFileHandler 文件类型过滤和 _processed_files 去重机制，覆盖 MONITOR-01 和 MONITOR-03，单元+集成全部绿灯**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T04:09:52Z
- **Completed:** 2026-03-14T04:12:29Z
- **Tasks:** 2 (Task 1: 编写测试; Task 2: 修正边界细节)
- **Files modified:** 1

## Accomplishments

- 创建 tests/test_wechat_monitor.py（401 行），覆盖 MONITOR-01 文件类型过滤和 MONITOR-03 去重
- 18 个测试全部通过：10 个 WeChatFileHandler 单元测试 + 5 个 WeChatMonitor 单元测试 + 3 个集成测试
- 发现并修正关键测试陷阱：Observer() 在 __init__ 中实例化，patch 必须包裹构造调用

## Task Commits

每个任务原子提交：

1. **Task 1+2: RED+GREEN — 编写并修正 WeChat 监控 TDD 测试套件** - `b06cbe2` (test)

**计划元数据:** (待本次 docs commit)

_注：本计划为 brownfield TDD，Task 1 初始写入时 17/18 通过，Task 2 修正 Observer patch 时机后全绿_

## Files Created/Modified

- `tests/test_wechat_monitor.py` - WeChat 监控全套测试，18 个测试，401 行

## Decisions Made

- **Observer patch 时机**: `WeChatMonitor.__init__` 直接调用 `Observer()`，因此 `patch('monitor.wechat_monitor.Observer')` 必须在实例化之前生效（包裹整个 `WeChatMonitor(...)` 构造调用），否则 mock 实例和 `monitor.observer` 是不同对象
- **真实文件 vs 路径字符串**: `on_created` 内有 `file_path.exists()` 和 `st_size == 0` 双重检查，单元测试必须向 `tmp_path` 写入非空真实文件
- **集成测试策略**: Windows 平台直接运行集成测试（不 skip），用 `time.sleep(0.1)` 轮询最多 5 秒，兼顾 watchdog 异步延迟和 `on_created` 内的 `time.sleep(0.5)`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 修正 Observer mock 时机导致的测试失败**
- **Found during:** Task 2 (GREEN — 验证现有实现通过全部测试)
- **Issue:** `test_start_with_existing_dir_returns_true` 断言 `mock_observer_instance.start.assert_called_once()` 失败（called 0 times）。根本原因：`WeChatMonitor.__init__` 在对象构造时已调用 `Observer()`，此时 patch 尚未生效，`monitor.observer` 引用的是真实 Observer 实例，而非 mock
- **Fix:** 将 `WeChatMonitor(...)` 实例化移入 `patch('monitor.wechat_monitor.Observer')` with 块内，同时修正同类单元测试（`test_start_no_dirs_*`, `test_stop_*`, `test_is_running_*`）
- **Files modified:** tests/test_wechat_monitor.py
- **Verification:** 全部 18 个测试 PASSED
- **Committed in:** b06cbe2 (Task 1+2 合并提交)

---

**Total deviations:** 1 auto-fixed (Rule 1 - 测试断言 bug)
**Impact on plan:** 修正必要，不影响被测源码，无 scope creep。

## Issues Encountered

- 无生产代码问题。测试层面的 mock 时机是 brownfield TDD 的常见陷阱，已通过自动修正解决。

## User Setup Required

无——无外部服务配置需求。

## Next Phase Readiness

- WeChat 监控层验证完毕，MONITOR-01 / MONITOR-03 需求已证明满足
- 测试套件为后续集成测试（Phase 3 Anthropic API）提供可信基线
- 下一步: 02-02（如有）或进入 Phase 3 OCR 验证

---
*Phase: 02-监控层验证*
*Completed: 2026-03-14*

## Self-Check: PASSED

- FOUND: tests/test_wechat_monitor.py (401 lines, > 120 minimum)
- FOUND: commit b06cbe2 (test(02-01): add WeChat monitor TDD test suite)
- FOUND: 18 tests PASSED, 0 FAILED, 0 ERROR
- FOUND: pytest.mark.skipif present in test file
- FOUND: MONITOR-01 (file type filter) and MONITOR-03 (dedup) covered
