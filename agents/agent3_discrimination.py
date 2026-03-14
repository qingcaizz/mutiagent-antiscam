"""
Agent 3: 诈骗判别
- 调用 Qwen3.5 结合案例上下文增强判别（替代 Claude SDK）
- 输出：诈骗概率 + 可解释依据
"""
import json
import os
import re
from pathlib import Path
from datetime import datetime

from openai import OpenAI
from loguru import logger


# 南审 Qwen API 基础地址
NAU_BASE_URL = "https://ai-api.nau.edu.cn/v1"


class DiscriminationAgent:
    """Agent 3: 诈骗判别（Qwen3.5）"""

    SYSTEM_PROMPT = """你是一位经验丰富的反诈骗专家，负责基于已有案例和特征分析，
对当前信息作出最终判别。

请严格按照以下 JSON 格式输出（不要输出 markdown 代码块，只输出纯 JSON）：
{
    "fraud_probability": 0.87,
    "verdict": "诈骗",
    "fraud_type": "具体诈骗类型或null",
    "evidence": ["证据1", "证据2", "证据3"],
    "counter_evidence": ["反证1"],
    "explanation": "详细判断说明（200字内）",
    "case_reference_ids": ["参考案例ID列表"]
}

verdict 只能是以下三个值之一：诈骗 / 可疑 / 正常
"""

    def __init__(self, model: str = "qwen3.5-35b-a3b-fp8"):
        self.model = model
        self.client = OpenAI(
            api_key=os.getenv("NAU_API_KEY", ""),
            base_url=os.getenv("NAU_BASE_URL", NAU_BASE_URL),
        )

    def run(self, step1_result: dict, step2_result: dict, step_dir: Path) -> dict:
        """执行诈骗判别"""
        logger.info(f"[Agent3] 开始判别: {step1_result['task_id']}")
        result = {
            "step": 3,
            "agent": "discrimination",
            "task_id": step1_result["task_id"],
            "started_at": datetime.now().isoformat(),
            "status": "processing"
        }

        try:
            prompt = self._build_prompt(step1_result, step2_result)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1024,
            )

            response_text = response.choices[0].message.content.strip()

            # 兼容模型输出 markdown 代码块
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            # 兼容 <think>...</think> 标签（Qwen 推理模型带推理过程）
            response_text = re.sub(
                r"<think>.*?</think>", "", response_text, flags=re.DOTALL
            ).strip()

            verdict_result = json.loads(response_text)

            result.update({
                "status": "success",
                "fraud_probability": float(verdict_result.get("fraud_probability", 0.0)),
                "verdict": verdict_result.get("verdict", "未知"),
                "fraud_type": verdict_result.get("fraud_type"),
                "evidence": verdict_result.get("evidence", []),
                "counter_evidence": verdict_result.get("counter_evidence", []),
                "explanation": verdict_result.get("explanation", ""),
                "case_reference_ids": verdict_result.get("case_reference_ids", []),
                "completed_at": datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"[Agent3] 判别失败: {e}")
            result.update({
                "status": "failed",
                "error": str(e),
                "fraud_probability": 0.5,
                "verdict": "未知",
                "completed_at": datetime.now().isoformat()
            })

        step_file = step_dir / "step3.json"
        with open(step_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[Agent3] 完成: {result.get('verdict')} "
            f"(概率:{result.get('fraud_probability', 0):.2f})"
        )
        return result

    def _build_prompt(self, step1: dict, step2: dict) -> str:
        """构造判别 Prompt"""
        cases_text = ""
        for i, case in enumerate(step2.get("relevant_cases", [])[:3], 1):
            score = case.get("similarity_score", case.get("similarity", 0))
            cases_text += f"\n案例{i}（相似度:{score:.2f}）:"
            cases_text += f"\n  描述: {case.get('description', '')}"
            cases_text += f"\n  结论: {case.get('verdict', '')}"

        return f"""请对以下信息进行诈骗判别：

【意图识别结果】
- 意图标签: {step1.get('intent_label', 'unknown')}
- 置信度: {step1.get('confidence', 0):.2f}
- 关键特征: {', '.join(step1.get('key_indicators', []))}
- 内容摘要: {step1.get('extracted_text_summary', '')}
- 判断理由: {step1.get('reasoning', '')}

【RAG检索结果】
- 平均相似度: {step2.get('avg_similarity', 0):.2f}
- 低相似度警告: {'是' if step2.get('low_similarity_warning') else '否'}
- 参考案例:
{cases_text if cases_text else '  无相关案例'}

【原始内容（前500字）】
{step1.get('extracted_text', '')[:500]}

请综合以上信息，给出最终判别结论（纯 JSON 格式）。"""
