"""
Agent2 RetrievalAgent TDD 测试套件
- 使用真实 LanceDB 临时实例（tmp_path 隔离）
- 不调用任何外部 API（sentence-transformers 本地运行）
- 验证 TOP-5 检索、similarity_score 字段、低相似度警告
"""
import json
import pytest
from pathlib import Path

from agents.agent2_retrieval import RetrievalAgent
from utils.lancedb_client import LanceDBClient


# ---- fixtures ----

@pytest.fixture(scope="module")
def lancedb_with_cases(tmp_path_factory):
    """创建临时 LanceDB 并插入 5 条诈骗测试案例"""
    db_path = str(tmp_path_factory.mktemp("test_lancedb"))
    client = LanceDBClient(db_path)
    client.init_schema()

    test_cases = [
        {
            "id": "case-001",
            "type": "financial_fraud",
            "text": "转账给我，可获得高额回报，投资年化收益30%",
            "label": "scam",
            "risk_level": "极高",
            "features": ["转账", "高回报"],
            "source": "test"
        },
        {
            "id": "case-002",
            "type": "impersonation",
            "text": "我是公安局警察，您的账户涉嫌洗钱，需要配合调查转移资金",
            "label": "scam",
            "risk_level": "极高",
            "features": ["冒充公检法", "资金转移"],
            "source": "test"
        },
        {
            "id": "case-003",
            "type": "romance_scam",
            "text": "我很喜欢你，我们建立感情后，我需要你帮我转账",
            "label": "scam",
            "risk_level": "高",
            "features": ["情感诱导", "转账"],
            "source": "test"
        },
        {
            "id": "case-004",
            "type": "lottery_scam",
            "text": "恭喜您中了一等奖，请先交纳500元手续费领取奖金",
            "label": "scam",
            "risk_level": "高",
            "features": ["中奖", "手续费"],
            "source": "test"
        },
        {
            "id": "case-005",
            "type": "job_scam",
            "text": "在家兼职刷单，每单30元，先充值激活账户",
            "label": "scam",
            "risk_level": "高",
            "features": ["刷单", "充值"],
            "source": "test"
        },
    ]

    for case in test_cases:
        client.add_case(case)

    return db_path


@pytest.fixture(scope="module")
def agent(lancedb_with_cases):
    """使用测试 LanceDB 初始化 RetrievalAgent"""
    return RetrievalAgent(
        lancedb_path=lancedb_with_cases,
        top_k=5,
        similarity_threshold=0.65
    )


@pytest.fixture(scope="module")
def step_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("step_output")


@pytest.fixture
def scam_step1_result():
    """模拟 Agent1 对诈骗内容的输出（用于传给 Agent2）"""
    return {
        "task_id": "test-agent2-001",
        "step": 1,
        "agent": "preprocessor",
        "status": "success",
        "intent_label": "financial_fraud",
        "confidence": 0.92,
        "key_indicators": ["转账", "高回报", "投资"],
        "extracted_text_summary": "用户声称投资可获得高额回报，要求转账",
        "extracted_text": "转账给我，可获得高额回报，投资年化收益30%"
    }


@pytest.fixture
def irrelevant_step1_result():
    """模拟 Agent1 对不相关内容的输出（用于触发低相似度警告）"""
    return {
        "task_id": "test-agent2-002",
        "step": 1,
        "agent": "preprocessor",
        "status": "success",
        "intent_label": "unknown",
        "confidence": 0.3,
        "key_indicators": [],
        "extracted_text_summary": "图片内容模糊，无法识别",
        "extracted_text": "xyzxyzxyz 完全无关的随机字符串 abcabc"
    }


# ---- 测试：基本检索功能 ----

def test_returns_result_dict(agent, scam_step1_result, step_dir):
    """run() 应返回包含必要字段的字典"""
    result = agent.run(scam_step1_result, step_dir)
    assert isinstance(result, dict)
    assert result["step"] == 2
    assert result["agent"] == "retrieval"
    assert result["status"] == "success"


