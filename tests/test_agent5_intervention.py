"""
Agent5 InterventionAgent TDD 测试套件
- mock agents.agent5_intervention.send_alert 拦截所有通知调用
- 验证报告文件生成、通知推送逻辑、监护人联动、反馈标志
- 不依赖真实邮件/飞书/钉钉账号
"""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agents.agent5_intervention import InterventionAgent


# ---- fixtures ----

@pytest.fixture
def reports_dir(tmp_path):
    d = tmp_path / "reports"
    d.mkdir()
    return d


@pytest.fixture
def conversations_dir(tmp_path):
    d = tmp_path / "conversations"
    d.mkdir()
    return d


@pytest.fixture
def step_dir(tmp_path):
    d = tmp_path / "steps"
    d.mkdir()
    return d


@pytest.fixture
def agent(reports_dir, conversations_dir):
    return InterventionAgent(
        reports_dir=str(reports_dir),
        conversations_dir=str(conversations_dir)
    )


@pytest.fixture
def step1_result():
    return {
        "task_id": "test-a5-001",
        "step": 1, "agent": "preprocessor", "status": "success",
        "intent_label": "financial_fraud", "confidence": 0.92,
        "key_indicators": ["转账", "高回报"],
        "extracted_text_summary": "用户收到诈骗信息",
        "extracted_text": "转账给我可获高额回报",
        "source": "wechat", "file_name": "test.png"
    }


@pytest.fixture
def step2_result():
    return {
        "task_id": "test-a5-001",
        "step": 2, "agent": "retrieval", "status": "success",
        "relevant_cases": [{"id": "case-001", "similarity": 0.85, "description": "诈骗案例", "verdict": "诈骗"}],
        "avg_similarity": 0.85, "low_similarity_warning": False, "total_retrieved": 1
    }


@pytest.fixture
def step3_result():
    return {
        "task_id": "test-a5-001",
        "step": 3, "agent": "discrimination", "status": "success",
        "fraud_probability": 0.92, "verdict": "诈骗",
        "fraud_type": "金融诈骗",
        "evidence": ["要求转账", "高回报承诺"],
        "counter_evidence": [],
        "explanation": "明显诈骗特征，要求立即转账。"
    }


@pytest.fixture
def step4_high_risk():
    return {
        "task_id": "test-a5-001",
        "step": 4, "agent": "assessment", "status": "success",
        "base_score": 0.92, "final_risk_score": 0.95,
        "risk_level": "极高", "risk_level_key": "extreme_high",
        "requires_guardian_alert": True,
        "rule_adjustments": [], "total_adjustment": 0.0
    }


@pytest.fixture
def step4_medium_risk():
    return {
        "task_id": "test-a5-002",
        "step": 4, "agent": "assessment", "status": "success",
        "base_score": 0.60, "final_risk_score": 0.60,
        "risk_level": "中", "risk_level_key": "medium",
        "requires_guardian_alert": False,
        "rule_adjustments": [], "total_adjustment": 0.0
    }


@pytest.fixture
def step4_low_risk():
    return {
        "task_id": "test-a5-003",
        "step": 4, "agent": "assessment", "status": "success",
        "base_score": 0.20, "final_risk_score": 0.20,
        "risk_level": "安全", "risk_level_key": "safe",
        "requires_guardian_alert": False,
        "rule_adjustments": [], "total_adjustment": 0.0
    }


# ---- 测试函数 ----

def test_returns_required_fields(agent, step1_result, step2_result, step3_result, step4_medium_risk, step_dir):
    """run() 应返回包含必要字段的字典"""
    with patch("agents.agent5_intervention.send_alert", return_value=True):
        result = agent.run(step1_result, step2_result, step3_result, step4_medium_risk, step_dir)
    assert result["step"] == 5
    assert result["agent"] == "intervention"
    assert result["status"] == "success"
    assert "report_path" in result
    assert "awaiting_feedback" in result


def test_awaiting_feedback_is_true(agent, step1_result, step2_result, step3_result, step4_medium_risk, step_dir):
    """INTERV-04: awaiting_feedback 应为 True"""
    with patch("agents.agent5_intervention.send_alert", return_value=True):
        result = agent.run(step1_result, step2_result, step3_result, step4_medium_risk, step_dir)
    assert result["awaiting_feedback"] is True


