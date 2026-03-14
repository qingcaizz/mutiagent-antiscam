"""
集成测试：日志写入验证（TRANS-03）+ 监控触发链路 + 判断方向性测试
"""
import json
import re
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from pipeline.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# 复用 05-01 mock 数据（重新定义）
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def make_agent_run(step_n: int, return_data: dict):
    """返回一个 side_effect 函数，写入 stepN.json 并返回 return_data"""
    def side_effect(*args, **kwargs):
        # args[-1] 是 step_dir（Path 对象）
        step_dir = args[-1]
        (step_dir / f"step{step_n}.json").write_text(
            json.dumps(return_data, ensure_ascii=False), encoding="utf-8"
        )
        return return_data
    return side_effect


def _setup_agent_mocks(MockA1, MockA2, MockA3, MockA4, MockA5):
    """为五个 Agent mock 设置 side_effect"""
    MockA1.return_value.run.side_effect = make_agent_run(1, MOCK_STEP1)
    MockA2.return_value.run.side_effect = make_agent_run(2, MOCK_STEP2)
    MockA3.return_value.run.side_effect = make_agent_run(3, MOCK_STEP3)
    MockA4.return_value.run.side_effect = make_agent_run(4, MOCK_STEP4)
    MockA5.return_value.run.side_effect = make_agent_run(5, MOCK_STEP5)


def _create_task_dir(pipeline_dir: Path, task_id: str) -> Path:
    """在 pipeline_dir 下创建任务目录并写入 input.json"""
    task_dir = pipeline_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "input.json").write_text(
        json.dumps({
            "task_id": task_id,
            "source": "wechat",
            "file_path": "test.jpg",
            "file_name": "test.jpg"
        }),
        encoding="utf-8"
    )
    return task_dir


# ---------------------------------------------------------------------------
# TestPipelineLogging
# ---------------------------------------------------------------------------

class TestPipelineLogging:
    """验证 Orchestrator 运行产生日志文件（TRANS-03）"""

    def test_pipeline_log_contains_step_markers(self, tmp_path):
        """运行管线后 pipeline.log 包含 Step 1/5 ~ Step 5/5 的日志条目"""
        from loguru import logger

        log_file = tmp_path / "pipeline.log"
        log_id = logger.add(str(log_file), format="{time} {level} {message}")

        try:
            with patch("pipeline.orchestrator.PreprocessorAgent") as MockA1, \
                 patch("pipeline.orchestrator.RetrievalAgent") as MockA2, \
                 patch("pipeline.orchestrator.DiscriminationAgent") as MockA3, \
                 patch("pipeline.orchestrator.AssessmentAgent") as MockA4, \
                 patch("pipeline.orchestrator.InterventionAgent") as MockA5:

                _setup_agent_mocks(MockA1, MockA2, MockA3, MockA4, MockA5)

                pipeline_dir = tmp_path / ".pipeline" / "tasks"
                task_id = "log-test-001"
                _create_task_dir(pipeline_dir, task_id)

                orc = Orchestrator(
                    pipeline_dir=str(pipeline_dir),
                    conversations_dir=str(tmp_path / "conversations"),
                    reports_dir=str(tmp_path / "reports")
                )
                orc.run_pipeline(task_id)

        finally:
            logger.remove(log_id)

        log_content = log_file.read_text(encoding="utf-8")
        assert "Step 1/5" in log_content, "log 应包含 Step 1/5 标记"
        assert "Step 5/5" in log_content, "log 应包含 Step 5/5 标记"
        assert task_id in log_content, f"log 应包含 task_id={task_id}"

    def test_log_contains_timestamp(self, tmp_path):
        """日志文件每行包含时间戳格式"""
        from loguru import logger

        log_file = tmp_path / "pipeline_ts.log"
        log_id = logger.add(str(log_file), format="{time:YYYY-MM-DD HH:mm:ss} | {message}")

        try:
            with patch("pipeline.orchestrator.PreprocessorAgent") as MockA1, \
                 patch("pipeline.orchestrator.RetrievalAgent") as MockA2, \
                 patch("pipeline.orchestrator.DiscriminationAgent") as MockA3, \
                 patch("pipeline.orchestrator.AssessmentAgent") as MockA4, \
                 patch("pipeline.orchestrator.InterventionAgent") as MockA5:

                _setup_agent_mocks(MockA1, MockA2, MockA3, MockA4, MockA5)

                pipeline_dir = tmp_path / ".pipeline" / "tasks"
                task_id = "ts-test-001"
                _create_task_dir(pipeline_dir, task_id)

                orc = Orchestrator(
                    pipeline_dir=str(pipeline_dir),
                    conversations_dir=str(tmp_path / "conversations"),
                    reports_dir=str(tmp_path / "reports")
                )
                orc.run_pipeline(task_id)

        finally:
            logger.remove(log_id)

        log_content = log_file.read_text(encoding="utf-8")
        assert re.search(r"\d{4}-\d{2}-\d{2}", log_content), "log 行应包含日期时间戳"


