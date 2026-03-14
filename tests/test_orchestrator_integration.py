"""
Orchestrator 集成测试套件 — 透明文件夹验证（TRANS-01 / TRANS-02）

目标：
- TRANS-01: 验证 conversations/YYYY-MM-DD/task-{id}-full.jsonl 正确写入（7行记录）
- TRANS-02: 验证 .pipeline/tasks/{taskId}/step1.json ~ step5.json 及 pipeline_summary.json 存在

测试策略：
- mock 5个 Agent 的 run() 方法，隔离外部 API/DB 依赖
- side_effect 写入 stepN.json，模拟真实 Agent 行为
- 专注验证文件写入行为和内容正确性
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# ==============================
# 预设 mock 返回值（完整诈骗场景）
# ==============================

MOCK_STEP1 = {
    "step": 1, "status": "success", "task_id": "test-task-001",
    "intent_label": "投资诈骗", "confidence": 0.92,
    "key_indicators": ["高收益", "快速致富"],
    "extracted_text_summary": "点击领取高额收益",
    "source": "wechat"
}
MOCK_STEP2 = {
    "step": 2, "status": "success",
    "relevant_cases": [{"case_id": "c001", "similarity_score": 0.85}],
    "avg_similarity": 0.85, "total_retrieved": 1,
    "low_similarity_warning": False
}
MOCK_STEP3 = {
    "step": 3, "status": "success",
    "verdict": "诈骗", "fraud_probability": 0.91,
    "fraud_type": "投资诈骗", "reasoning": "高度匹配诈骗特征",
    "evidence": ["高收益承诺"], "counter_evidence": [],
    "explanation": "典型投资诈骗话术"
}
MOCK_STEP4 = {
    "step": 4, "status": "success",
    "risk_level": "极高", "final_risk_score": 0.91,
    "base_score": 0.85, "total_adjustment": 0.06,
    "requires_guardian_alert": True
}
MOCK_STEP5 = {
    "step": 5, "status": "success",
    "risk_level": "极高", "verdict": "诈骗",
    "report_path": "reports/test.md",
    "notifications_sent": [{"channel": "auto", "sent": False}],
    "guardian_alerted": False, "awaiting_feedback": True
}


def make_agent_run(step_n: int, return_data: dict):
    """
    构造 Agent.run() 的 side_effect：
    从 args 末尾取 step_dir，写入 stepN.json，返回预设数据。
    """
    def side_effect(*args, **kwargs):
        # args[-1] 是 step_dir（Path 对象）
        step_dir = args[-1]
        (step_dir / f"step{step_n}.json").write_text(
            json.dumps(return_data, ensure_ascii=False), encoding="utf-8"
        )
        return return_data
    return side_effect


# ==============================
# Fixtures
# ==============================

@pytest.fixture
def setup_orchestrator(tmp_path):
    """
    创建 Orchestrator 所需目录结构及 input.json，返回关键路径。
    """
    pipeline_dir = tmp_path / ".pipeline" / "tasks"
    conversations_dir = tmp_path / "conversations"
    reports_dir = tmp_path / "reports"
    pipeline_dir.mkdir(parents=True)
    conversations_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    task_id = "test-task-001"
    task_dir = pipeline_dir / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "input.json").write_text(
        json.dumps({
            "task_id": task_id,
            "source": "wechat",
            "file_path": "test.jpg",
            "file_name": "test.jpg"
        }),
        encoding="utf-8"
    )
    return pipeline_dir, conversations_dir, reports_dir, task_id


@pytest.fixture
def orchestrator_with_mocks(setup_orchestrator):
    """
    创建带 mock Agent 的 Orchestrator 实例及 run 执行结果。
    返回 (orchestrator, result, pipeline_dir, conversations_dir, task_id)。
    """
    from pipeline.orchestrator import Orchestrator

    pipeline_dir, conversations_dir, reports_dir, task_id = setup_orchestrator

    with patch("pipeline.orchestrator.PreprocessorAgent") as MockA1, \
         patch("pipeline.orchestrator.RetrievalAgent") as MockA2, \
         patch("pipeline.orchestrator.DiscriminationAgent") as MockA3, \
         patch("pipeline.orchestrator.AssessmentAgent") as MockA4, \
         patch("pipeline.orchestrator.InterventionAgent") as MockA5:

        MockA1.return_value.run.side_effect = make_agent_run(1, MOCK_STEP1)
        MockA2.return_value.run.side_effect = make_agent_run(2, MOCK_STEP2)
        MockA3.return_value.run.side_effect = make_agent_run(3, MOCK_STEP3)
        MockA4.return_value.run.side_effect = make_agent_run(4, MOCK_STEP4)
        MockA5.return_value.run.side_effect = make_agent_run(5, MOCK_STEP5)

        orc = Orchestrator(
            pipeline_dir=str(pipeline_dir),
            conversations_dir=str(conversations_dir),
            reports_dir=str(reports_dir),
        )
        result = orc.run_pipeline(task_id)

    return orc, result, pipeline_dir, conversations_dir, task_id


# ==============================
# TestOrchestratorTransparency
# ==============================

class TestOrchestratorTransparency:
    """验证 Orchestrator 执行后透明文件夹正确写入（TRANS-01 + TRANS-02）"""

    def test_jsonl_full_chain_written(self, orchestrator_with_mocks):
        """
        TRANS-01: run_pipeline() 后，conversations/YYYY-MM-DD/task-{id}-full.jsonl 存在且含 7 行。
        """
        orc, result, pipeline_dir, conversations_dir, task_id = orchestrator_with_mocks

        today = datetime.now().strftime("%Y-%m-%d")
        jsonl_path = conversations_dir / today / f"task-{task_id}-full.jsonl"

        assert jsonl_path.exists(), f"JSONL 文件不存在: {jsonl_path}"

        lines = [line for line in jsonl_path.read_text(encoding="utf-8").strip().split("\n") if line]
        assert len(lines) == 7, f"期望 7 行，实际 {len(lines)} 行"

        expected_events = [
            "input", "step1_preprocessor", "step2_retrieval",
            "step3_discrimination", "step4_assessment",
            "step5_intervention", "pipeline_summary"
        ]
        actual_events = [json.loads(line)["event"] for line in lines]
        assert actual_events == expected_events, f"event 字段顺序不符: {actual_events}"

    def test_step_files_written(self, orchestrator_with_mocks):
        """
        TRANS-02: run_pipeline() 后，step1.json ~ step5.json 及 pipeline_summary.json 均存在。
        """
        orc, result, pipeline_dir, conversations_dir, task_id = orchestrator_with_mocks

        task_dir = pipeline_dir / task_id

        for i in range(1, 6):
            step_file = task_dir / f"step{i}.json"
            assert step_file.exists(), f"step{i}.json 不存在: {step_file}"

        summary_file = task_dir / "pipeline_summary.json"
        assert summary_file.exists(), f"pipeline_summary.json 不存在: {summary_file}"

        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        assert summary["final_status"] == "completed", (
            f"pipeline_summary.json final_status 期望 'completed'，实际 '{summary['final_status']}'"
        )

    def test_pipeline_summary_fields(self, orchestrator_with_mocks):
        """
        pipeline_summary.json 应包含 task_id、pipeline_started_at、pipeline_completed_at、
        steps、final_status、verdict、risk_level 字段。
        """
        orc, result, pipeline_dir, conversations_dir, task_id = orchestrator_with_mocks

        summary_file = pipeline_dir / task_id / "pipeline_summary.json"
        summary = json.loads(summary_file.read_text(encoding="utf-8"))

        required_fields = [
            "task_id", "pipeline_started_at", "pipeline_completed_at",
            "steps", "final_status", "verdict", "risk_level"
        ]
        for field in required_fields:
            assert field in summary, f"pipeline_summary.json 缺少字段: {field}"

    def test_jsonl_record_content(self, orchestrator_with_mocks):
        """
        JSONL 中 pipeline_summary event 的 data.verdict == '诈骗' 且 data.risk_level == '极高'。
        """
        orc, result, pipeline_dir, conversations_dir, task_id = orchestrator_with_mocks

        today = datetime.now().strftime("%Y-%m-%d")
        jsonl_path = conversations_dir / today / f"task-{task_id}-full.jsonl"

        lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
        summary_record = json.loads(lines[-1])

        assert summary_record["event"] == "pipeline_summary"
        assert summary_record["data"]["verdict"] == "诈骗", (
            f"verdict 期望 '诈骗'，实际 '{summary_record['data'].get('verdict')}'"
        )
        assert summary_record["data"]["risk_level"] == "极高", (
            f"risk_level 期望 '极高'，实际 '{summary_record['data'].get('risk_level')}'"
        )

    def test_multiple_runs_create_separate_task_dirs(self, tmp_path):
        """
        用两个不同 task_id 运行，各自有独立 step 目录且互不干扰。
        """
        from pipeline.orchestrator import Orchestrator

        pipeline_dir = tmp_path / ".pipeline" / "tasks"
        conversations_dir = tmp_path / "conversations"
        reports_dir = tmp_path / "reports"
        pipeline_dir.mkdir(parents=True)
        conversations_dir.mkdir(parents=True)
        reports_dir.mkdir(parents=True)

        task_ids = ["task-aaa-001", "task-bbb-002"]

        for task_id in task_ids:
            task_dir = pipeline_dir / task_id
            task_dir.mkdir(parents=True)
            (task_dir / "input.json").write_text(
                json.dumps({
                    "task_id": task_id,
                    "source": "email",
                    "file_path": "sample.txt",
                    "file_name": "sample.txt"
                }),
                encoding="utf-8"
            )

        with patch("pipeline.orchestrator.PreprocessorAgent") as MockA1, \
             patch("pipeline.orchestrator.RetrievalAgent") as MockA2, \
             patch("pipeline.orchestrator.DiscriminationAgent") as MockA3, \
             patch("pipeline.orchestrator.AssessmentAgent") as MockA4, \
             patch("pipeline.orchestrator.InterventionAgent") as MockA5:

            MockA1.return_value.run.side_effect = make_agent_run(1, MOCK_STEP1)
            MockA2.return_value.run.side_effect = make_agent_run(2, MOCK_STEP2)
            MockA3.return_value.run.side_effect = make_agent_run(3, MOCK_STEP3)
            MockA4.return_value.run.side_effect = make_agent_run(4, MOCK_STEP4)
            MockA5.return_value.run.side_effect = make_agent_run(5, MOCK_STEP5)

            orc = Orchestrator(
                pipeline_dir=str(pipeline_dir),
                conversations_dir=str(conversations_dir),
                reports_dir=str(reports_dir),
            )

            for task_id in task_ids:
                orc.run_pipeline(task_id)

        # 验证各自独立的 step 目录
        for task_id in task_ids:
            task_dir = pipeline_dir / task_id
            for i in range(1, 6):
                step_file = task_dir / f"step{i}.json"
                assert step_file.exists(), (
                    f"task '{task_id}' 的 step{i}.json 不存在: {step_file}"
                )
            summary_file = task_dir / "pipeline_summary.json"
            assert summary_file.exists(), (
                f"task '{task_id}' 的 pipeline_summary.json 不存在"
            )


# ==============================
# TestWorkflowTransparency（扩展：Orchestrator run() 接口健壮性）
# ==============================

class TestWorkflowTransparency:
    """验证 Orchestrator run_pipeline 返回值的结构完整性"""

    def test_run_pipeline_returns_dict(self, orchestrator_with_mocks):
        """run_pipeline() 应返回字典"""
        orc, result, *_ = orchestrator_with_mocks
        assert isinstance(result, dict), "run_pipeline() 应返回字典"

    def test_run_pipeline_result_has_task_id(self, orchestrator_with_mocks):
        """返回字典应包含 task_id 字段"""
        orc, result, *_ = orchestrator_with_mocks
        assert "task_id" in result

    def test_run_pipeline_result_final_status_completed(self, orchestrator_with_mocks):
        """成功执行后 final_status 应为 'completed'"""
        orc, result, *_ = orchestrator_with_mocks
        assert result.get("final_status") == "completed"

    def test_run_pipeline_result_has_verdict_and_risk(self, orchestrator_with_mocks):
        """返回字典应包含 verdict 和 risk_level 字段"""
        orc, result, *_ = orchestrator_with_mocks
        assert "verdict" in result
        assert "risk_level" in result
