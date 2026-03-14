"""
迭代闭环集成测试
- 验证 capabilities.md 在 ReflectorAgent 更新后可被读取（REFLECT-04）
- 验证 AssessmentAgent 在 memory_path 指向有效文件时接口畅通（ASSESS-03）
- 验证 AssessmentAgent 实际消费 capabilities.md 规则，关键词命中时分数高于不命中（ASSESS-03 规则消费验证）
- 无真实 Claude API 调用
"""
import json
import pytest
from pathlib import Path

from memory.reflector import ReflectorAgent
from agents.agent4_assessment import AssessmentAgent


# ---- Task 1: REFLECT-04 — capabilities 可读性测试 ----

def test_capabilities_readable_after_update(tmp_path):
    """
    REFLECT-04: ReflectorAgent._update_capabilities 写入规则后，
    capabilities 文件应包含新规则文本，且返回值 == 1。
    """
    # 1. 使用 tmp_path 创建临时 capabilities 文件（初始内容为最小合法 Markdown）
    tmp_caps = tmp_path / "capabilities.md"
    tmp_caps.write_text("# 系统能力规则库\n\n初始内容。\n", encoding="utf-8")

    # 2. 构造 reflection_data
    reflection_data = {
        "root_cause": "测试根因",
        "analysis": "测试分析",
        "missed_features": ["特征A"],
        "new_rules": [
            {
                "rule": "遇到关键词X立即升级风险",
                "rationale": "历史误判"
            }
        ],
        "prevention": "测试预防措施"
    }

    # 3. 初始化 ReflectorAgent（传入 tmp_path 目录），使用 tmp capabilities 文件
    reflections_dir = tmp_path / "reflections"
    reflections_dir.mkdir()
    agent = ReflectorAgent(
        pipeline_dir=str(tmp_path / "pipeline"),
        reflections_dir=str(reflections_dir),
        capabilities_file=str(tmp_caps)
    )

    # 4. 调用 _update_capabilities
    rules_added = agent._update_capabilities("test-cap-001", reflection_data)

    # 5. 断言返回值 == 1
    assert rules_added == 1, f"期望 rules_added == 1，实际 {rules_added}"

    # 6. 读取 tmp capabilities 文件内容，断言包含新规则文本
    content = tmp_caps.read_text(encoding="utf-8")
    assert "遇到关键词X立即升级风险" in content, (
        f"capabilities.md 应包含新规则文本，实际内容：\n{content}"
    )

    # 7. 确认原有内容未被覆盖
    assert "初始内容" in content, "原有内容不应被覆盖"


# ---- Task 2: ASSESS-03 — Agent4 读取新规则的闭环测试 ----

def test_agent4_reflects_updated_rules(tmp_path):
    """
    ASSESS-03: AssessmentAgent 在 memory_path 指向有效 capabilities.md 时，
    能正常初始化并完成 run()，输出 status == "success"，
    final_risk_score 在 [0.0, 1.0]，step4.json 文件存在。
    """
    # 1. 创建包含规则条目的 capabilities.md 文件
    tmp_caps = tmp_path / "capabilities.md"
    tmp_caps.write_text(
        "# 系统能力规则库\n\n"
        "## 从误判中学习 [2026-03-14 10:00] (task: test-cap-001)\n"
        "> 根因：测试根因\n\n"
        "- **规则1**: 遇到关键词X立即升级风险\n"
        "  - 依据：历史误判\n",
        encoding="utf-8"
    )

    # 2. 初始化 AssessmentAgent，传入 tmp capabilities 文件路径
    agent = AssessmentAgent(
        rules_path="config/risk-rules.json",
        memory_path=str(tmp_caps)
    )

    # 3. 构造测试输入（参考 test_agent4_assessment.py 的 fixture 模式）
    step1 = {
        "task_id": "loop-test-001",
        "intent_label": "financial_fraud",
        "extracted_text": "转账给我可获高额回报"
    }
    step2 = {
        "avg_similarity": 0.80,
        "low_similarity_warning": False
    }
    step3 = {
        "fraud_probability": 0.85,
        "verdict": "诈骗",
        "fraud_type": "金融诈骗"
    }

    # 4. 创建输出目录
    step_dir = tmp_path / "step_output"
    step_dir.mkdir()

    # 5. 调用 agent.run()
    result = agent.run(step1, step2, step3, step_dir)

    # 6. 断言 status == "success"
    assert result["status"] == "success", (
        f"期望 status == 'success'，实际 {result['status']}，"
        f"error={result.get('error', 'N/A')}"
    )

    # 7. 断言 final_risk_score 在 [0.0, 1.0]
    score = result["final_risk_score"]
    assert isinstance(score, float), f"final_risk_score 应为 float，实际 {type(score)}"
    assert 0.0 <= score <= 1.0, f"final_risk_score={score} 超出 [0.0, 1.0] 范围"

    # 8. 断言 step_dir/step4.json 文件存在
    step4_file = step_dir / "step4.json"
    assert step4_file.exists(), "step4.json 应在 step_dir 中生成"

    # 9. 验证 step4.json 内容完整
    with open(step4_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["status"] == "success", f"step4.json 中 status 应为 success，实际 {data['status']}"
    assert data["step"] == 4, f"step4.json 中 step 应为 4，实际 {data['step']}"

    # ---- 步骤 A — 第二次运行（不含规则关键词的输入）----
    step1_no_kw = {
        "task_id": "loop-test-002",
        "intent_label": "financial_fraud",
        "extracted_text": "普通转账请求"
    }
    step_dir_no_kw = tmp_path / "step_output_no_kw"
    step_dir_no_kw.mkdir()
    result_no_kw = agent.run(step1_no_kw, step2, step3, step_dir_no_kw)
    score_without_keyword = result_no_kw["final_risk_score"]

    # ---- 步骤 B — 第三次运行（含规则关键词的输入）----
    step1_with_kw = {
        "task_id": "loop-test-003",
        "intent_label": "financial_fraud",
        "extracted_text": "关键词X 转账"
    }
    step_dir_with_kw = tmp_path / "step_output_with_kw"
    step_dir_with_kw.mkdir()
    result_with_kw = agent.run(step1_with_kw, step2, step3, step_dir_with_kw)
    score_with_keyword = result_with_kw["final_risk_score"]

    # ---- 断言：关键词命中时分数应高于不命中时 ----
    assert score_with_keyword > score_without_keyword, (
        f"包含 capabilities 规则关键词时分数({score_with_keyword:.3f}) "
        f"应高于不含时({score_without_keyword:.3f})，实际相等或更低"
    )