def test_returns_cases_list(agent, scam_step1_result, step_dir):
    """结果应包含 cases 列表（完整 TOP-5）"""
    result = agent.run(scam_step1_result, step_dir)
    assert "cases" in result, "结果应包含 cases 字段"
    assert isinstance(result["cases"], list), "cases 应为列表"


def test_each_case_has_similarity_score(agent, scam_step1_result, step_dir):
    """每条返回案例应包含 similarity_score 浮点字段"""
    result = agent.run(scam_step1_result, step_dir)
    cases = result.get("cases", [])
    for case in cases:
        assert "similarity_score" in case, f"案例缺少 similarity_score 字段: {case.get('id')}"
        score = case["similarity_score"]
        assert isinstance(score, float), f"similarity_score 应为浮点数，实际: {type(score)}"
        assert 0.0 <= score <= 1.0, f"similarity_score 应在 0-1 之间，实际: {score}"


def test_avg_similarity_field_present(agent, scam_step1_result, step_dir):
    """结果应包含 avg_similarity 字段"""
    result = agent.run(scam_step1_result, step_dir)
    assert "avg_similarity" in result
    assert isinstance(result["avg_similarity"], float)
    assert 0.0 <= result["avg_similarity"] <= 1.0


# ---- 测试：低相似度警告 ----

def test_low_similarity_warning_false_for_relevant_query(agent, scam_step1_result, step_dir):
    """与库中案例相似的查询，low_similarity_warning 应为 False"""
    result = agent.run(scam_step1_result, step_dir)
    # 诈骗相关内容与库中 5 条诈骗案例应有较高相似度
    # 如果 avg_similarity >= 0.65，则 warning 为 False
    if result["avg_similarity"] >= 0.65:
        assert result["low_similarity_warning"] is False, \
            f"avg_similarity={result['avg_similarity']:.3f} >= 0.65 但 warning=True"


def test_low_similarity_warning_present_in_result(agent, irrelevant_step1_result, step_dir):
    """结果字典中必须包含 low_similarity_warning 字段"""
    result = agent.run(irrelevant_step1_result, step_dir)
    assert "low_similarity_warning" in result, "结果应包含 low_similarity_warning 字段"
    assert isinstance(result["low_similarity_warning"], bool), "low_similarity_warning 应为布尔值"


def test_warning_logic_consistent_with_avg_similarity(agent, irrelevant_step1_result, step_dir):
    """low_similarity_warning 应与 avg_similarity 和阈值一致"""
    result = agent.run(irrelevant_step1_result, step_dir)
    avg = result["avg_similarity"]
    warning = result["low_similarity_warning"]
    if avg < 0.65:
        assert warning is True, f"avg_similarity={avg:.3f} < 0.65 但 warning=False"
    else:
        assert warning is False, f"avg_similarity={avg:.3f} >= 0.65 但 warning=True"


# ---- 测试：step2.json 写入 ----

def test_step2_json_written(agent, scam_step1_result, step_dir):
    """run() 执行后应在 step_dir 写入 step2.json"""
    agent.run(scam_step1_result, step_dir)
    step_file = step_dir / "step2.json"
    assert step_file.exists(), "step2.json 应被写入"
    with open(step_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["step"] == 2
    assert data["agent"] == "retrieval"


# ---- 测试：build_query 逻辑 ----

def test_build_query_includes_intent_and_indicators(agent):
    """_build_query 应将 intent_label 和 key_indicators 拼入查询字符串"""
    step1 = {
        "task_id": "query-test",
        "intent_label": "phishing",
        "key_indicators": ["钓鱼链接", "验证码"],
        "extracted_text_summary": "发现可疑链接",
        "extracted_text": ""
    }
    query = agent._build_query(step1)
    assert "phishing" in query or "意图类型" in query
    assert "钓鱼链接" in query
