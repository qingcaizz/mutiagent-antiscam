---
phase: "03"
plan: "02"
subsystem: Agent2-RAG检索
tags: [tdd, lancedb, sentence-transformers, bug-fix, vector-search]
dependency_graph:
  requires: []
  provides: [Agent2-verified, similarity_score-conversion, TDD-suite-agent2]
  affects: [agent3_discrimination.py, downstream-consumers]
tech_stack:
  added: []
  patterns: [LanceDB-_distance-to-similarity_score, avg-based-warning-threshold]
key_files:
  created:
    - tests/test_agent2_retrieval.py
  modified:
    - agents/agent2_retrieval.py
decisions:
  - "search_similar() 是 LanceDBClient 唯一检索方法，Agent2 中旧的 search() 调用已全部替换"
  - "similarity_score = round(max(0.0, 1.0 - _distance), 4)：归一化向量 L2 距离约 0-2，1-distance 得到 0-1 近似相似度"
  - "low_similarity_warning 改为基于 avg_similarity < similarity_threshold 判断，与 ROADMAP 规格一致"
  - "result 字典新增 cases 字段（含 similarity_score 的完整 TOP-5 列表），供下游 Agent3 使用"
metrics:
  duration: "153 seconds (2.5 minutes)"
  completed_date: "2026-03-14"
  tasks_completed: 2
  files_modified: 2
  tests_passed: 9
---

# Phase 03 Plan 02: Agent2 RAG 检索接口修复与 TDD 验证 Summary

**One-liner:** 修复 Agent2 中 search()→search_similar() 接口不匹配 bug，添加 _distance→similarity_score 转换，9 个 TDD 测试全部通过

## What Was Built

RetrievalAgent（Agent2）的代码修复和 TDD 测试套件：

1. **接口修复**：将 `self.db.search(query=query_text, top_k=self.top_k)` 替换为 `self.db.search_similar(query_text, self.top_k)`，消除 AttributeError

2. **字段转换**：LanceDB 返回 `_distance`（L2 距离，越小越相似），转换公式 `similarity_score = round(max(0.0, 1.0 - _distance), 4)` 输出 0-1 范围的相似度分数

3. **警告逻辑修复**：`low_similarity_warning` 从原来的 `len(relevant_cases) < top_k // 2` 改为 `avg_similarity < similarity_threshold`，与 ROADMAP 规格对齐

4. **输出格式扩展**：result 字典新增 `cases` 字段（完整 TOP-5 列表，每条含 similarity_score），`relevant_cases` 改为用 similarity_score 过滤

5. **TDD 测试套件**：9 个集成测试覆盖核心行为，使用真实 LanceDB 临时实例，sentence-transformers 本地运行，无需外部 API

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | 修复 Agent2 接口不匹配 bug | 48b9b68 | agents/agent2_retrieval.py |
| 2 (RED) | 添加 TDD 测试套件 | 3188cef | tests/test_agent2_retrieval.py |
| 2 (GREEN) | 测试全部通过（无需额外修复） | - | 复用任务1修复 |

## Test Results

```
9 passed, 4 warnings in 36.42s

tests/test_agent2_retrieval.py::test_returns_result_dict PASSED
tests/test_agent2_retrieval.py::test_returns_cases_list PASSED
tests/test_agent2_retrieval.py::test_each_case_has_similarity_score PASSED
tests/test_agent2_retrieval.py::test_avg_similarity_field_present PASSED
tests/test_agent2_retrieval.py::test_low_similarity_warning_false_for_relevant_query PASSED
tests/test_agent2_retrieval.py::test_low_similarity_warning_present_in_result PASSED
tests/test_agent2_retrieval.py::test_warning_logic_consistent_with_avg_similarity PASSED
tests/test_agent2_retrieval.py::test_step2_json_written PASSED
tests/test_agent2_retrieval.py::test_build_query_includes_intent_and_indicators PASSED
```

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| search_similar() 替换 search() | LanceDBClient 只有 search_similar(text, top_k) 接口，search() 不存在 |
| similarity_score = max(0.0, 1.0 - _distance) | 归一化向量 L2 距离范围约 0-2，此公式将其映射到 0-1 相似度 |
| avg-based warning threshold | ROADMAP 规格要求基于平均相似度判断，而非案例数量 |
| cases 字段包含完整 TOP-5 | 下游 Agent3 需要访问所有候选案例（含低相似度），relevant_cases 仅含过滤后结果 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 旧接口 search() 已在任务1修复，TDD 测试直接进入 GREEN**
- **Found during:** 任务2 RED 阶段
- **Issue:** 按计划 RED 阶段测试应失败，但任务1已修复所有接口问题
- **Fix:** 测试文件写入后直接运行，9 个测试全部通过，无需额外 GREEN 阶段修复
- **Files modified:** 无（任务1已处理）
- **Commit:** 48b9b68（任务1）

无其他偏差。

## Self-Check: PASSED

- FOUND: agents/agent2_retrieval.py
- FOUND: tests/test_agent2_retrieval.py
- FOUND: .planning/phases/03-Agent1-2验证/03-02-SUMMARY.md
- FOUND commit: 48b9b68 (fix agent2 interface)
- FOUND commit: 3188cef (add TDD tests)
- 9/9 tests PASSED