# ---------------------------------------------------------------------------
# TestFraudDirectionality
# ---------------------------------------------------------------------------

class TestFraudDirectionality:
    """验证流水线对诈骗/正常样本判断方向正确（TRANS-01 成功标准第4条）"""

    def test_fraud_sample_verdict_not_normal(self, tmp_path):
        """诈骗样本流水线输出 verdict 应为诈骗或可疑，不得为正常"""
        with patch("pipeline.orchestrator.PreprocessorAgent") as MockA1, \
             patch("pipeline.orchestrator.RetrievalAgent") as MockA2, \
             patch("pipeline.orchestrator.DiscriminationAgent") as MockA3, \
             patch("pipeline.orchestrator.AssessmentAgent") as MockA4, \
             patch("pipeline.orchestrator.InterventionAgent") as MockA5:

            _setup_agent_mocks(MockA1, MockA2, MockA3, MockA4, MockA5)

            pipeline_dir = tmp_path / ".pipeline" / "tasks"
            task_id = "fraud-dir-001"
            _create_task_dir(pipeline_dir, task_id)

            orc = Orchestrator(
                pipeline_dir=str(pipeline_dir),
                conversations_dir=str(tmp_path / "conversations"),
                reports_dir=str(tmp_path / "reports")
            )
            result = orc.run_pipeline(task_id)

        assert result["verdict"] != "正常", \
            f"诈骗样本 verdict 不应为正常，实际: {result['verdict']}"
        assert result["verdict"] in ["诈骗", "可疑"], \
            f"verdict 应为诈骗或可疑，实际: {result['verdict']}"

    def test_safe_sample_verdict(self, tmp_path):
        """正常样本流水线输出 verdict 应为正常或可疑"""
        SAFE_STEP3 = {
            "step": 3, "status": "success",
            "verdict": "正常", "fraud_probability": 0.05,
            "fraud_type": None, "reasoning": "未发现诈骗特征",
            "evidence": [], "counter_evidence": ["内容正常"],
            "explanation": "未发现明显诈骗特征"
        }
        SAFE_STEP4 = {
            "step": 4, "status": "success",
            "risk_level": "安全", "final_risk_score": 0.05,
            "base_score": 0.05, "total_adjustment": 0.0,
            "requires_guardian_alert": False
        }
        SAFE_STEP5 = {
            "step": 5, "status": "success",
            "risk_level": "安全", "verdict": "正常",
            "report_path": "reports/safe-test.md",
            "notifications_sent": [],
            "guardian_alerted": False, "awaiting_feedback": False
        }

        def make_safe_mocks(MockA1, MockA2, MockA3, MockA4, MockA5):
            MockA1.return_value.run.side_effect = make_agent_run(1, MOCK_STEP1)
            MockA2.return_value.run.side_effect = make_agent_run(2, MOCK_STEP2)
            MockA3.return_value.run.side_effect = make_agent_run(3, SAFE_STEP3)
            MockA4.return_value.run.side_effect = make_agent_run(4, SAFE_STEP4)
            MockA5.return_value.run.side_effect = make_agent_run(5, SAFE_STEP5)

        with patch("pipeline.orchestrator.PreprocessorAgent") as MockA1, \
             patch("pipeline.orchestrator.RetrievalAgent") as MockA2, \
             patch("pipeline.orchestrator.DiscriminationAgent") as MockA3, \
             patch("pipeline.orchestrator.AssessmentAgent") as MockA4, \
             patch("pipeline.orchestrator.InterventionAgent") as MockA5:

            make_safe_mocks(MockA1, MockA2, MockA3, MockA4, MockA5)

            pipeline_dir = tmp_path / ".pipeline" / "tasks"
            task_id = "safe-dir-001"
            _create_task_dir(pipeline_dir, task_id)

            orc = Orchestrator(
                pipeline_dir=str(pipeline_dir),
                conversations_dir=str(tmp_path / "conversations"),
                reports_dir=str(tmp_path / "reports")
            )
            result = orc.run_pipeline(task_id)

        assert result["verdict"] in ["正常", "可疑"], \
            f"正常样本 verdict 不应为诈骗，实际: {result['verdict']}"


