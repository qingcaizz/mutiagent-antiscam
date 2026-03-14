"""
邮件 IMAP 监控器
支持 QQ邮箱 / Gmail / Outlook IMAP 轮询
新邮件（含图片/附件）触发诈骗分析
"""
import imaplib
import email
import time
import json
import uuid
import os
from email.header import decode_header
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional
from loguru import logger


class EmailMonitor:
    """
    IMAP 邮件监控器
    轮询收件箱，提取图片和文本触发分析
    """

    # 常见 IMAP 服务器配置
    IMAP_SERVERS = {
        "qq": ("imap.qq.com", 993),
        "gmail": ("imap.gmail.com", 993),
        "outlook": ("imap-mail.outlook.com", 993),
        "163": ("imap.163.com", 993),
        "126": ("imap.126.com", 993),
    }

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        task_callback: Callable[[dict], None],
        pipeline_dir: str = ".pipeline/tasks",
        poll_interval: int = 30,
        attachment_save_dir: str = ".pipeline/email_attachments"
    ):
        """
        Args:
            host: IMAP 服务器地址
            port: 端口（通常 993）
            username: 邮箱账号
            password: 密码或授权码
            task_callback: 新任务触发回调
            pipeline_dir: 任务状态目录
            poll_interval: 轮询间隔（秒）
            attachment_save_dir: 附件保存目录
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.task_callback = task_callback
        self.pipeline_dir = Path(pipeline_dir)
        self.pipeline_dir.mkdir(parents=True, exist_ok=True)
        self.attachment_save_dir = Path(attachment_save_dir)
        self.attachment_save_dir.mkdir(parents=True, exist_ok=True)
        self.poll_interval = poll_interval
        self._running = False
        self._last_uid = None  # 最后处理的邮件 UID
        self._connection: Optional[imaplib.IMAP4_SSL] = None

    def _connect(self) -> bool:
        """连接 IMAP 服务器"""
        try:
            self._connection = imaplib.IMAP4_SSL(self.host, self.port)
            self._connection.login(self.username, self.password)
            logger.info(f"[Email] 已连接 {self.host}，用户: {self.username}")
            return True
        except Exception as e:
            logger.error(f"[Email] 连接失败: {e}")
            return False

    def _disconnect(self):
        """断开连接"""
        if self._connection:
            try:
                self._connection.logout()
            except Exception:
                pass
            self._connection = None

    def _fetch_new_emails(self) -> list:
        """获取未读/新邮件"""
        try:
            self._connection.select("INBOX")

            # 搜索未读邮件
            _, message_ids = self._connection.search(None, "UNSEEN")
            ids = message_ids[0].split()

            if not ids:
                return []

            logger.info(f"[Email] 发现 {len(ids)} 封新邮件")
            emails = []

            for msg_id in ids:
                try:
                    _, msg_data = self._connection.fetch(msg_id, "(RFC822)")
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    parsed = self._parse_email(msg, msg_id.decode())
                    if parsed:
                        emails.append(parsed)
                except Exception as e:
                    logger.warning(f"[Email] 解析邮件失败 {msg_id}: {e}")

            return emails
        except Exception as e:
            logger.error(f"[Email] 获取邮件失败: {e}")
            return []

    def _parse_email(self, msg: email.message.Message, msg_id: str) -> Optional[dict]:
        """解析邮件内容"""
        # 解码主题
        subject = ""
        raw_subject = msg.get("Subject", "")
        if raw_subject:
            decoded_parts = decode_header(raw_subject)
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    subject += part.decode(charset or "utf-8", errors="ignore")
                else:
                    subject += part

        sender = msg.get("From", "")
        date_str = msg.get("Date", "")

        body_text = ""
        attachments = []

        # 遍历邮件部分
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = part.get("Content-Disposition", "")

            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    body_text += part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="ignore"
                    )
                except Exception:
                    pass

            elif "attachment" in content_disposition or content_type.startswith("image/"):
                filename = part.get_filename()
                if filename:
                    # 解码文件名
                    decoded_filename = decode_header(filename)
                    decoded_name = ""
                    for part_name, charset in decoded_filename:
                        if isinstance(part_name, bytes):
                            decoded_name += part_name.decode(charset or "utf-8", errors="ignore")
                        else:
                            decoded_name += part_name

                    # 保存附件
                    save_path = self.attachment_save_dir / f"{msg_id}_{decoded_name}"
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            with open(save_path, "wb") as f:
                                f.write(payload)
                            attachments.append({
                                "filename": decoded_name,
                                "path": str(save_path),
                                "content_type": content_type,
                                "is_image": content_type.startswith("image/")
                            })
                    except Exception as e:
                        logger.warning(f"[Email] 保存附件失败 {decoded_name}: {e}")

        return {
            "msg_id": msg_id,
            "subject": subject,
            "sender": sender,
            "date": date_str,
            "body_text": body_text,
            "attachments": attachments
        }

    def _create_task(self, email_data: dict):
        """创建分析任务"""
        task_id = f"email-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        task_dir = self.pipeline_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        task_input = {
            "task_id": task_id,
            "source": "email",
            "email_id": email_data["msg_id"],
            "subject": email_data["subject"],
            "sender": email_data["sender"],
            "body_text": email_data["body_text"],
            "attachments": email_data["attachments"],
            "has_images": any(a["is_image"] for a in email_data["attachments"]),
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }

        with open(task_dir / "input.json", "w", encoding="utf-8") as f:
            json.dump(task_input, f, ensure_ascii=False, indent=2)

        logger.info(f"[Email] 任务创建: {task_id} | 主题: {email_data['subject'][:50]}")
        self.task_callback(task_input)

    def start(self):
        """启动轮询监控"""
        if not self._connect():
            return False

        self._running = True
        logger.info(f"[Email] 开始轮询，间隔 {self.poll_interval}s")

        while self._running:
            try:
                # 检测连接是否还活跃
                try:
                    self._connection.noop()
                except Exception:
                    logger.warning("[Email] 连接断开，重新连接...")
                    self._disconnect()
                    if not self._connect():
                        time.sleep(10)
                        continue

                # 获取新邮件
                new_emails = self._fetch_new_emails()
                for email_data in new_emails:
                    try:
                        self._create_task(email_data)
                    except Exception as e:
                        logger.error(f"[Email] 任务创建失败: {e}")

                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"[Email] 轮询异常: {e}")
                time.sleep(5)

        self._disconnect()
        logger.info("[Email] 监控已停止")

    def stop(self):
        """停止监控"""
        self._running = False

    @classmethod
    def from_env(cls, task_callback: Callable) -> "EmailMonitor":
        """从环境变量创建监控器"""
        from dotenv import load_dotenv
        load_dotenv()

        host = os.getenv("EMAIL_HOST", "imap.qq.com")
        port = int(os.getenv("EMAIL_PORT", "993"))
        user = os.getenv("EMAIL_USER", "")
        password = os.getenv("EMAIL_PASS", "")

        if not user or not password:
            raise ValueError("EMAIL_USER 和 EMAIL_PASS 环境变量未配置")

        return cls(
            host=host,
            port=port,
            username=user,
            password=password,
            task_callback=task_callback
        )


# 使用示例
if __name__ == "__main__":
    def dummy_callback(task: dict):
        logger.info(f"新邮件任务: {task['task_id']} | {task.get('subject', 'No Subject')}")

    monitor = EmailMonitor.from_env(task_callback=dummy_callback)
    monitor.start()
