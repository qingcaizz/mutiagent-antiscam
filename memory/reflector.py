"""
自反思 Agent（ReflectorAgent）
- 在收到用户误判反馈后，读取完整执行链路分析根因
- 调用 Claude API 生成反思报告
- 写入 memory/reflections/ 并更新 memory/capabilities.md
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
from loguru import logger

# 路径常量
_PROJECT_ROOT = Path("D:/个人项目/mutiagent_trea")
_PIPELINE_DIR = _PROJECT_ROOT / ".pipeline" / "tasks"
_REFLECTIONS_DIR = _PROJECT_ROOT / "memory" / "reflections"
_CAPABILITIES_FILE = _PROJECT_ROOT / "memory" / "capabilities.md"

_MODEL = "claude-sonnet-4-6"

_REFLECTION_SYSTEM_PROMPT = """你是一个诈骗识别系统的自反思分析师。
你的职责是分析系统的误判案例，找出根本原因，并提出改进规则。

请严格按照以下 JSON 格式输出（不要添加任何其他内容）：
{
    "root_cause": "误判根本原因（简洁描述）",
    "analysis": "详细分析（200字以内）",
    "missed_features": ["遗漏的关键特征1", "遗漏的关键特征2"],
    "new_rules": [
        {
            "rule": "新规则描述",
            "rationale": "规则依据"
        }
    ],
    "prevention": "未来如何避免此类误判（100字以内）"
}"""


class ReflectorAgent:
    """
    自反思 Agent：分析误判根因，生成反思报告，更新能力记忆文件。
    """

    def __init__(
        self,
        pipeline_dir: Optional[str] = None,
        reflections_dir: Optional[str] = None,
        capabilities_file: Optional[str] = None,
        model: str = _MODEL,
    ) -> None:
        self.pipeline_dir = Path(pipeline_dir) if pipeline_dir else _PIPELINE_DIR
        self.reflections_dir = (
            Path(reflections_dir) if reflections_dir else _REFLECTIONS_DIR
        )
        self.capabilities_file = (
            Path(capabilities_file) if capabilities_file else _CAPABILITIES_FILE
        )
        self.model = model
        self.client = anthropic.Anthropic()

        self.reflections_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[Reflector] 自反思 Agent 初始化完成")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def reflect(self, task_id: str, feedback: str) -> dict:
        """
        主反思入口。

        Args:
            task_id: 被误判的任务 ID
            feedback: 用户反馈内容

        Returns:
            反思结果字典，含 status / reflection_file / rules_added 等字段
        """
        logger.info(f"[Reflector] 开始反思: task_id={task_id}")
        result = {
            "task_id": task_id,
            "feedback": feedback,
            "started_at": datetime.now().isoformat(),
            "status": "processing",
        }

        try:
            # 1. 读取完整执行链路
            execution_chain = self._load_execution_chain(task_id)

            # 2. 读取历史反思（避免重复犯错）
            historical_reflections = self._load_historical_reflections(limit=5)

            # 3. 调用 Claude 分析根因
            reflection_data = self._analyze_with_claude(
                task_id, feedback, execution_chain, historical_reflections
            )

            # 4. 写入反思报告
            reflection_file = self._write_reflection_report(
                task_id, feedback, execution_chain, reflection_data
            )

            # 5. 更新 capabilities.md
            rules_added = self._update_capabilities(task_id, reflection_data)

            result.update(
                {
                    "status": "success",
                    "root_cause": reflection_data.get("root_cause", ""),
                    "new_rules": reflection_data.get("new_rules", []),
                    "rules_added": rules_added,
                    "reflection_file": str(reflection_file),
                    "completed_at": datetime.now().isoformat(),
                }
            )
            logger.info(f"[Reflector] 反思完成: {task_id}，新增规则 {rules_added} 条")

        except Exception as exc:
            logger.error(f"[Reflector] 反思失败 ({task_id}): {exc}")
            result.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "completed_at": datetime.now().isoformat(),
                }
            )

        return result

    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------

    def _load_execution_chain(self, task_id: str) -> dict:
        """读取 step1~step5.json，构建完整执行链路字典。"""
        task_dir = self.pipeline_dir / task_id
        chain: dict = {"task_id": task_id, "steps": {}}

        for i in range(1, 6):
            step_file = task_dir / f"step{i}.json"
            if step_file.exists():
                with open(step_file, "r", encoding="utf-8") as f:
                    chain["steps"][f"step{i}"] = json.load(f)
            else:
                logger.warning(f"[Reflector] 步骤文件不存在: {step_file}")
                chain["steps"][f"step{i}"] = {}

        # 同时尝试读取 input.json
        input_file = task_dir / "input.json"
        if input_file.exists():
            with open(input_file, "r", encoding="utf-8") as f:
                chain["input"] = json.load(f)

        return chain

    def _load_historical_reflections(self, limit: int = 5) -> list[str]:
        """读取最近 N 个反思报告的摘要（避免重复犯同类错误）。"""
        reflection_files = sorted(
            self.reflections_dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        summaries: list[str] = []
        for rf in reflection_files:
            try:
                content = rf.read_text(encoding="utf-8")
                # 只取前 500 字作为摘要
                summaries.append(f"## 历史反思：{rf.name}\n{content[:500]}")
            except Exception as exc:
                logger.warning(f"[Reflector] 读取历史反思失败 ({rf}): {exc}")

        logger.debug(f"[Reflector] 读取历史反思 {len(summaries)} 份")
        return summaries

    def _analyze_with_claude(
        self,
        task_id: str,
        feedback: str,
        execution_chain: dict,
        historical_reflections: list[str],
    ) -> dict:
        """调用 Claude 分析误判根因，返回结构化反思数据。"""
        # 构建上下文（避免超长，截取关键信息）
        chain_summary = json.dumps(
            {
                "task_id": execution_chain.get("task_id"),
                "step1_intent": execution_chain["steps"].get("step1", {}).get("intent_label"),
                "step1_confidence": execution_chain["steps"].get("step1", {}).get("confidence"),
                "step2_cases_found": len(
                    execution_chain["steps"].get("step2", {}).get("relevant_cases", [])
                ),
                "step3_verdict": execution_chain["steps"].get("step3", {}).get("verdict"),
                "step3_fraud_probability": execution_chain["steps"].get("step3", {}).get(
                    "fraud_probability"
                ),
                "step4_risk_level": execution_chain["steps"].get("step4", {}).get("risk_level"),
                "step4_final_score": execution_chain["steps"].get("step4", {}).get(
                    "final_risk_score"
                ),
                "step3_explanation": execution_chain["steps"].get("step3", {}).get(
                    "explanation", ""
                )[:300],
                "step1_extracted_text": execution_chain["steps"].get("step1", {}).get(
                    "extracted_text", ""
                )[:500],
            },
            ensure_ascii=False,
            indent=2,
        )

        history_text = (
            "\n\n".join(historical_reflections)
            if historical_reflections
            else "暂无历史反思记录"
        )

        user_prompt = f"""任务ID: {task_id}
