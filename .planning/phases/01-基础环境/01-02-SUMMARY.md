---
phase: "01-基础环境"
plan: "02"
subsystem: "配置加载 + 案例库初始化"
tags: ["tdd", "config", "lancedb", "dotenv", "sentence-transformers"]
dependency_graph:
  requires: ["01-01"]
  provides: ["config-loader", "lancedb-init", "monitor-dedup-verification"]
  affects: ["02-监控管线", "03-分析引擎", "all-subsequent-phases"]
tech_stack:
  added: ["python-dotenv (load_dotenv)", "dataclasses (AppConfig)"]
  patterns: ["TDD RED-GREEN", "idempotent initialization", "lazy model loading"]
key_files:
  created:
    - "config/__init__.py"
    - "config/load_config.py"
    - "scripts/__init__.py"
    - "scripts/init_lancedb.py"
    - "tests/test_config_loader.py"
    - "tests/test_lancedb_init.py"
  modified:
    - "utils/lancedb_client.py"
decisions:
  - "AppConfig 使用 dataclass 而非 dict，提供类型提示和属性访问"
  - "init_lancedb 幂等设计：count > 0 时直接返回，不重复插入"
  - "LanceDB features 占位数据从 [] 改为 ['placeholder']，修复 Arrow 类型推断 bug"
  - "scripts/init_lancedb.py 需从项目根目录以 python -m scripts.init_lancedb 运行"
metrics:
  duration: "7 minutes"
  completed_date: "2026-03-14"
  tasks_completed: 3
  files_changed: 7
---

# Phase 01 Plan 02: 配置加载与案例库初始化 Summary

**One-liner:** TDD 实现 dotenv 配置加载（AppConfig dataclass + 必需变量验证）和 LanceDB 幂等初始化（sentence-transformers embedding，8 条案例），同时修复 Arrow 类型推断 bug。

## What Was Built

通过 TDD RED-GREEN 流程完成了配置加载和案例库初始化：

1. **Task 1 (RED):** 创建 `tests/test_config_loader.py`，5 个测试（4 config + 1 MONITOR-03 去重基础设施验证）。4 个因 `config.load_config` 不存在失败，1 个（去重基础设施）立即通过（棕地代码已存在）。

2. **Task 2 (RED):** 创建 `tests/test_lancedb_init.py`，4 个测试均因 `scripts.init_lancedb` 不存在失败。

3. **Task 3 (GREEN):** 实现 `config/load_config.py`（AppConfig + load_config()）和 `scripts/init_lancedb.py`（init_case_database()），发现并修复 LanceDB Arrow 类型推断 bug（Rule 1 auto-fix），全部 17 个测试通过。

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | 配置加载失败测试 | 8eab378 | tests/test_config_loader.py |
| 2 (RED) | LanceDB 初始化失败测试 | 66cdc15 | tests/test_lancedb_init.py |
| 3 (GREEN+Fix) | 实现配置加载和 LanceDB 初始化 | 106831a | config/__init__.py, config/load_config.py, scripts/__init__.py, scripts/init_lancedb.py, utils/lancedb_client.py |

## Verification Results

```
1. pytest tests/test_config_loader.py -v  → 5 passed
2. pytest tests/test_lancedb_init.py -v   → 4 passed
3. pytest tests/ -v                       → 17 passed, 1 skipped (paddleocr)
4. python -m scripts.init_lancedb         → "案例库初始化成功，共 8 条记录"
5. from config.load_config import load_config → no error
6. ls logs/                               → logs/ 目录存在
```

## AppConfig 结构

`config/load_config.py` 导出的 `AppConfig` dataclass：

| 字段 | 类型 | 默认值 | 来源 |
|------|------|--------|------|
| anthropic_api_key | str | 必需 | ANTHROPIC_API_KEY |
| log_level | str | "INFO" | LOG_LEVEL |
| log_dir | str | "logs/" | LOG_DIR |
| lancedb_path | str | "cases/lancedb" | LANCEDB_PATH |
| embedding_model | str | paraphrase-multilingual-MiniLM-L12-v2 | EMBEDDING_MODEL |
| rag_top_k | int | 5 | RAG_TOP_K |
| rag_similarity_threshold | float | 0.65 | RAG_SIMILARITY_THRESHOLD |

## LanceDB 初始化机制

`scripts/init_lancedb.py` 的幂等设计：
1. 检查 `cases_path` 文件存在性（FileNotFoundError 如不存在）
2. 调用 `LanceDBClient.init_schema()`（若表已存在则跳过）
3. 检查 `client.count()`：若 > 0 → 输出"跳过"并返回；否则逐条插入
4. 返回实际案例总数

## sentence-transformers 模型加载耗时

首次运行（含模型下载）：
- 模型：`paraphrase-multilingual-MiniLM-L12-v2`
- 下载时间：约 2 分钟（模型文件 199 个权重块）
- 后续运行（本地缓存）：约 8-10 秒

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 修复 LanceDB features 空列表导致 Arrow 类型推断失败**
- **Found during:** Task 3 GREEN 阶段运行测试
- **Issue:** `utils/lancedb_client.py` 的 `init_schema()` 中，占位数据 `features: []` 导致 LanceDB 将该字段推断为 Arrow `null` 类型，后续 `add_case()` 插入含字符串的 `features` 时抛出 `ArrowNotImplementedError: Unsupported cast from string to null`
- **Fix:** 将 `features: []` 改为 `features: ["placeholder"]`，使 Arrow 正确推断 `list<string>` 类型
- **Files modified:** `utils/lancedb_client.py`
- **Commit:** 106831a

## Phase 1 整体验证（ROADMAP Success Criteria）

| SC | 描述 | 结果 |
|----|------|------|
| SC-1 | pytest tests/test_env_imports.py -v 全部通过 | 8 passed, 1 skipped |
| SC-2 | pytest tests/test_config_loader.py -v 全部通过 | 5 passed |
| SC-3 | python -m scripts.init_lancedb 输出"案例库初始化成功，共 8 条记录" | PASSED |
| SC-4 | logs/ 目录存在且可写 | PASSED |
| SC-5 | monitor/wechat_monitor.py 包含去重机制 | PASSED (test_monitor_dedup_infrastructure_exists) |

## Self-Check: PASSED

- [x] config/__init__.py 存在
- [x] config/load_config.py 存在，导出 load_config 和 AppConfig
- [x] scripts/__init__.py 存在
- [x] scripts/init_lancedb.py 存在，导出 init_case_database
- [x] tests/test_config_loader.py 存在，5 个测试函数
- [x] tests/test_lancedb_init.py 存在，4 个测试函数
- [x] pytest tests/ 17 passed, 1 skipped
- [x] "案例库初始化成功，共 8 条记录" 输出验证通过
- [x] logs/ 目录存在
- [x] Commits 8eab378, 66cdc15, 106831a 均已存在
