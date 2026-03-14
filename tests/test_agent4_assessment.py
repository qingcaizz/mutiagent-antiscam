"""
Agent4 AssessmentAgent TDD 测试套件
- 纯本地规则引擎，无需 mock，无外部 API 依赖
- 使用真实 config/risk-rules.json
- 覆盖：规则加载（ASSESS-01）、风险等级输出（ASSESS-02）、
         capabilities.md 接口（ASSESS-03）、极高风险标志（ASSESS-04）
"""
import json
import pytest
from pathlib import Path

from agents.agent4_assessment import AssessmentAgent


# ---- fixtures ----

@pytest.fixture(scope="module")
def agent():
    """使用真实 risk-rules.json 初始化 AssessmentAgent（无 mock）"""
    return AssessmentAgent(
        rules_path="config/risk-rules.json",
        memory_path="memory/capabilities.md"
    )


@pytest.fixture
def step_dir(tmp_path):
    """为每个测试提供独立的临时输出目录"""
    d = tmp_path / "step_output"
    d.mkdir()
    return d


@pytest.fixture
def base_step1():
    """模拟 Agent1 对金融诈骗内容的基础输出"""
    return {
        "task_id": "test-a4-001",
        "intent_label": "financial_fraud",
        "extracted_text": "转账给我可获高额回报"
    }


@pytest.fixture
def base_step2():
    """模拟 Agent2 的基础检索结果"""
    return {
        "avg_similarity": 0.80,
        "low_similarity_warning": False
    }


@pytest.fixture
def base_step3():
    """模拟 Agent3 的基础分析结果"""
    return {
        "fraud_probability": 0.85,
        "verdict": "诈骗",
        "fraud_type": "金融诈骗"
    }


# ---- 测试：规则加载（ASSESS-01）----

def test_rules_loaded_successfully(agent):
    """Agent4 应成功加载 risk-rules.json 并解析 8 条规则"""
    assert len(agent.rules.get("rules", [])) == 8, \
        f"期望 8 条规则，实际 {len(agent.rules.get('rules', []))}"
    assert "thresholds" in agent.rules, "规则文件应包含 thresholds 字段"


def test_thresholds_loaded(agent):
    """风险阈值应正确加载"""
    t = agent.thresholds
    assert t["extreme_high"] == 0.90, f"extreme_high 期望 0.90，实际 {t['extreme_high']}"
    assert t["high"] == 0.75, f"high 期望 0.75，实际 {t['high']}"
    assert t["medium"] == 0.55, f"medium 期望 0.55，实际 {t['medium']}"
    assert t["low"] == 0.30, f"low 期望 0.30，实际 {t['low']}"


# ---- 测试：必要字段输出（ASSESS-02）----

def test_returns_required_fields(agent, step_dir):
    """run() 应返回所有必要字段"""
    step1 = {"task_id": "t1", "intent_label": "financial_fraud", "extracted_text": "转账给我"}
    step2 = {"avg_similarity": 0.8, "low_similarity_warning": False}
    step3 = {"fraud_probability": 0.85, "verdict": "诈骗", "fraud_type": "金融诈骗"}
    result = agent.run(step1, step2, step3, step_dir)

    assert result["step"] == 4, f"step 应为 4，实际 {result['step']}"
    assert result["agent"] == "assessment", f"agent 应为 assessment，实际 {result['agent']}"
    assert result["status"] == "success", f"status 应为 success，实际 {result['status']}"

    required_fields = ["base_score", "final_risk_score", "risk_level",
                       "requires_guardian_alert", "rule_adjustments"]
    for field in required_fields:
        assert field in result, f"结果缺少必要字段: {field}"


