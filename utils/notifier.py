"""
通知渠道封装（可插拔）
- EmailNotifier: SMTP 邮件通知（首选，复用已配置的邮箱）
- FeishuNotifier: 飞书 Webhook 推送（可选）
- DingTalkNotifier: 钉钉 Webhook 推送（可选）
- send_alert: 自动按已配置渠道发送，用户在 .env 配了哪个就用哪个

通知渠道优先级（有配置就发，可叠加）：
  EMAIL_USER + SMTP_HOST + NOTIFY_TO_EMAIL → 邮件
  FEISHU_WEBHOOK_URL → 飞书
  DINGTALK_WEBHOOK_URL → 钉钉
"""
from __future__ import annotations

import asyncio
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from loguru import logger

# ------------------------------------------------------------------
# 风险等级 → 颜色（飞书 card color / 钉钉 markdown 颜色标签）
# ------------------------------------------------------------------
_RISK_COLOR_FEISHU: dict[str, str] = {
    "低": "green",
    "中": "yellow",
    "高": "orange",
    "极高": "red",
    "安全": "green",
}

_RISK_COLOR_DINGTALK: dict[str, str] = {
    "低": "#00CC00",    # 绿
    "中": "#FFBB00",    # 黄
    "高": "#FF6600",    # 橙
    "极高": "#FF0000",  # 红
    "安全": "#00CC00",
}

_RISK_EMOJI: dict[str, str] = {
    "低": "ℹ️",
    "中": "❓",
    "高": "⚠️",
    "极高": "🚨",
    "安全": "✅",
}

# 默认超时（秒）
_HTTP_TIMEOUT = 10.0


# ------------------------------------------------------------------
# 邮件通知器（复用已配置的 QQ/Gmail 邮箱）
# ------------------------------------------------------------------

class EmailNotifier:
    """SMTP 邮件通知器。

    复用监控邮箱（EMAIL_USER/EMAIL_PASS）作为发件人，
    发送给 NOTIFY_TO_EMAIL 指定的收件人。

    SMTP 配置（.env）：
        SMTP_HOST      - SMTP 服务器，默认从 EMAIL_HOST 推断（imap→smtp）
        SMTP_PORT      - 端口，默认 465（SSL）
        EMAIL_USER     - 发件人账号（复用监控邮箱）
        EMAIL_PASS     - 发件人密码/授权码（复用监控邮箱）
        NOTIFY_TO_EMAIL - 收件人地址（逗号分隔可填多个）
    """

    def __init__(
        self,
        smtp_host: str = "",
        smtp_port: int = 465,
        username: str = "",
        password: str = "",
        to_addrs: str = "",
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        # 支持多收件人，逗号分隔
        self.to_addrs = [a.strip() for a in to_addrs.split(",") if a.strip()]

    @property
    def enabled(self) -> bool:
        return bool(self.smtp_host and self.username and self.password and self.to_addrs)

    def send(self, subject: str, body: str, risk_level: str = "") -> bool:
        """发送 HTML 邮件通知。"""
        if not self.enabled:
            logger.warning("[Email] 邮件通知未配置（需要 SMTP_HOST/EMAIL_USER/EMAIL_PASS/NOTIFY_TO_EMAIL），跳过")
            return False
        try:
            emoji = _RISK_EMOJI.get(risk_level, "")
            full_subject = f"{emoji} {subject}".strip() if emoji else subject

            msg = MIMEMultipart("alternative")
            msg["Subject"] = full_subject
            msg["From"] = self.username
            msg["To"] = ", ".join(self.to_addrs)

            # 纯文本备用
            msg.attach(MIMEText(body, "plain", "utf-8"))
            # HTML 版本（简单 Markdown 风格）
            html_body = body.replace("\n", "<br>").replace("**", "<b>").replace("**", "</b>")
            msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html", "utf-8"))

            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.username, self.password)
                server.sendmail(self.username, self.to_addrs, msg.as_string())

            logger.info(f"[Email] 通知已发送至 {self.to_addrs}")
            return True
        except Exception as exc:
            logger.error(f"[Email] 发送失败: {exc}")
            return False


