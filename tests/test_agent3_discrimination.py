"""
Agent3 DiscriminationAgent TDD 测试套件
- mock Qwen3.5 OpenAI SDK 调用（不发出真实请求）
- 验证返回字段格式、fraud_probability 范围、verdict 合法值
- 验证 step3.json 写入、降级失败处理
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agents.agent3_discrimination import DiscriminationAgent


# ---- fixtures ----

@pytest.fixture
def step_dir(tmp_path):
    """返回函数级别隔离的临时目录"""
    return tmp_path


@pytest.fixture
def step1_result():
    """模拟 Agent1 输出"""
    return {
        "task_id": "test-agent3-001",
        "step": 1,
        "agent": "preprocessor",
        "status": "success",
        "intent_label": "financial_fraud",
        "confidence": 0.92,
        "key_indicators": ["转账", "高回报"],
        "extracted_text_summary": "用户要求转账，承诺高额回报",
        "extracted_text": "转账给我，可获高额回报",
        "reasoning": "包含明显资金转移和高回报诱导特征",
    }


@pytest.fixture
def step2_result():
    """模拟 Agent2 输出"""
    return {
        "task_id": "test-agent3-001",
        "step": 2,
        "agent": "retrieval",
        "status": "success",
        "avg_similarity": 0.85,
        "low_similarity_warning": False,
        "relevant_cases": [
            {
                "id": "case-001",
                "similarity": 0.85,
                "similarity_score": 0.85,
                "description": "要求转账并承诺高额回报的金融诈骗案例",
                "verdict": "诈骗",
            }
        ],
        "cases": [
            {
                "id": "case-001",
                "similarity_score": 0.85,
                "description": "要求转账并承诺高额回报的金融诈骗案例",
                "verdict": "诈骗",
            }
        ],
    }


@pytest.fixture
def agent_with_mock():
    """
    使用 unittest.mock.patch 打补丁，mock Qwen3.5 OpenAI API。
    - patch 目标：agents.agent3_discrimination.OpenAI
    - mock client.chat.completions.create 返回合法 JSON
    """
    mock_content = MagicMock()
    mock_content.message = MagicMock()
    mock_content.message.content = json.dumps({
        "fraud_probability": 0.92,
        "verdict": "诈骗",
        "fraud_type": "金融诈骗",
        "evidence": ["要求转账", "高回报承诺"],
        "counter_evidence": [],
        "explanation": "明显诈骗特征：要求转账并承诺高额回报",
        "case_reference_ids": ["case-001"],
    })

    mock_response = MagicMock()
    mock_response.choices = [mock_content]

    with patch("agents.agent3_discrimination.OpenAI") as mock_openai:
        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create.return_value = mock_response
        yield DiscriminationAgent()


# ---- 测试函数 ----

def test_returns_dict_with_required_fields(agent_with_mock, step1_result, step2_result, step_dir):
    """run() 应返回含必要字段的字典"""
    agent = agent_with_mock
    result = agent.run(step1_result, step2_result, step_dir)

    assert isinstance(result, dict), "返回值应为 dict"
    assert result["step"] == 3, f"step 应为 3，实际: {result.get('step')}"
    assert result["agent"] == "discrimination", f"agent 应为 discrimination，实际: {result.get('agent')}"
    assert result["status"] == "success", f"status 应为 success，实际: {result.get('status')}"


def test_fraud_probability_in_range(agent_with_mock, step1_result, step2_result, step_dir):
    """fraud_probability 应为 0.0-1.0 之间的浮点数"""
    agent = agent_with_mock
    result = agent.run(step1_result, step2_result, step_dir)

    assert "fraud_probability" in result, "结果应包含 fraud_probability 字段"
    assert isinstance(result["fraud_probability"], float), (
        f"fraud_probability 应为 float，实际: {type(result['fraud_probability'])}"
    )
    assert 0.0 <= result["fraud_probability"] <= 1.0, (
        f"fraud_probability 应在 0-1 之间，实际: {result['fraud_probability']}"
    )


def test_verdict_is_valid_value(agent_with_mock, step1_result, step2_result, step_dir):
    """verdict 只能是 诈骗/可疑/正常 之一"""
    agent = agent_with_mock
    result = agent.run(step1_result, step2_result, step_dir)

    VALID_VERDICTS = {"诈骗", "可疑", "正常"}
    assert result["verdict"] in VALID_VERDICTS, (
        f"verdict 应为 {VALID_VERDICTS} 之一，实际: {result.get('verdict')}"
    )


def test_explanation_is_non_empty_string(agent_with_mock, step1_result, step2_result, step_dir):
    """explanation 应为非空字符串"""
    agent = agent_with_mock
    result = agent.run(step1_result, step2_result, step_dir)

    assert "explanation" in result, "结果应包含 explanation 字段"
    assert isinstance(result["explanation"], str), (
        f"explanation 应为 str，实际: {type(result['explanation'])}"
    )
    assert len(result["explanation"]) > 0, "explanation 不应为空字符串"


def test_step3_json_written_correctly(agent_with_mock, step1_result, step2_result, step_dir):
    """run() 后应在 step_dir 写入合法的 step3.json"""
    agent = agent_with_mock
    agent.run(step1_result, step2_result, step_dir)

    step_file = step_dir / "step3.json"
    assert step_file.exists(), "step3.json 应被写入到 step_dir"

    with open(step_file, encoding="utf-8") as f:
        data = json.load(f)

    assert data["step"] == 3, f"step3.json 中 step 应为 3，实际: {data.get('step')}"
    assert data["agent"] == "discrimination", (
        f"step3.json 中 agent 应为 discrimination，实际: {data.get('agent')}"
    )


def test_evidence_is_list(agent_with_mock, step1_result, step2_result, step_dir):
    """evidence 字段应为 list 类型"""
    agent = agent_with_mock
    result = agent.run(step1_result, step2_result, step_dir)

    assert isinstance(result["evidence"], list), (
        f"evidence 应为 list，实际: {type(result.get('evidence'))}"
    )


def test_graceful_failure_on_api_error(step1_result, step2_result, step_dir):
    """API 调用失败时，Agent3 应优雅降级而非崩溃"""
    with patch("agents.agent3_discrimination.OpenAI") as mock_openai:
        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create.side_effect = Exception("API error")

        result = DiscriminationAgent().run(step1_result, step2_result, step_dir)

    assert result["status"] == "failed", (
        f"API 错误时 status 应为 failed，实际: {result.get('status')}"
    )
    assert "error" in result, "失败结果应包含 error 字段"
    assert result.get("fraud_probability") == 0.5, (
        f"降级时 fraud_probability 应为 0.5，实际: {result.get('fraud_probability')}"
    )


def test_task_id_propagated(agent_with_mock, step1_result, step2_result, step_dir):
    """task_id 应从 step1_result 透传到返回结果"""
    agent = agent_with_mock
    result = agent.run(step1_result, step2_result, step_dir)

    assert result["task_id"] == step1_result["task_id"], (
        f"task_id 应透传，期望: {step1_result['task_id']}，实际: {result.get('task_id')}"
    )
