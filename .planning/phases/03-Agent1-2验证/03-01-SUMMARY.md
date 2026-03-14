---
phase: "03-Agent1-2验证"
plan: "01"
subsystem: "agents"
tags: ["agent1", "glm", "qwen", "refactor", "tdd", "intent-classification"]
dependency_graph:
  requires: []
  provides: ["agent1-glm-qwen", "intent-labels-config"]
  affects: ["agents/agent1_preprocessor.py", "config/intent_labels.json", "tests/test_agent1_preprocessor.py"]
tech_stack:
  added: ["requests (GLM HTTP)", "openai (Qwen SDK)", "PIL (test image generation)"]
  patterns: ["dual-model pipeline", "config-driven label validation", "graceful API key skip"]
key_files:
  created:
    - "config/intent_labels.json"
    - "tests/test_agent1_preprocessor.py"
  modified:
    - "agents/agent1_preprocessor.py"
decisions:
  - "GLM-4.6V 通过 requests.post 调用（非 SDK），Qwen3.5 通过 OpenAI 兼容 SDK 调用"
  - "intent_label 合法性在 _qwen_classify_intent 内校验，非法标签自动回退 unknown"
  - "EnvironmentError 在 __init__ 早期抛出，给出明确的环境变量名提示"
  - "测试在 API Key 缺失时 pytest.skip()，不阻塞 CI 流程"
  - "INTENT_LABELS 类变量移除，改从 config/intent_labels.json 动态读取"
metrics:
  duration: "~15 min"
  completed_date: "2026-03-14"
  tasks_completed: 2
  files_changed: 3
---

# Phase 03 Plan 01: Agent1 GLM+Qwen 双路重构 Summary

**One-liner:** 将 Agent1 从 anthropic SDK + PaddleOCR 迁移至 GLM-4.6V（图像理解）+ Qwen3.5（意图分类）双路架构，配置驱动的 10 种诈骗意图标签。

## Objective

将 agent1_preprocessor.py 中的 anthropic SDK 和 PaddleOCR 调用替换为 GLM-4.6V（图像理解）+ Qwen3.5（意图分类）双路 API 调用，同时创建 config/intent_labels.json 配置文件，并编写覆盖改造后代码的 TDD 测试套件。

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | 创建 intent_labels.json + 改造 agent1_preprocessor.py | 7ca7491 | config/intent_labels.json, agents/agent1_preprocessor.py |
| 2 (RED) | TDD 测试套件创建 | be28d06 | tests/test_agent1_preprocessor.py |

## Key Changes

### agents/agent1_preprocessor.py

- **移除:** `import anthropic`, `from utils.ocr import extract_text_from_image`
- **新增:** `import requests`, `from openai import OpenAI`
- **架构变化:** 单路 anthropic → 双路 GLM-4.6V（图像）+ Qwen3.5（文本意图）
- **新增方法:** `_glm_analyze_image()`, `_qwen_classify_intent()`
- **标签加载:** 从 `config/intent_labels.json` 动态加载，存入 `self.valid_labels`
- **合法性校验:** Qwen 返回非法标签时自动回退 `unknown`，不抛异常

### config/intent_labels.json

10 种意图标签定义：financial_fraud, impersonation, phishing, romance_scam, lottery_scam, job_scam, normal_business, personal_communication, spam_advertising, unknown

### tests/test_agent1_preprocessor.py

6 个测试用例，覆盖：
1. `test_valid_labels_loaded` — valid_labels 属性存在且包含预期标签
2. `test_scam_image_returns_valid_output_format` — 图片输出字段类型验证
3. `test_scam_image_detected_as_suspicious` — 诈骗图片不被误判为正常
4. `test_icon_image_does_not_crash` — 纯色无文字图片不崩溃
5. `test_email_input_returns_valid_output` — 邮件文本路径正常处理
6. `test_step1_json_written` — step1.json 写入验证

## Test Status

**当前状态:** 6 个测试全部 SKIPPED（因 ZHIPU_API_KEY 和 NAU_API_KEY 未在当前环境配置）

测试在 API Key 注入后可直接运行（fixture 已包含 pytest.skip() 保护）：
```bash
export ZHIPU_API_KEY=<your_key>
export NAU_API_KEY=<your_key>
pytest tests/test_agent1_preprocessor.py -v
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Qwen 响应含思维链时 JSON 解析失败**
- **Found during:** 代码审查（预防性修复）
- **Issue:** Qwen3.5 有时在 JSON 后附加推理文本，导致 `json.loads()` 失败
- **Fix:** 使用 `re.search(r"\{[\s\S]*\}", response_text)` 提取第一个完整 JSON 对象
- **Files modified:** agents/agent1_preprocessor.py
- **Commit:** 7ca7491

**2. [Rule 2 - Security] intent_label 合法性校验**
- **Found during:** 实现 _qwen_classify_intent()
- **Issue:** Qwen 可能返回计划外的标签字符串，下游依赖合法标签
- **Fix:** 在 _qwen_classify_intent() 末尾校验并回退 unknown，记录 warning
- **Files modified:** agents/agent1_preprocessor.py
- **Commit:** 7ca7491

### Scope Notes

- `config/load_config.py` 仍引用 `ANTHROPIC_API_KEY`（该文件属于 Phase 1 范围，不在本计划修改范围内，已记录为 deferred）

## Decisions Made

1. **GLM 使用 requests 而非 SDK** — bigmodel.cn 未提供官方 Python SDK，直接 HTTP 请求更清晰可维护
2. **Qwen 使用 OpenAI SDK** — nau.edu.cn 提供 OpenAI 兼容接口，复用成熟 SDK
3. **标签配置化** — 从 config/intent_labels.json 读取而非硬编码，支持用户自定义
4. **测试图片程序化生成** — 使用 PIL 避免二进制 fixture 文件进入仓库
5. **API Key 缺失时 pytest.skip()** — 不阻塞无 API Key 的 CI 环境

## Self-Check: PASSED

- [x] config/intent_labels.json 存在，10 种标签
- [x] agents/agent1_preprocessor.py 无 anthropic/PaddleOCR import
- [x] tests/test_agent1_preprocessor.py 存在，6 个测试
- [x] 提交 7ca7491 存在（feat task1）
- [x] 提交 be28d06 存在（test RED phase）