def _infer_smtp_host(imap_host: str) -> str:
    """从 IMAP 地址推断 SMTP 地址（imap.qq.com → smtp.qq.com）。"""
    return imap_host.replace("imap.", "smtp.", 1) if imap_host.startswith("imap.") else imap_host


# ------------------------------------------------------------------
# 飞书通知器（可选）
# ------------------------------------------------------------------

class FeishuNotifier:
    """飞书 Webhook 通知器。"""

    def __init__(self, webhook_url: str = "") -> None:
        self.webhook_url = webhook_url

    def send(self, message: str) -> bool:
        """同步发送消息（内部调用异步实现）。"""
        if not self.webhook_url:
            logger.warning("[Feishu] webhook_url 未配置，跳过发送")
            return False
        return _run_async(self._async_send_text(message))

    def send_card(self, title: str, content: str, risk_level: str) -> bool:
        """发送飞书富文本卡片消息。"""
        if not self.webhook_url:
            logger.warning("[Feishu] webhook_url 未配置，跳过发送")
            return False
        return _run_async(self._async_send_card(title, content, risk_level))

    async def _async_send_text(self, message: str) -> bool:
        payload = {
            "msg_type": "text",
            "content": {"text": message},
        }
        return await self._post(payload)

    async def _async_send_card(
        self, title: str, content: str, risk_level: str
    ) -> bool:
        color = _RISK_COLOR_FEISHU.get(risk_level, "blue")
        emoji = _RISK_EMOJI.get(risk_level, "❓")
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{emoji} {title}",
                    },
                    "template": color,
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": content,
                        },
                    }
                ],
            },
        }
        return await self._post(payload)

    async def _post(self, payload: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code", 0) == 0 or data.get("StatusCode") == 0:
                    logger.info("[Feishu] 消息发送成功")
                    return True
                else:
                    logger.warning(f"[Feishu] 发送失败，响应: {data}")
                    return False
        except httpx.HTTPError as exc:
            logger.error(f"[Feishu] HTTP 错误: {exc}")
            return False
        except Exception as exc:
            logger.error(f"[Feishu] 发送异常: {exc}")
            return False


# ------------------------------------------------------------------
# 钉钉通知器
# ------------------------------------------------------------------

class DingTalkNotifier:
    """钉钉 Webhook 通知器。"""

    def __init__(self, webhook_url: str = "") -> None:
        self.webhook_url = webhook_url

    def send(self, message: str) -> bool:
        """同步发送 Markdown 消息。"""
        if not self.webhook_url:
            logger.warning("[DingTalk] webhook_url 未配置，跳过发送")
            return False
        return _run_async(self._async_send_markdown("诈骗预警", message))

    def send_markdown(self, title: str, content: str, risk_level: str) -> bool:
        """发送钉钉 Markdown 富文本消息。"""
        if not self.webhook_url:
            logger.warning("[DingTalk] webhook_url 未配置，跳过发送")
            return False
        return _run_async(self._async_send_markdown(title, content))

    async def _async_send_markdown(self, title: str, content: str) -> bool:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": content,
            },
        }
        return await self._post(payload)

    async def _post(self, payload: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("errcode", -1) == 0:
                    logger.info("[DingTalk] 消息发送成功")
                    return True
                else:
                    logger.warning(f"[DingTalk] 发送失败，响应: {data}")
                    return False
        except httpx.HTTPError as exc:
            logger.error(f"[DingTalk] HTTP 错误: {exc}")
            return False
        except Exception as exc:
            logger.error(f"[DingTalk] 发送异常: {exc}")
            return False


# ------------------------------------------------------------------
# 模块级快捷函数
# ------------------------------------------------------------------

async def _async_send_feishu(
    webhook_url: str, title: str, content: str, risk_level: str
) -> bool:
    """异步发送飞书卡片通知。"""
    notifier = FeishuNotifier(webhook_url)
    return await notifier._async_send_card(title, content, risk_level)


async def _async_send_dingtalk(
    webhook_url: str, title: str, content: str, risk_level: str
) -> bool:
    """异步发送钉钉 Markdown 通知。"""
    emoji = _RISK_EMOJI.get(risk_level, "❓")
    color = _RISK_COLOR_DINGTALK.get(risk_level, "#0078D7")
    markdown_content = (
        f"## {emoji} {title}\n\n"
        f"> 风险等级：<font color='{color}'>{risk_level}</font>\n\n"
        f"{content}"
    )
    notifier = DingTalkNotifier(webhook_url)
    return await notifier._async_send_markdown(title, markdown_content)


def send_feishu(
    webhook_url: str, title: str, content: str, risk_level: str
) -> bool:
    """
    发送飞书 Webhook 通知（同步接口）。

    Args:
        webhook_url: 飞书机器人 Webhook 地址
        title: 消息标题
        content: 消息正文（支持飞书 Markdown）
        risk_level: 风险等级（低/中/高/极高/安全）

    Returns:
        发送成功返回 True，否则返回 False。
    """
    return _run_async(_async_send_feishu(webhook_url, title, content, risk_level))


def send_dingtalk(
    webhook_url: str, title: str, content: str, risk_level: str
) -> bool:
    """
    发送钉钉 Webhook 通知（同步接口）。

    Args:
        webhook_url: 钉钉机器人 Webhook 地址
        title: 消息标题
        content: 消息正文（支持钉钉 Markdown）
        risk_level: 风险等级（低/中/高/极高/安全）

    Returns:
        发送成功返回 True，否则返回 False。
    """
    return _run_async(_async_send_dingtalk(webhook_url, title, content, risk_level))


def send_alert(title: str, content: str, risk_level: str) -> bool:
    """
    自动读取环境变量，向所有已配置的渠道发送预警通知。

    支持的渠道（有配置就发，可叠加）：
      - 邮件：SMTP_HOST（或自动从 EMAIL_HOST 推断）+ EMAIL_USER + EMAIL_PASS + NOTIFY_TO_EMAIL
      - 飞书：FEISHU_WEBHOOK_URL
      - 钉钉：DINGTALK_WEBHOOK_URL

    一个都没配时记录警告并返回 False，至少一个成功返回 True。
    """
    results: list[bool] = []

    # --- 邮件渠道 ---
    notify_to = os.getenv("NOTIFY_TO_EMAIL", "").strip()
    email_user = os.getenv("EMAIL_USER", "").strip()
    email_pass = os.getenv("EMAIL_PASS", "").strip()
    smtp_host = (
        os.getenv("SMTP_HOST", "").strip()
        or _infer_smtp_host(os.getenv("EMAIL_HOST", "").strip())
    )
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    email_notifier = EmailNotifier(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        username=email_user,
        password=email_pass,
        to_addrs=notify_to,
    )
    if email_notifier.enabled:
        ok = email_notifier.send(title, content, risk_level)
        results.append(ok)

    # --- 飞书渠道（可选）---
    feishu_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if feishu_url and not feishu_url.startswith("https://open.feishu.cn/open-apis/bot/v2/hook/YOUR"):
        ok = send_feishu(feishu_url, title, content, risk_level)
        results.append(ok)

    # --- 钉钉渠道（可选）---
    dingtalk_url = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
    if dingtalk_url and not dingtalk_url.startswith("https://oapi.dingtalk.com/robot/send?access_token=YOUR"):
        ok = send_dingtalk(dingtalk_url, title, content, risk_level)
        results.append(ok)

    if not results:
        logger.warning(
            "[Notifier] 未配置任何通知渠道（NOTIFY_TO_EMAIL / FEISHU_WEBHOOK_URL / DINGTALK_WEBHOOK_URL），跳过通知"
        )
        return False

    return any(results)


# ------------------------------------------------------------------
# 内部工具：在同步上下文中运行协程
# ------------------------------------------------------------------

def _run_async(coro) -> bool:
    """在同步上下文中运行异步协程，兼容已有事件循环的情况。"""
    try:
        loop = asyncio.get_running_loop()
        # 如果已有运行中的事件循环（如 Jupyter / FastAPI），使用 nest_asyncio
        import nest_asyncio  # type: ignore
        nest_asyncio.apply(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        # 没有运行中的事件循环，直接 run
        return asyncio.run(coro)
    except ImportError:
        # nest_asyncio 未安装，回退到新线程执行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result(timeout=_HTTP_TIMEOUT + 5)