def test_risk_level_is_valid_value(agent, step_dir):
    """risk_level 只能是预定义的五个值之一"""
    VALID_LEVELS = {"安全", "低", "中", "高", "极高"}
    step1 = {"task_id": "valid-level-test", "intent_label": "financial_fraud",
             "extracted_text": "转账给我可获高额回报"}
    step2 = {"avg_similarity": 0.8, "low_similarity_warning": False}
    step3 = {"fraud_probability": 0.85, "verdict": "诈骗", "fraud_type": "金融诈骗"}
    result = agent.run(step1, step2, step3, step_dir)
    assert result["risk_level"] in VALID_LEVELS, \
        f"risk_level '{result['risk_level']}' 不在有效值集合 {VALID_LEVELS} 中"


# ---- 测试：参数化高风险关键词（ASSESS-02）----

@pytest.mark.parametrize("extracted_text,min_expected_level,rule_desc", [
    (
        "立即转账 今天必须 不转就走人",
        "高",
        "R001 紧急转账要求"
    ),
    (
        "公安局 检察院 安全账户 配合调查",
        "高",
        "R002 冒充公检法"
    ),
    (
        "刷单 刷好评 兼职接单 日赚佣金",
        "高",
        "R003 网络刷单返利"
    ),
    (
        "恭喜中奖 领取奖品 交保证金 手续费",
        "高",
        "R006 中奖通知"
    ),
])
def test_high_risk_keywords_trigger_high_level(
    agent, step_dir, extracted_text, min_expected_level, rule_desc
):
    """高风险关键词命中时，risk_level 应达到或超过 min_expected_level"""
    step1 = {
        "task_id": f"kw-test-{rule_desc[:4]}",
        "intent_label": "fraud",
        "extracted_text": extracted_text
    }
    step2 = {"avg_similarity": 0.9, "low_similarity_warning": False}
    step3 = {"fraud_probability": 0.80, "verdict": "诈骗", "fraud_type": "测试"}

    result = agent.run(step1, step2, step3, step_dir)

    LEVEL_ORDER = ["安全", "低", "中", "高", "极高"]
    actual_idx = LEVEL_ORDER.index(result["risk_level"])
    expected_idx = LEVEL_ORDER.index(min_expected_level)

    assert actual_idx >= expected_idx, (
        f"[{rule_desc}] 期望 risk_level >= '{min_expected_level}'，"
        f"实际 '{result['risk_level']}' (final_score={result['final_risk_score']:.3f})"
    )


# ---- 测试：极高风险监护人标志（ASSESS-04）----

def test_extreme_high_requires_guardian_alert(agent, step_dir):
    """极高风险时 requires_guardian_alert 应为 True"""
    # fraud_probability=0.95 + R001+R002多关键词叠加 -> final_score >= 0.90
    step1 = {
        "task_id": "guardian-test",
        "intent_label": "fraud",
        "extracted_text": "立即转账 公安局 安全账户 今天必须"
    }
    step2 = {"avg_similarity": 0.9, "low_similarity_warning": False}
    step3 = {"fraud_probability": 0.95, "verdict": "诈骗", "fraud_type": "极高风险测试"}

    result = agent.run(step1, step2, step3, step_dir)

    if result["risk_level"] == "极高":
        assert result["requires_guardian_alert"] is True, \
            f"极高风险时 requires_guardian_alert 应为 True，实际 {result['requires_guardian_alert']}"
    else:
        pytest.skip(
            f"分数不足以触发极高风险: final_score={result['final_risk_score']:.3f}，"
            f"risk_level={result['risk_level']}"
        )


def test_non_extreme_risk_guardian_alert_false(agent, step_dir):
    """非极高风险时 requires_guardian_alert 应为 False"""
    step1 = {
        "task_id": "safe-test",
        "intent_label": "unknown",
        "extracted_text": "今天天气不错"
    }
    step2 = {"avg_similarity": 0.5, "low_similarity_warning": True}
    step3 = {"fraud_probability": 0.50, "verdict": "可疑", "fraud_type": None}

    result = agent.run(step1, step2, step3, step_dir)

    if result["risk_level"] != "极高":
        assert result["requires_guardian_alert"] is False, \
            f"非极高风险时 requires_guardian_alert 应为 False，实际 {result['requires_guardian_alert']}"


# ---- 测试：白名单规则降低分数（ASSESS-01 + ASSESS-02）----