def test_report_generated_for_medium_risk(agent, step1_result, step2_result, step3_result, step4_medium_risk, step_dir, reports_dir):
    """INTERV-02: 中风险时生成报告文件，且包含关键内容"""
    with patch("agents.agent5_intervention.send_alert", return_value=True):
        result = agent.run(step1_result, step2_result, step3_result, step4_medium_risk, step_dir)
    report_path = Path(result["report_path"])
    assert report_path.exists(), f"报告文件不存在: {report_path}"
    content = report_path.read_text(encoding="utf-8")
    assert "诈骗分析报告" in content
    assert step1_result["task_id"] in content


def test_report_generated_for_low_risk(agent, step1_result, step2_result, step3_result, step4_low_risk, step_dir):
    """低风险也应生成报告文件，但不推送通知"""
    result = agent.run(step1_result, step2_result, step3_result, step4_low_risk, step_dir)
    assert result["status"] == "success"
    report_path = Path(result["report_path"])
    assert report_path.exists()


def test_alert_sent_for_medium_risk(agent, step1_result, step2_result, step3_result, step4_medium_risk, step_dir):
    """INTERV-01: 中风险时 send_alert 应被调用一次"""
    with patch("agents.agent5_intervention.send_alert", return_value=True) as mock_alert:
        result = agent.run(step1_result, step2_result, step3_result, step4_medium_risk, step_dir)
    mock_alert.assert_called_once()
    assert result["notifications_sent"][0]["sent"] is True


def test_alert_not_sent_for_low_risk(agent, step1_result, step2_result, step3_result, step4_low_risk, step_dir):
    """低风险时 send_alert 不应被调用，notifications_sent 应为空"""
    with patch("agents.agent5_intervention.send_alert", return_value=True) as mock_alert:
        result = agent.run(step1_result, step2_result, step3_result, step4_low_risk, step_dir)
    mock_alert.assert_not_called()
    assert result["notifications_sent"] == []


def test_guardian_alert_triggered_for_extreme_risk(agent, step1_result, step2_result, step3_result, step4_high_risk, step_dir):
    """INTERV-03: 极高风险时 guardian_alerted 字段存在且为布尔型"""
    with patch("agents.agent5_intervention.send_alert", return_value=True):
        with patch.object(agent.guardian_email, "send", return_value=True):
            result = agent.run(step1_result, step2_result, step3_result, step4_high_risk, step_dir)
    # guardian_alerted 字段必须存在且为布尔型
    assert "guardian_alerted" in result
    assert isinstance(result["guardian_alerted"], bool)


def test_guardian_alert_with_email_configured(step1_result, step2_result, step3_result, step4_high_risk, tmp_path):
    """INTERV-03: 配置了 GUARDIAN_EMAIL 时，guardian_email.send 被调用且 guardian_alerted=True"""
    agent = InterventionAgent(reports_dir=str(tmp_path / "r"), conversations_dir=str(tmp_path / "c"))
    step_dir = tmp_path / "steps"
    step_dir.mkdir()
    with patch("agents.agent5_intervention.send_alert", return_value=True):
        with patch.object(agent.guardian_email, "send", return_value=True) as mock_guardian:
            agent.guardian_email.smtp_host = "smtp.qq.com"
            agent.guardian_email.username = "test@qq.com"
            agent.guardian_email.password = "test"
            agent.guardian_email.to_addrs = ["guardian@example.com"]
            result = agent.run(step1_result, step2_result, step3_result, step4_high_risk, step_dir)
    mock_guardian.assert_called_once()
    assert result["guardian_alerted"] is True


def test_step5_json_written(agent, step1_result, step2_result, step3_result, step4_medium_risk, step_dir):
    """run() 执行后应在 step_dir 写入合法的 step5.json"""
    with patch("agents.agent5_intervention.send_alert", return_value=True):
        agent.run(step1_result, step2_result, step3_result, step4_medium_risk, step_dir)
    step_file = step_dir / "step5.json"
    assert step_file.exists()
    data = json.load(open(step_file, encoding="utf-8"))
    assert data["step"] == 5
    assert data["agent"] == "intervention"