用户反馈: {feedback}

执行链路摘要:
{chain_summary}

历史反思记录（参考，避免重复犯错）:
{history_text[:2000]}

请分析此次误判的根本原因，并提出改进规则。"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=_REFLECTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = response.content[0].text.strip()
        # 清理可能的 markdown 代码块
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        reflection_data = json.loads(response_text)
        logger.info(f"[Reflector] Claude 分析完成: {reflection_data.get('root_cause', '')[:80]}")
        return reflection_data

    def _write_reflection_report(
        self,
        task_id: str,
        feedback: str,
        execution_chain: dict,
        reflection_data: dict,
    ) -> Path:
        """生成并写入 Markdown 反思报告。"""
        today = datetime.now().strftime("%Y-%m-%d")
        report_path = self.reflections_dir / f"{today}-case-{task_id}.md"

        new_rules_md = ""
        for i, rule in enumerate(reflection_data.get("new_rules", []), start=1):
            new_rules_md += (
                f"\n{i}. **{rule.get('rule', '')}**\n"
                f"   - 依据：{rule.get('rationale', '')}\n"
            )

        missed_features = reflection_data.get("missed_features", [])
        missed_md = "\n".join(f"- {f}" for f in missed_features) or "无"

        step3 = execution_chain["steps"].get("step3", {})
        step4 = execution_chain["steps"].get("step4", {})

        report_content = f"""# 误判反思报告

**任务ID**: {task_id}
**反思时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**用户反馈**: {feedback}

---

## 原始判断

| 字段 | 值 |
|------|----|
| 意图识别 | {execution_chain["steps"].get("step1", {}).get("intent_label", "N/A")} |
| 置信度 | {execution_chain["steps"].get("step1", {}).get("confidence", 0):.1%} |
| 判决结果 | {step3.get("verdict", "N/A")} |
| 诈骗概率 | {step3.get("fraud_probability", 0):.1%} |
| 风险等级 | {step4.get("risk_level", "N/A")} |
| 风险分数 | {step4.get("final_risk_score", 0):.2f} |

## 根本原因

{reflection_data.get("root_cause", "未知")}

## 详细分析

{reflection_data.get("analysis", "无")}

## 遗漏的关键特征

{missed_md}

## 改进规则

{new_rules_md or "无"}

## 预防措施

{reflection_data.get("prevention", "无")}

---

*此报告由系统自动生成，用于持续改进诈骗识别能力*
"""
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"[Reflector] 反思报告已写入: {report_path}")
        return report_path

    def _update_capabilities(self, task_id: str, reflection_data: dict) -> int:
        """
        将新规则追加写入 memory/capabilities.md。

        Returns:
            追加的规则数量。
        """
        new_rules = reflection_data.get("new_rules", [])
        if not new_rules:
            return 0

        # 确保文件存在
        self.capabilities_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.capabilities_file.exists():
            self.capabilities_file.write_text(
                "# 系统能力规则库\n\n本文件由反思 Agent 自动维护。\n",
                encoding="utf-8",
            )

        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        append_content = f"\n\n## 从误判中学习 [{timestamp}] (task: {task_id})\n"
        append_content += f"> 根因：{reflection_data.get('root_cause', '')}\n\n"

        for i, rule in enumerate(new_rules, start=1):
            append_content += (
                f"- **规则{i}**: {rule.get('rule', '')}\n"
                f"  - 依据：{rule.get('rationale', '')}\n"
            )

        with open(self.capabilities_file, "a", encoding="utf-8") as f:
            f.write(append_content)

        logger.info(
            f"[Reflector] capabilities.md 已更新，新增 {len(new_rules)} 条规则"
        )
        return len(new_rules)
