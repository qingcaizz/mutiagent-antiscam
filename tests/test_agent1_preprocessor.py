"""
Agent1 PreprocessorAgent TDD 测试套件
- 真实调用 GLM-4.6V 和 Qwen3.5 API
- 需要环境变量：ZHIPU_API_KEY, NAU_API_KEY
- 测试图片：程序化生成（红色背景含诈骗文字 / 纯色图片）
"""
import json
import os
import pytest
from pathlib import Path
from PIL import Image, ImageDraw

from agents.agent1_preprocessor import PreprocessorAgent


# ---- fixtures ----

@pytest.fixture(scope="module")
def agent():
    """初始化 PreprocessorAgent，要求 API Key 已配置"""
    zhipu_key = os.environ.get("ZHIPU_API_KEY")
    nau_key = os.environ.get("NAU_API_KEY")
    if not zhipu_key or not nau_key:
        pytest.skip("需要 ZHIPU_API_KEY 和 NAU_API_KEY 环境变量")
    return PreprocessorAgent()


@pytest.fixture(scope="module")
def scam_image_path(tmp_path_factory):
    """生成含诈骗文字的测试图片（红色背景，白色文字）"""
    tmp = tmp_path_factory.mktemp("fixtures")
    img_path = tmp / "scam_test.png"
    img = Image.new("RGB", (400, 200), color=(200, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.text((20, 80), "恭喜您中奖！请转账5000元激活奖金", fill=(255, 255, 255))
    img.save(str(img_path))
    return str(img_path)


@pytest.fixture(scope="module")
def icon_image_path(tmp_path_factory):
    """生成无文字的纯色图片（测试无文字路径）"""
    tmp = tmp_path_factory.mktemp("fixtures")
    img_path = tmp / "icon_test.png"
    img = Image.new("RGB", (100, 100), color=(100, 149, 237))
    img.save(str(img_path))
    return str(img_path)


@pytest.fixture(scope="module")
def step_dir(tmp_path_factory):
    """临时步骤输出目录"""
    return tmp_path_factory.mktemp("step_output")


# ---- 测试：标签配置加载 ----

def test_valid_labels_loaded(agent):
    """Agent 初始化后，valid_labels 应包含来自配置的标签 ID 列表"""
    assert hasattr(agent, "valid_labels"), "PreprocessorAgent 应有 valid_labels 属性"
    assert len(agent.valid_labels) >= 5, "至少应有 5 种意图标签"
    assert "unknown" in agent.valid_labels, "应包含 unknown 标签"
    assert "financial_fraud" in agent.valid_labels, "应包含 financial_fraud 标签"


# ---- 测试：图片输入完整流程 ----

def test_scam_image_returns_valid_output_format(agent, scam_image_path, step_dir):
    """含诈骗文字的图片应返回符合规格的输出字典"""
    task_input = {
        "task_id": "test-001",
        "file_type": "image",
        "file_path": scam_image_path,
        "source": "wechat",
        "file_name": "scam_test.png",
    }
    result = agent.run(task_input, step_dir)

    # 必须包含的字段
    assert result["status"] == "success", f"应成功，实际: {result.get('error')}"
    assert "intent_label" in result
    assert "confidence" in result
    assert "key_indicators" in result
    assert "extracted_text_summary" in result

    # 字段类型验证
    assert isinstance(result["intent_label"], str), "intent_label 应为字符串"
    assert result["intent_label"] in agent.valid_labels, (
        f"intent_label '{result['intent_label']}' 不在合法标签列表中"
    )
    assert 0.0 <= result["confidence"] <= 1.0, (
        f"confidence 应在 0-1 之间，实际: {result['confidence']}"
    )
    assert isinstance(result["key_indicators"], list), "key_indicators 应为列表"
    assert isinstance(result["extracted_text_summary"], str), (
        "extracted_text_summary 应为字符串"
    )
    assert len(result["extracted_text_summary"]) > 0, "extracted_text_summary 不应为空"


def test_scam_image_detected_as_suspicious(agent, scam_image_path, step_dir):
    """含明显诈骗特征的图片，intent_label 不应为 normal_business 或 personal_communication"""
    task_input = {
        "task_id": "test-002",
        "file_type": "image",
        "file_path": scam_image_path,
        "source": "wechat",
        "file_name": "scam_test.png",
    }
    result = agent.run(task_input, step_dir)
    non_scam_labels = {"normal_business", "personal_communication"}
    assert result["intent_label"] not in non_scam_labels, (
        f"诈骗图片被误判为正常：{result['intent_label']}"
    )


def test_icon_image_does_not_crash(agent, icon_image_path, step_dir):
    """纯色无文字图片不应导致崩溃，应返回有效结果"""
    task_input = {
        "task_id": "test-003",
        "file_type": "image",
        "file_path": icon_image_path,
        "source": "wechat",
        "file_name": "icon_test.png",
    }
    try:
        result = agent.run(task_input, step_dir)
        assert "intent_label" in result, "结果应包含 intent_label 字段"
        assert "status" in result, "结果应包含 status 字段"
    except Exception as e:
        pytest.fail(f"纯图标图片不应抛出未捕获异常: {e}")


# ---- 测试：邮件输入路径 ----

def test_email_input_returns_valid_output(agent, step_dir):
    """邮件文本输入应正常处理并返回合法 intent_label"""
    task_input = {
        "task_id": "test-004",
        "source": "email",
        "subject": "您的账户存在风险",
        "body_text": (
            "尊敬的用户，您的银行账户存在异常，"
            "请立即点击链接验证：http://fake-bank.com/verify"
        ),
        "attachments": [],
    }
    result = agent.run(task_input, step_dir)
    assert result["intent_label"] in agent.valid_labels
    assert 0.0 <= result["confidence"] <= 1.0


# ---- 测试：step1.json 写入 ----

def test_step1_json_written(agent, scam_image_path, step_dir):
    """run() 执行后应在 step_dir 写入 step1.json"""
    task_input = {
        "task_id": "test-005",
        "file_type": "image",
        "file_path": scam_image_path,
        "source": "wechat",
        "file_name": "scam_test.png",
    }
    agent.run(task_input, step_dir)
    step_file = step_dir / "step1.json"
    assert step_file.exists(), "step1.json 应被写入"
    with open(step_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["step"] == 1
    assert data["agent"] == "preprocessor"
