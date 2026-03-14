"""
ReflectorAgent TDD 测试套件
覆盖：
  - REFLECT-01: _load_execution_chain 链路读取
  - REFLECT-02: _write_reflection_report 报告写入
  - REFLECT-03: _update_capabilities 规则追加
  - 端到端: reflect() 主入口（mock Claude）
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memory.reflector import ReflectorAgent


# ---------------------------------------------------------------------------
# Task 1: _load_execution_chain
# ---------------------------------------------------------------------------

def test_load_execution_chain(tmp_path):
    """REFLECT-01: 读取 step1~step5.json，构建链路字典；缺失步骤返回 {} 而非异常。"""
    # 准备目录和文件
    task_dir = tmp_path / ".pipeline" / "tasks" / "test-001"
    task_dir.mkdir(parents=True)

    step_data = {
        "step1": {"intent_label": "fraud", "confidence": 0.9},
        "step2": {"relevant_cases": ["case-A"]},
        "step3": {"verdict": "FRAUD", "fraud_probability": 0.92},
        "step4": {"risk_level": "HIGH", "final_risk_score": 0.88},
        "step5": {"action": "alert_sent"},
    }
    for step_name, data in step_data.items():
        (task_dir / f"{step_name}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    agent = ReflectorAgent(
        pipeline_dir=str(tmp_path / ".pipeline" / "tasks"),
        reflections_dir=str(tmp_path / "reflections"),
        capabilities_file=str(tmp_path / "capabilities.md"),
    )

    chain = agent._load_execution_chain("test-001")

    # 基本结构
    assert isinstance(chain, dict)
    assert "steps" in chain

    # 全部 step1~step5 均加载
    for i in range(1, 6):
        assert f"step{i}" in chain["steps"], f"step{i} 应存在于 chain['steps']"

    # 值正确
    assert chain["steps"]["step1"]["intent_label"] == "fraud"
    assert chain["steps"]["step3"]["verdict"] == "FRAUD"

    # 缺失步骤返回 {} 而非异常
    (task_dir / "step3.json").unlink()
    chain2 = agent._load_execution_chain("test-001")
    assert chain2["steps"]["step3"] == {}, "缺失文件应返回空 dict"


# ---------------------------------------------------------------------------
# Task 2: _write_reflection_report
# ---------------------------------------------------------------------------

def test_write_reflection_report(tmp_path):
    """REFLECT-02: 写入 reflections/YYYY-MM-DD-case-{id}.md，内容含 root_cause 和 new_rules。"""
    reflections_dir = tmp_path / "reflections"
    reflections_dir.mkdir(parents=True)

    agent = ReflectorAgent(
        pipeline_dir=str(tmp_path / ".pipeline" / "tasks"),
        reflections_dir=str(reflections_dir),
        capabilities_file=str(tmp_path / "capabilities.md"),
    )

    reflection_data = {
        "root_cause": "测试根因",
        "analysis": "详细分析内容",
        "missed_features": ["特征A"],
        "new_rules": [{"rule": "规则1", "rationale": "依据1"}],
        "prevention": "预防措施",
    }

    # 提供空执行链路（_write_reflection_report 需要）
    execution_chain = {
        "task_id": "test-002",
        "steps": {f"step{i}": {} for i in range(1, 6)},
    }

    result_path = agent._write_reflection_report(
        "test-002", "用户反馈", execution_chain, reflection_data
    )

    # 路径格式匹配 YYYY-MM-DD-case-test-002.md
    assert result_path.name.endswith("-case-test-002.md"), f"文件名格式错误: {result_path.name}"
    import re
    assert re.match(r"\d{4}-\d{2}-\d{2}-case-test-002\.md", result_path.name), \
        f"日期前缀格式不正确: {result_path.name}"

    # 文件确实写入
    assert result_path.exists(), "报告文件应存在"

    content = result_path.read_text(encoding="utf-8")
    assert "测试根因" in content, "内容应包含 root_cause 文本"
    assert "规则1" in content, "内容应包含 new_rules 文本"


# ---------------------------------------------------------------------------
# Task 3: _update_capabilities
# ---------------------------------------------------------------------------

def test_update_capabilities(tmp_path):
    """REFLECT-03: 追加新规则到 capabilities.md，返回规则数，不覆盖原有内容。"""
    capabilities_file = tmp_path / "capabilities.md"
    capabilities_file.write_text("# Capabilities\n初始内容\n", encoding="utf-8")

    agent = ReflectorAgent(
        pipeline_dir=str(tmp_path / ".pipeline" / "tasks"),
        reflections_dir=str(tmp_path / "reflections"),
        capabilities_file=str(capabilities_file),
    )

    reflection_data = {
        "root_cause": "测试根因",
        "new_rules": [
            {"rule": "规则A", "rationale": "依据A"},
            {"rule": "规则B", "rationale": "依据B"},
        ],
    }

    count = agent._update_capabilities("test-003", reflection_data)

    # 返回整数等于规则数
    assert count == 2, f"应返回 2，实际返回 {count}"

    content = capabilities_file.read_text(encoding="utf-8")
    assert "规则A" in content, "capabilities.md 应包含 规则A"
    assert "规则B" in content, "capabilities.md 应包含 规则B"
    assert "初始内容" in content, "原有内容不应被覆盖"


# ---------------------------------------------------------------------------
# Task 4: reflect() 主入口端到端（mock Claude）
# ---------------------------------------------------------------------------

def test_reflect_end_to_end(tmp_path):
    """端到端: reflect() 在 mock Claude 后返回 status=success，包含 reflection_file 和 rules_added。"""
    # 搭建完整目录结构
    task_dir = tmp_path / ".pipeline" / "tasks" / "test-004"
    task_dir.mkdir(parents=True)
    reflections_dir = tmp_path / "reflections"
    reflections_dir.mkdir(parents=True)
    capabilities_file = tmp_path / "capabilities.md"
    capabilities_file.write_text("# Capabilities\n", encoding="utf-8")

    # step1~step5.json
    step_contents = {
        "step1": {"intent_label": "normal", "confidence": 0.6, "extracted_text": "示例文本"},
        "step2": {"relevant_cases": []},
        "step3": {"verdict": "NORMAL", "fraud_probability": 0.1, "explanation": "看起来正常"},
        "step4": {"risk_level": "LOW", "final_risk_score": 0.1},
        "step5": {"action": "no_action"},
    }
    for name, data in step_contents.items():
        (task_dir / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    # mock Claude 返回合法 JSON
    mock_response_text = json.dumps({
        "root_cause": "测试根因",
        "analysis": "分析内容",
        "missed_features": [],
        "new_rules": [{"rule": "mock规则", "rationale": "mock依据"}],
        "prevention": "预防措施",
    }, ensure_ascii=False)

    mock_content = MagicMock()
    mock_content.text = mock_response_text

    mock_message = MagicMock()
    mock_message.content = [mock_content]

    mock_messages = MagicMock()
    mock_messages.create.return_value = mock_message

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    mock_anthropic_cls = MagicMock(return_value=mock_client)

    with patch("memory.reflector.anthropic.Anthropic", mock_anthropic_cls):
        agent = ReflectorAgent(
            pipeline_dir=str(tmp_path / ".pipeline" / "tasks"),
            reflections_dir=str(reflections_dir),
            capabilities_file=str(capabilities_file),
        )
        result = agent.reflect("test-004", "测试反馈")

    assert result["status"] == "success", f"应为 success，实际: {result}"
    assert "reflection_file" in result, "应包含 reflection_file 字段"
    assert os.path.exists(result["reflection_file"]), "reflection_file 应为真实存在的文件"
    assert result["rules_added"] >= 0, "rules_added 应 >= 0"
