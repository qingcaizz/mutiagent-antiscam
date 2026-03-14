"""
Agent 1: 多模态预处理 + 意图识别
- GLM-4.6V 理解图片内容（替代 OCR + Claude Vision 两条路径）
- Qwen3.5 意图分类（替代 anthropic SDK）
- 输出：图像描述 / 文本内容 + 意图标签 + 置信度
"""
import base64
import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

import requests
from openai import OpenAI
from loguru import logger


# 智谱 GLM API 基础地址
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
# 南审 Qwen API 基础地址
NAU_BASE_URL = "https://ai-api.nau.edu.cn/v1"
# 意图标签配置文件路径（相对项目根目录）
INTENT_LABELS_PATH = Path(__file__).parent.parent / "config" / "intent_labels.json"


class PreprocessorAgent:
    """Agent 1: 多模态预处理 + 意图识别（GLM-4.6V + Qwen3.5 双路）"""

    SYSTEM_PROMPT = """你是一个专业的诈骗识别分析师，专门分析中文诈骗信息。
你的任务是对给定的文本/图片描述内容进行意图识别。

请严格按照以下 JSON 格式输出（不要添加任何其他内容，不要输出 markdown 代码块）：
{
    "intent_label": "意图标签（从提供列表中选择）",
    "confidence": 0.85,
    "key_indicators": ["关键特征1", "关键特征2"],
    "extracted_text_summary": "提取内容摘要（100字内）",
    "reasoning": "判断理由（简洁）"
}

意图标签选项（必须从以下标签中选择一个，不得自造标签）：
- financial_fraud: 金融诈骗（转账/贷款/投资）
- impersonation: 冒充身份（公检法/亲友/客服）
- phishing: 钓鱼链接/验证码
- romance_scam: 情感骗局
- lottery_scam: 中奖诈骗
- job_scam: 刷单/招聘诈骗
- normal_business: 正常商业
- personal_communication: 正常通讯
- spam_advertising: 垃圾广告
- unknown: 无法判断
"""

    def __init__(self):
        """
        初始化 GLM 和 Qwen 双客户端，加载意图标签配置。

        Raises:
            EnvironmentError: 若 ZHIPU_API_KEY 或 NAU_API_KEY 未设置。
        """
        zhipu_key = os.environ.get("ZHIPU_API_KEY")
        nau_key = os.environ.get("NAU_API_KEY")

        if not zhipu_key:
            raise EnvironmentError(
                "环境变量 ZHIPU_API_KEY 未设置。"
                "请通过 export ZHIPU_API_KEY=<你的智谱Key> 或 .env 文件配置。"
            )
        if not nau_key:
            raise EnvironmentError(
                "环境变量 NAU_API_KEY 未设置。"
                "请通过 export NAU_API_KEY=<你的南审Key> 或 .env 文件配置。"
            )

        self._zhipu_key = zhipu_key
        # Qwen 客户端（OpenAI SDK 兼容接口）
        self._qwen_client = OpenAI(base_url=NAU_BASE_URL, api_key=nau_key)

        # 从配置文件加载合法标签列表
        with open(INTENT_LABELS_PATH, encoding="utf-8") as f:
            labels_config = json.load(f)
        self.valid_labels: list[str] = [item["id"] for item in labels_config["labels"]]

        logger.info(
            f"[Agent1] 初始化完成，已加载 {len(self.valid_labels)} 种意图标签"
        )

    def _glm_analyze_image(self, file_path: str) -> str:
        """
        调用 GLM-4.6V 分析图片，返回图像内容描述文本。

        Args:
            file_path: 图片文件路径。

        Returns:
            GLM 返回的图像描述字符串。
        """
        ext_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".webp": "image/webp",
        }
        ext = Path(file_path).suffix.lower()
        media_type = ext_map.get(ext, "image/jpeg")

        with open(file_path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode("utf-8")

        resp = requests.post(
            f"{GLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._zhipu_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "glm-4.6v",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{img_data}"
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "请详细描述这张图片的内容，"
                                    "包括所有文字、图形、颜色和可能的含义。"
                                ),
                            },
                        ],
                    }
                ],
                "max_tokens": 1024,
            },
            timeout=60,
        )
        resp.raise_for_status()
        glm_result = resp.json()
        image_description: str = glm_result["choices"][0]["message"]["content"]
        logger.info(f"[Agent1] GLM 图像描述: {len(image_description)} 字符")
        return image_description

    def _qwen_classify_intent(self, content: str, source: str, file_name: str) -> dict:
        """
        调用 Qwen3.5 对内容进行意图分类。

        Args:
            content: 待分析的文本内容（图像描述或邮件正文）。
            source: 来源（wechat/email/unknown）。
            file_name: 文件名或邮件主题。

        Returns:
            解析后的意图分类结果字典。
        """
        valid_labels_str = "\n".join(
            f"- {label}" for label in self.valid_labels
        )
        analysis_prompt = (
            f"请分析以下内容的诈骗意图：\n\n"
            f"来源：{source}\n"
            f"文件名/主题：{file_name}\n\n"
            f"内容描述：\n{content[:3000]}\n\n"
            f"合法意图标签（必须从以下选项中选择一个）：\n{valid_labels_str}\n\n"
            f"请识别意图并严格按照 JSON 格式输出结果。"
        )

        response = self._qwen_client.chat.completions.create(
            model="qwen3.5-35b-a3b-fp8",
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": analysis_prompt},
            ],
            max_tokens=1024,
        )
        response_text = response.choices[0].message.content.strip()

        # 移除 Qwen thinking 模型的思考链标签 <think>...</think>
        response_text = re.sub(r"<think>[\s\S]*?</think>", "", response_text).strip()

        # 清理可能的 markdown 代码块
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        # 提取第一个完整 JSON 对象（模型可能在 JSON 后附加说明文字）
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            response_text = json_match.group(0)

        if not response_text:
            raise ValueError("Qwen 返回空内容，无法解析 JSON")

        intent_result = json.loads(response_text)

        # 校验 intent_label 合法性，不合法则回退 unknown
        if intent_result.get("intent_label") not in self.valid_labels:
            logger.warning(
                f"[Agent1] Qwen 返回了非法标签: {intent_result.get('intent_label')}，"
                "已回退为 unknown"
            )
            intent_result["intent_label"] = "unknown"

        return intent_result

    def run(self, task_input: dict, step_dir: Path) -> dict:
        """
        执行预处理 + 意图识别。

        Args:
            task_input: 任务输入字典。
            step_dir: 步骤输出目录（.pipeline/tasks/{id}/）。

        Returns:
            step1 结果字典。
        """
        logger.info(f"[Agent1] 开始处理: {task_input['task_id']}")
        result = {
            "step": 1,
            "agent": "preprocessor",
            "task_id": task_input["task_id"],
            "started_at": datetime.now().isoformat(),
            "status": "processing",
        }

        try:
            content = ""
            source = task_input.get("source", "unknown")
            file_name = task_input.get("file_name", task_input.get("subject", "unknown"))

            # 步骤1：内容获取（图片 → GLM 描述；邮件 → 直接使用文本）
            if task_input.get("file_type") == "image":
                file_path = task_input.get("file_path", "")
                if file_path and Path(file_path).exists():
                    content = self._glm_analyze_image(file_path)
                else:
                    content = "（图片文件不存在或路径无效）"

            elif source == "email":
                content = task_input.get("body_text", "")
                # 处理邮件附件图片（可选）
                for attachment in task_input.get("attachments", []):
                    if attachment.get("is_image"):
                        att_path = attachment.get("path", "")
                        if att_path and Path(att_path).exists():
                            att_desc = self._glm_analyze_image(att_path)
                            content += f"\n[附件图片描述]: {att_desc}"

            else:
                content = task_input.get("body_text", task_input.get("text", ""))

            # 步骤2：Qwen 意图分类
            intent_result = self._qwen_classify_intent(content, source, file_name)

            result.update(
                {
                    "status": "success",
                    "extracted_text": content,
                    "intent_label": intent_result.get("intent_label", "unknown"),
                    "confidence": float(intent_result.get("confidence", 0.0)),
                    "key_indicators": intent_result.get("key_indicators", []),
                    "extracted_text_summary": intent_result.get(
                        "extracted_text_summary", ""
                    ),
                    "reasoning": intent_result.get("reasoning", ""),
                    "completed_at": datetime.now().isoformat(),
                }
            )

        except Exception as e:
            logger.error(f"[Agent1] 处理失败: {e}")
            result.update(
                {
                    "status": "failed",
                    "error": str(e),
                    "extracted_text": "",
                    "intent_label": "unknown",
                    "confidence": 0.0,
                    "key_indicators": [],
                    "extracted_text_summary": "",
                    "completed_at": datetime.now().isoformat(),
                }
            )

        # 保存步骤结果
        step_file = Path(step_dir) / "step1.json"
        with open(step_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[Agent1] 完成: {result['intent_label']} ({result.get('confidence', 0):.2f})"
        )
        return result