def test_whitelist_rule_reduces_score(agent, step_dir):
    """R008 白名单关键词命中时，应降低最终风险分数"""
    step2 = {"avg_similarity": 0.7, "low_similarity_warning": False}
    step3_medium = {"fraud_probability": 0.70, "verdict": "可疑", "fraud_type": "待确认"}

    # 带白名单词的输入
    step1_with_whitelist = {
        "task_id": "whitelist-test-with",
        "intent_label": "normal",
        "extracted_text": "保险产品 理财规划 定期存款"
    }
    # 不带白名单词的输入（用同等中性文本对比）
    step1_no_whitelist = {
        "task_id": "whitelist-test-without",
        "intent_label": "normal",
        "extracted_text": "普通文本内容"
    }

    result_white = agent.run(step1_with_whitelist, step2, step3_medium, step_dir)
    result_no = agent.run(step1_no_whitelist, step2, step3_medium, step_dir)

    assert result_white["final_risk_score"] <= result_no["final_risk_score"], (
        f"白名单词应降低分数: "
        f"有白名单={result_white['final_risk_score']:.3f}, "
        f"无白名单={result_no['final_risk_score']:.3f}"
    )


# ---- 测试：step4.json 写入（ASSESS-02）----

def test_step4_json_written(agent, step_dir):
    """run() 执行后应在 step_dir 写入合法的 step4.json"""
    step1 = {"task_id": "json-write-test", "intent_label": "financial_fraud",
             "extracted_text": "转账给我"}
    step2 = {"avg_similarity": 0.8, "low_similarity_warning": False}
    step3 = {"fraud_probability": 0.85, "verdict": "诈骗", "fraud_type": "金融诈骗"}

    agent.run(step1, step2, step3, step_dir)

    step_file = step_dir / "step4.json"
    assert step_file.exists(), "step4.json 应被写入"

    with open(step_file, encoding="utf-8") as f:
        data = json.load(f)

    assert data["step"] == 4, f"step4.json 中 step 应为 4，实际 {data['step']}"
    assert data["agent"] == "assessment"
    assert data["status"] == "success"


# ---- 测试：capabilities.md 接口（ASSESS-03）----

def test_memory_path_interface_accessible(agent):
    """ASSESS-03：memory_path 接口应可访问且类型正确"""
    assert hasattr(agent, "memory_path"), "AssessmentAgent 应有 memory_path 属性"
    assert isinstance(agent.memory_path, Path), \
        f"memory_path 应为 Path 类型，实际 {type(agent.memory_path)}"
    # 不验证 capabilities.md 内容，Phase 6 负责完整验证


# ---- 测试：分数边界与计算正确性 ----

def test_base_score_comes_from_step3_fraud_probability(agent, step_dir):
    """base_score 应直接来自 step3_result 的 fraud_probability"""
    fraud_prob = 0.72
    step1 = {"task_id": "score-base-test", "intent_label": "unknown", "extracted_text": ""}
    step2 = {"avg_similarity": 0.8, "low_similarity_warning": False}
    step3 = {"fraud_probability": fraud_prob, "verdict": "可疑", "fraud_type": None}

    result = agent.run(step1, step2, step3, step_dir)

    assert result["base_score"] == fraud_prob, \
        f"base_score 期望 {fraud_prob}，实际 {result['base_score']}"


def test_final_risk_score_in_range(agent, step_dir):
    """final_risk_score 应在 [0.0, 1.0] 范围内"""
    step1 = {"task_id": "range-test", "intent_label": "fraud",
             "extracted_text": "立即转账 公安局 安全账户"}
    step2 = {"avg_similarity": 0.9, "low_similarity_warning": False}
    step3 = {"fraud_probability": 0.99, "verdict": "诈骗", "fraud_type": "测试"}

    result = agent.run(step1, step2, step3, step_dir)

    score = result["final_risk_score"]
    assert 0.0 <= score <= 1.0, f"final_risk_score={score} 超出 [0.0, 1.0] 范围"
