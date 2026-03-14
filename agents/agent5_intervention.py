"""
Agent 5: 干预交互
- 发送预警通知（邮件优先；飞书/钉钉可选，.env 配了就发）
- 极高风险 → 监护人联动（GUARDIAN_EMAIL / GUARDIAN_FEISHU 二选一或叠加）
- 生成分析报告 → reports/
- 等待用户反馈（是否误判）
"""
import json
import os
from pathlib import Path
from datetime import datetime
from loguru import logger

from utils.notifier import (
    EmailNotifier, FeishuNotifier, DingTalkNotifier,
    _infer_smtp_host, send_alert,
)


class InterventionAgent:
    """Agent 5: 干预 + 通知 + 报告"""

    RISK_EMOJI = {
        "极高": "🚨",
        "高": "⚠️",
        "中": "❓",
        "低": "ℹ️",
        "安全": "✅"
    }

    def __init__(
        self,
        reports_dir: str = "reports",
        conversations_dir: str = "conversations"
    ):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_dir = Path(conversations_dir)

        # 监护人邮件通知器（极高风险专用）
        smtp_host = (
            os.getenv("SMTP_HOST", "").strip()
            or _infer_smtp_host(os.getenv("EMAIL_HOST", "").strip())
        )
        self.guardian_email = EmailNotifier(
            smtp_host=smtp_host,
            smtp_port=int(os.getenv("SMTP_PORT", "465")),
            username=os.getenv("EMAIL_USER", ""),
            password=os.getenv("EMAIL_PASS", ""),
            to_addrs=os.getenv("GUARDIAN_EMAIL", ""),
        )
        # 可选：监护人飞书
        self.guardian_feishu_url = os.getenv("GUARDIAN_FEISHU", "")

    def run(
        self,
        step1_result: dict,
        step2_result: dict,
        step3_result: dict,
        step4_result: dict,
        step_dir: Path
    ) -> dict:
        """执行干预和通知"""
        task_id = step1_result["task_id"]
        logger.info(f"[Agent5] 开始干预: {task_id}")

        result = {
            "step": 5,
            "agent": "intervention",
            "task_id": task_id,
            "started_at": datetime.now().isoformat(),
            "status": "processing"
        }

        try:
            risk_level = step4_result.get("risk_level", "未知")
            risk_score = step4_result.get("final_risk_score", 0)
            verdict = step3_result.get("verdict", "未知")
            fraud_type = step3_result.get("fraud_type", "未知")
            source = step1_result.get("source", "unknown")

            # 1. 生成分析报告
            report_path = self._generate_report(
                task_id, step1_result, step2_result, step3_result, step4_result
            )

            # 2. 推送通知（中风险及以上，自动使用已配置的渠道）
            notifications_sent = []
            if risk_level in ["中", "高", "极高"]:
                subject = self._build_notification_subject(risk_level, verdict, fraud_type)
                msg = self._build_notification_message(
                    task_id, risk_level, risk_score, verdict, fraud_type, source, step3_result
                )
                sent = send_alert(subject, msg, risk_level)
                notifications_sent.append({"channel": "auto", "sent": sent})

            # 3. 极高风险 → 监护人联动
            guardian_alerted = False
            if step4_result.get("requires_guardian_alert"):
                guardian_alerted = self._alert_guardian(
                    task_id, risk_level, risk_score, step3_result
                )

            # 4. 保存会话记录
            self._save_conversation(
                task_id, step1_result, step2_result, step3_result, step4_result, result
            )

            result.update({
                "status": "success",
                "risk_level": risk_level,
                "verdict": verdict,
                "report_path": str(report_path),
                "notifications_sent": notifications_sent,
                "guardian_alerted": guardian_alerted,
                "awaiting_feedback": True,
                "feedback_instructions": (
                    "如判断有误，请在飞书/钉钉回复'误判'，"
                    "系统将自动触发反思流程"
                ),
                "completed_at": datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"[Agent5] 干预失败: {e}")
            result.update({
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now().isoformat()
            })

        step_file = step_dir / "step5.json"
        with open(step_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"[Agent5] 完成: 风险{result.get('risk_level')} 已推送通知")
        return result

    def _generate_report(
        self,
        task_id: str,
        step1: dict,
        step2: dict,
        step3: dict,
        step4: dict
    ) -> Path:
        """生成 Markdown 分析报告"""
        risk_emoji = self.RISK_EMOJI.get(step4.get("risk_level", ""), "❓")
        report_content = f"""# 诈骗分析报告

**任务ID**: {task_id}
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**风险等级**: {risk_emoji} {step4.get('risk_level', '未知')}
**诈骗概率**: {step3.get('fraud_probability', 0):.1%}
**最终判决**: {step3.get('verdict', '未知')}

---

## 内容来源
- **来源**: {step1.get('source', 'unknown')}
- **文件/主题**: {step1.get('file_name', step1.get('subject', 'N/A'))}

## 意图识别（Agent 1）
- **识别标签**: {step1.get('intent_label', 'unknown')}
- **置信度**: {step1.get('confidence', 0):.1%}
- **关键特征**: {', '.join(step1.get('key_indicators', []))}
- **内容摘要**: {step1.get('extracted_text_summary', 'N/A')}

## 案例检索（Agent 2）
- **检索到案例数**: {step2.get('total_retrieved', 0)}
- **平均相似度**: {step2.get('avg_similarity', 0):.2f}
- **低相似度警告**: {'是' if step2.get('low_similarity_warning') else '否'}

## 判别结果（Agent 3）
- **诈骗类型**: {step3.get('fraud_type', 'N/A')}
- **判断依据**:
{chr(10).join(f'  - {e}' for e in step3.get('evidence', []))}
- **反向证据**:
{chr(10).join(f'  - {e}' for e in step3.get('counter_evidence', [])) or '  无'}
- **详细说明**: {step3.get('explanation', 'N/A')}

## 风险评估（Agent 4）
- **基础分数**: {step4.get('base_score', 0):.2f}
- **规则调整**: {step4.get('total_adjustment', 0):+.2f}
- **最终风险分**: {step4.get('final_risk_score', 0):.2f}

## 处置建议
{self._get_recommendation(step4.get('risk_level', '未知'), step3.get('fraud_type'))}

---
*如本次判断有误，请回复"误判"，系统将自动反思学习*
"""
        today = datetime.now().strftime("%Y-%m-%d")
        report_path = self.reports_dir / today / f"{task_id}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        return report_path

    def _build_notification_subject(self, risk_level, verdict, fraud_type) -> str:
        emoji = self.RISK_EMOJI.get(risk_level, "❓")
        fraud_str = f"（{fraud_type}）" if fraud_type else ""
        return f"{emoji} 诈骗预警：{risk_level}风险 - {verdict}{fraud_str}"

    def _build_notification_message(
        self, task_id, risk_level, risk_score, verdict, fraud_type, source, step3
    ) -> str:
        emoji = self.RISK_EMOJI.get(risk_level, "❓")
        return (
            f"{emoji} 诈骗预警\n\n"
            f"风险等级: {risk_level}\n"
            f"诈骗概率: {risk_score:.1%}\n"
            f"判决: {verdict}\n"
            f"诈骗类型: {fraud_type or '未知'}\n"
            f"来源: {source}\n"
            f"说明: {step3.get('explanation', '')[:200]}\n\n"
            f"任务ID: {task_id}\n"
            f"如判断有误，请回复原邮件并在正文注明：误判 {task_id}"
        )

    def _alert_guardian(self, task_id, risk_level, risk_score, step3) -> bool:
        """极高风险监护人联动（邮件优先，飞书可选）"""
        alerted = False
        msg = (
            f"🚨 紧急预警 🚨\n\n"
            f"检测到极高风险诈骗信息！\n"
            f"风险分数: {risk_score:.1%}\n"
            f"说明: {step3.get('explanation', '')[:200]}\n\n"
            f"请立即干预！任务ID: {task_id}"
        )
        logger.warning(f"[Agent5] 触发监护人联动: {task_id}")

        # 监护人邮件（GUARDIAN_EMAIL 配置后生效）
        if self.guardian_email.enabled:
            ok = self.guardian_email.send("🚨 紧急预警：极高风险诈骗", msg, "极高")
            alerted = alerted or ok
        else:
            logger.warning("[Agent5] 未配置 GUARDIAN_EMAIL，跳过监护人邮件联动")

        # 可选：监护人飞书（GUARDIAN_FEISHU 配置后生效）
        if self.guardian_feishu_url:
            from utils.notifier import send_feishu
            ok = send_feishu(self.guardian_feishu_url, "🚨 紧急预警", msg, "极高")
            alerted = alerted or ok

        return alerted

    def _save_conversation(self, task_id, step1, step2, step3, step4, step5):
        """保存完整会话记录"""
        today = datetime.now().strftime("%Y-%m-%d")
        conv_dir = self.conversations_dir / today
        conv_dir.mkdir(parents=True, exist_ok=True)

        full_chain = {
            "task_id": task_id,
            "saved_at": datetime.now().isoformat(),
            "pipeline": [step1, step2, step3, step4, step5]
        }

        with open(conv_dir / f"{task_id}-full.json", "w", encoding="utf-8") as f:
            json.dump(full_chain, f, ensure_ascii=False, indent=2)

    def _get_recommendation(self, risk_level: str, fraud_type: str) -> str:
        recommendations = {
            "极高": "🚨 立即停止与对方的任何资金往来！不要点击任何链接！已触发监护人联动。",
            "高": "⚠️ 高度警惕！不要转账、不要透露验证码、不要点击不明链接。建议核实对方身份。",
            "中": "❓ 存在可疑特征，建议谨慎处理。通过官方渠道核实信息真实性。",
            "低": "ℹ️ 低风险，但仍需注意个人信息保护。",
            "安全": "✅ 未发现明显诈骗特征。"
        }
        return recommendations.get(risk_level, "请谨慎处理。")
