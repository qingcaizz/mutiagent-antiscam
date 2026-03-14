"""
Agent 2: RAG 案例检索
- LanceDB 向量相似度检索
- 输出：TOP-K 相似案例 + 语义相关度分数
"""
import json
from pathlib import Path
from datetime import datetime
from loguru import logger

from utils.lancedb_client import LanceDBClient


class RetrievalAgent:
    """Agent 2: RAG 案例检索"""

    def __init__(
        self,
        lancedb_path: str = "cases/lancedb",
        top_k: int = 5,
        similarity_threshold: float = 0.65
    ):
        self.db = LanceDBClient(lancedb_path)
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold

    def run(self, step1_result: dict, step_dir: Path) -> dict:
        """
        执行 RAG 案例检索

        Args:
            step1_result: Agent1 输出结果
            step_dir: 步骤输出目录

        Returns:
            step2 结果字典
        """
        logger.info(f"[Agent2] 开始检索: {step1_result['task_id']}")
        result = {
            "step": 2,
            "agent": "retrieval",
            "task_id": step1_result["task_id"],
            "started_at": datetime.now().isoformat(),
            "status": "processing"
        }

        try:
            # 构造检索查询
            query_text = self._build_query(step1_result)

            # 向量检索（使用 search_similar 方法）
            raw_cases = self.db.search_similar(query_text, self.top_k)

            # 将 LanceDB 返回的 _distance（L2，越小越相似）转换为 similarity_score（越大越相似）
            similar_cases = []
            for case in raw_cases:
                case["similarity_score"] = round(
                    max(0.0, 1.0 - case.get("_distance", 1.0)), 4
                )
                similar_cases.append(case)

            # 计算平均相似度
            avg_similarity = (
                sum(c["similarity_score"] for c in similar_cases) / len(similar_cases)
                if similar_cases else 0.0
            )

            # 过滤低相关度案例（基于 similarity_score 字段）
            relevant_cases = [
                case for case in similar_cases
                if case.get("similarity_score", 0) >= self.similarity_threshold
            ]

            # 低相似度警告：基于 avg_similarity 与阈值比较
            low_similarity = avg_similarity < self.similarity_threshold

            result.update({
                "status": "success",
                "query_text": query_text,
                "total_retrieved": len(similar_cases),
                "cases": similar_cases,
                "relevant_cases": relevant_cases,
                "avg_similarity": round(avg_similarity, 4),
                "low_similarity_warning": low_similarity,
                "intent_label": step1_result.get("intent_label", "unknown"),
                "completed_at": datetime.now().isoformat()
            })

            if low_similarity:
                logger.warning(
                    f"[Agent2] 低相关度警告: avg_similarity={avg_similarity:.2f}"
                )

        except Exception as e:
            logger.error(f"[Agent2] 检索失败: {e}")
            result.update({
                "status": "failed",
                "error": str(e),
                "relevant_cases": [],
                "avg_similarity": 0.0,
                "completed_at": datetime.now().isoformat()
            })

        # 保存步骤结果
        step_file = step_dir / "step2.json"
        with open(step_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[Agent2] 完成: 找到 {len(result.get('relevant_cases', []))} 个相关案例"
        )
        return result

    def _build_query(self, step1_result: dict) -> str:
        """从 step1 结果构造检索查询"""
        parts = []

        intent = step1_result.get("intent_label", "")
        if intent and intent != "unknown":
            parts.append(f"意图类型: {intent}")

        indicators = step1_result.get("key_indicators", [])
        if indicators:
            parts.append("关键特征: " + "、".join(indicators[:5]))

        summary = step1_result.get("extracted_text_summary", "")
        if summary:
            parts.append(f"内容摘要: {summary}")

        extracted = step1_result.get("extracted_text", "")
        if extracted:
            parts.append(extracted[:500])

        return "\n".join(parts) if parts else "诈骗信息分析"
