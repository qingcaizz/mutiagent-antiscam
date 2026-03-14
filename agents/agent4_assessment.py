"""
Agent 4: 风险评估
- 加载 risk-rules.json 手写规则
- 结合用户画像 + 历史误判记忆
- 输出：风险等级（低/中/高/极高）
"""
import json
from pathlib import Path
from datetime import datetime
from loguru import logger


class AssessmentAgent:
    """Agent 4: 规则引擎风险评估"""

    RISK_LEVELS = {
        "extreme_high": "极高",
        "high": "高",
        "medium": "中",
        "low": "低",
        "safe": "安全"
    }

    def __init__(
        self,
        rules_path: str = "config/risk-rules.json",
        memory_path: str = "memory/capabilities.md"
    ):
        self.rules_path = Path(rules_path)
        self.memory_path = Path(memory_path)
        self.rules = self._load_rules()
        self.thresholds = self.rules.get("thresholds", {
            "extreme_high": 0.90,
            "high": 0.75,
            "medium": 0.55,
            "low": 0.30
        })
        self.memory_rules = self._load_memory_rules()

    def _load_memory_rules(self) -> list:
        """从 capabilities.md 加载历史学习规则，提取关键词列表"""
        if not self.memory_path.exists():
            logger.debug(f"[Agent4] capabilities 文件不存在，跳过历史规则加载: {self.memory_path}")
            return []
        rules = []
        try:
            content = self.memory_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                # 匹配格式：- **规则N**: 规则文本
                if stripped.startswith("- **规则") and "**:" in stripped:
                    colon_idx = stripped.index("**:")
                    rule_text = stripped[colon_idx + 3:].strip()
                    if rule_text:
                        tokens = [t for t in rule_text.split() if len(t) >= 2]
                        if tokens:
                            rules.append({"keywords": tokens, "weight": 0.5})
            logger.info(f"[Agent4] 从 capabilities.md 加载 {len(rules)} 条历史规则")
        except Exception as e:
            logger.warning(f"[Agent4] 读取 capabilities.md 失败: {e}")
        return rules

    def _load_rules(self) -> dict:
        """加载风险规则"""
        if self.rules_path.exists():
            with open(self.rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        logger.warning(f"[Agent4] 规则文件不存在: {self.rules_path}")
        return {"rules": [], "thresholds": {}}

    def run(
        self,
        step1_result: dict,
        step2_result: dict,
        step3_result: dict,
        step_dir: Path
    ) -> dict:
        """执行风险评估"""
        logger.info(f"[Agent4] 开始评估: {step1_result['task_id']}")
        result = {
            "step": 4,
            "agent": "assessment",
            "task_id": step1_result["task_id"],
            "started_at": datetime.now().isoformat(),
            "status": "processing"
        }

        try:
            # 1. 基础分数来自 Agent3 的诈骗概率
            base_score = step3_result.get("fraud_probability", 0.5)

            # 2. 规则引擎调整
            rule_adjustments = []
            extracted_text = step1_result.get("extracted_text", "").lower()
            intent = step1_result.get("intent_label", "")

            for rule in self.rules.get("rules", []):
                keywords = rule.get("keywords", [])
                is_whitelist = rule.get("is_whitelist", False)
                weight = rule.get("weight", 0)

                # 检查关键词匹配
                matched_keywords = [kw for kw in keywords if kw in extracted_text]
                if matched_keywords:
                    adjustment = weight * (len(matched_keywords) / len(keywords)) * 0.1
                    if is_whitelist:
                        adjustment = abs(adjustment) * -1  # 白名单降低分数
                    rule_adjustments.append({
                        "rule_id": rule.get("id"),
                        "rule_name": rule.get("name"),
                        "matched_keywords": matched_keywords,
                        "adjustment": adjustment
                    })

            # 2b. 历史学习规则调整（来自 capabilities.md）
            # 将 extracted_text 按空格拆分，用于检查输入词是否出现在规则描述中
            extracted_tokens = [t for t in extracted_text.split() if len(t) >= 2]
            for mem_rule in self.memory_rules:
                mem_keywords = mem_rule.get("keywords", [])
                mem_weight = mem_rule.get("weight", 0.5)
                # 双向子串匹配（大小写不敏感）：规则关键词在输入中，或输入词在规则描述中
                matched = [
                    kw for kw in mem_keywords
                    if kw.lower() in extracted_text
                    or any(et in kw.lower() for et in extracted_tokens)
                ]
                if matched:
                    adjustment = mem_weight * (len(matched) / max(len(mem_keywords), 1)) * 0.1
                    rule_adjustments.append({
                        "rule_id": "memory_rule",
                        "rule_name": "历史学习规则",
                        "matched_keywords": matched,
                        "adjustment": adjustment
                    })

            # 3. 检查特殊条件（来自误判记忆）
            special_conditions_applied = []
            for condition in self.rules.get("special_conditions", []):
                if (step2_result.get("avg_similarity", 1.0) < 0.65
                        and any(kw in extracted_text for kw in ["保险", "理财", "基金"])):
                    special_conditions_applied.append(condition.get("condition"))
                    # 应用条件：降低分数（额外校验）
                    base_score *= 0.9

            # 4. 计算最终分数
            total_adjustment = sum(adj["adjustment"] for adj in rule_adjustments)
            final_score = min(1.0, max(0.0, base_score + total_adjustment))

            # 5. 确定风险等级
            risk_level_key = "safe"
            if final_score >= self.thresholds.get("extreme_high", 0.90):
                risk_level_key = "extreme_high"
            elif final_score >= self.thresholds.get("high", 0.75):
                risk_level_key = "high"
            elif final_score >= self.thresholds.get("medium", 0.55):
                risk_level_key = "medium"
            elif final_score >= self.thresholds.get("low", 0.30):
                risk_level_key = "low"

            risk_level = self.RISK_LEVELS[risk_level_key]

            result.update({
                "status": "success",
                "base_score": base_score,
                "rule_adjustments": rule_adjustments,
                "special_conditions_applied": special_conditions_applied,
                "total_adjustment": total_adjustment,
                "final_risk_score": final_score,
                "risk_level_key": risk_level_key,
                "risk_level": risk_level,
                "verdict": step3_result.get("verdict", "未知"),
                "fraud_type": step3_result.get("fraud_type"),
                "requires_guardian_alert": risk_level_key == "extreme_high",
                "completed_at": datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"[Agent4] 评估失败: {e}")
            result.update({
                "status": "failed",
                "error": str(e),
                "risk_level": "未知",
                "final_risk_score": 0.5,
                "completed_at": datetime.now().isoformat()
            })

        step_file = step_dir / "step4.json"
        with open(step_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[Agent4] 完成: 风险{result.get('risk_level')} "
            f"(分数:{result.get('final_risk_score', 0):.2f})"
        )
        return result