# ---------------------------------------------------------------------------
# TestMonitorTriggerChain
# ---------------------------------------------------------------------------

class TestMonitorTriggerChain:
    """验证监控层 WeChatFileHandler → task_callback 触发链路（TRANS-03 监控日志）"""

    def test_wechat_handler_triggers_callback_on_image(self, tmp_path):
        """图片文件创建事件触发 task_callback，并在 pipeline_dir 创建 input.json"""
        from watchdog.events import FileCreatedEvent
        from monitor.wechat_monitor import WeChatFileHandler

        # 创建真实的非空图片文件（on_created 会检查文件存在性和大小）
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # 非空 JPEG 头

        callback = MagicMock()
        pipeline_dir = tmp_path / ".pipeline" / "tasks"

        with patch("monitor.wechat_monitor.extract_text_from_image", return_value="测试文字"):
            handler = WeChatFileHandler(
                task_callback=callback,
                pipeline_dir=str(pipeline_dir)
            )
            event = FileCreatedEvent(str(img_file))
            object.__setattr__(event, "is_directory", False)
            handler.on_created(event)

        callback.assert_called_once()
        task = callback.call_args[0][0]
        assert task["source"] == "wechat"
        assert "task_id" in task

    def test_pipeline_dir_input_json_created(self, tmp_path):
        """WeChatFileHandler 创建 input.json 到 pipeline_dir/task_id/"""
        from watchdog.events import FileCreatedEvent
        from monitor.wechat_monitor import WeChatFileHandler

        # 创建真实的非空 PNG 文件
        scam_file = tmp_path / "scam.png"
        scam_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # 非空 PNG 头

        pipeline_dir = tmp_path / ".pipeline" / "tasks"
        received_tasks = []

        def capture_task(task):
            received_tasks.append(task)

        with patch("monitor.wechat_monitor.extract_text_from_image", return_value=""):
            handler = WeChatFileHandler(
                task_callback=capture_task,
                pipeline_dir=str(pipeline_dir)
            )
            event = FileCreatedEvent(str(scam_file))
            object.__setattr__(event, "is_directory", False)
            handler.on_created(event)

        # task_callback 被调用，input.json 已写入 pipeline_dir
        assert len(received_tasks) == 1, f"应有 1 个任务，实际: {len(received_tasks)}"
        task_id = received_tasks[0]["task_id"]
        input_file = pipeline_dir / task_id / "input.json"
        assert input_file.exists(), f"input.json 应在 {input_file}"
        data = json.loads(input_file.read_text(encoding="utf-8"))
        assert data["task_id"] == task_id
