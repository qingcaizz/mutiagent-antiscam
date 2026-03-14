"""
Email IMAP 监控器 TDD 测试套件

覆盖：
- MONITOR-02: IMAP 轮询检测新邮件

测试策略：
- 主路单元测试：mock imaplib.IMAP4_SSL，验证 _connect/_fetch_new_emails/_create_task
- 主路集成测试：构造真实 email.message.Message 对象，直接调用 _parse_email
- Playwright 备路骨架：@pytest.mark.playwright，验证数据处理逻辑
"""
import sys
import email
import email.mime.multipart
import email.mime.text
import email.mime.image
import email.mime.base
from email.header import make_header, decode_header
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from monitor.email_monitor import EmailMonitor


# ──────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────

def make_raw_email(
    subject: str = "Test Subject",
    from_addr: str = "sender@example.com",
    body: str = "Test body text",
    has_image: bool = False,
    image_filename: str = "test.png",
    subject_charset: str = None,
) -> bytes:
    """
    构造真实的 RFC822 邮件字节。
    subject_charset: 若指定，对 subject 使用 RFC 2047 编码（如 'utf-8', 'gb2312'）
    """
    msg = email.mime.multipart.MIMEMultipart()

    if subject_charset:
        # RFC 2047 编码主题
        from email.header import Header
        msg['Subject'] = Header(subject, subject_charset)
    else:
        msg['Subject'] = subject

    msg['From'] = from_addr
    msg['Date'] = 'Sat, 14 Mar 2026 10:00:00 +0800'

    # 添加文本正文
    msg.attach(email.mime.text.MIMEText(body, 'plain', 'utf-8'))

    if has_image:
        # 构造最小有效 PNG 字节（1x1 透明像素）
        png_bytes = (
            b'\x89PNG\r\n\x1a\n'  # PNG signature
            b'\x00\x00\x00\rIHDR'  # IHDR chunk
            b'\x00\x00\x00\x01\x00\x00\x00\x01'  # 1x1
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'  # 32-bit RGBA
            b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4'
            b'\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        img_part = email.mime.image.MIMEImage(png_bytes, _subtype='png')
        img_part.add_header('Content-Disposition', 'attachment', filename=image_filename)
        msg.attach(img_part)

    return msg.as_bytes()


def make_monitor(tmp_path: Path) -> EmailMonitor:
    """创建 EmailMonitor 实例，使用 tmp_path 内的目录"""
    pipeline_dir = str(tmp_path / '.pipeline' / 'tasks')
    attachment_dir = str(tmp_path / 'attachments')
    return EmailMonitor(
        host='imap.test.com',
        port=993,
        username='test@test.com',
        password='pass',
        task_callback=MagicMock(),
        pipeline_dir=pipeline_dir,
        attachment_save_dir=attachment_dir,
    )


# ──────────────────────────────────────────────────────────────
# Fixture
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def monitor(tmp_path):
    """提供 EmailMonitor fixture，使用 tmp_path 内的隔离目录"""
    return make_monitor(tmp_path)


# ──────────────────────────────────────────────────────────────
# 测试类 1: _connect() 连接测试
# ──────────────────────────────────────────────────────────────

class TestEmailMonitorConnect:
    """测试 _connect() 的成功和失败路径"""

    def test_connect_success(self, monitor):
        """_connect() 登录成功 → 返回 True，logger.info 含 '已连接'"""
        with patch('monitor.email_monitor.imaplib.IMAP4_SSL') as MockIMAP, \
             patch('monitor.email_monitor.logger') as mock_logger:
            mock_conn = MagicMock()
            MockIMAP.return_value = mock_conn
            mock_conn.login.return_value = ('OK', [b'Logged in'])

            result = monitor._connect()

        assert result is True
        mock_conn.login.assert_called_once_with('test@test.com', 'pass')
        # logger.info 应被调用，且消息含 '已连接'
        assert mock_logger.info.called
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any('已连接' in c for c in info_calls)

    def test_connect_failure_exception(self, monitor):
        """_connect() login 抛出 Exception → 返回 False，logger.error 含 '连接失败'"""
        with patch('monitor.email_monitor.imaplib.IMAP4_SSL') as MockIMAP, \
             patch('monitor.email_monitor.logger') as mock_logger:
            MockIMAP.side_effect = Exception("Connection refused")

            result = monitor._connect()

        assert result is False
        assert mock_logger.error.called
        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert any('连接失败' in c for c in error_calls)

    def test_connect_login_failure(self, monitor):
        """_connect() IMAP4_SSL 实例化成功但 login 抛异常 → 返回 False"""
        with patch('monitor.email_monitor.imaplib.IMAP4_SSL') as MockIMAP, \
             patch('monitor.email_monitor.logger'):
            mock_conn = MagicMock()
            MockIMAP.return_value = mock_conn
            mock_conn.login.side_effect = Exception("Invalid credentials")

            result = monitor._connect()

        assert result is False


# ──────────────────────────────────────────────────────────────
# 测试类 2: _fetch_new_emails() — mock IMAP 连接
# ──────────────────────────────────────────────────────────────

class TestFetchNewEmails:
    """测试 _fetch_new_emails() 的各种场景，mock imaplib 连接"""

    def _setup_mock_connection(self, monitor, mock_conn):
        """将 mock 连接注入到 monitor 中"""
        monitor._connection = mock_conn

    def test_no_unread_returns_empty(self, monitor):
        """search 返回空字符串 → 返回 []"""
        mock_conn = MagicMock()
        mock_conn.search.return_value = ('OK', [b''])
        self._setup_mock_connection(monitor, mock_conn)

        result = monitor._fetch_new_emails()

        assert result == []
        mock_conn.select.assert_called_once_with('INBOX')

    def test_one_unread_text_only(self, monitor):
        """search 返回 b'1'，fetch 返回纯文本邮件 → 列表长度 1，attachments=[]"""
        mock_conn = MagicMock()
        raw = make_raw_email(subject='Hello', body='Hello World', has_image=False)
        mock_conn.search.return_value = ('OK', [b'1'])
        mock_conn.fetch.return_value = ('OK', [(b'1 (RFC822 {123})', raw)])
        self._setup_mock_connection(monitor, mock_conn)

        result = monitor._fetch_new_emails()

        assert len(result) == 1
        assert result[0]['subject'] == 'Hello'
        assert result[0]['attachments'] == []
        assert result[0]['msg_id'] == '1'

    def test_one_unread_with_image(self, monitor):
        """fetch 返回含 image/png 附件邮件 → attachments[0]['is_image'] == True"""
        mock_conn = MagicMock()
        raw = make_raw_email(subject='Image Email', has_image=True, image_filename='photo.png')
        mock_conn.search.return_value = ('OK', [b'1'])
        mock_conn.fetch.return_value = ('OK', [(b'1 (RFC822 {456})', raw)])
        self._setup_mock_connection(monitor, mock_conn)

        result = monitor._fetch_new_emails()

        assert len(result) == 1
        assert len(result[0]['attachments']) == 1
        assert result[0]['attachments'][0]['is_image'] is True
        assert result[0]['attachments'][0]['filename'] == 'photo.png'

    def test_two_unread_returns_list_of_two(self, monitor):
        """search 返回 b'1 2' → 返回列表长度 2"""
        mock_conn = MagicMock()
        raw1 = make_raw_email(subject='Email 1')
        raw2 = make_raw_email(subject='Email 2')
        mock_conn.search.return_value = ('OK', [b'1 2'])
        mock_conn.fetch.side_effect = [
            ('OK', [(b'1 (RFC822 {100})', raw1)]),
            ('OK', [(b'2 (RFC822 {100})', raw2)]),
        ]
        self._setup_mock_connection(monitor, mock_conn)

        result = monitor._fetch_new_emails()

        assert len(result) == 2

    def test_fetch_parse_error_skips_email(self, monitor):
        """fetch 抛出 Exception → logger.warning 被调用，返回 []（跳过该邮件）"""
        mock_conn = MagicMock()
        mock_conn.search.return_value = ('OK', [b'1'])
        mock_conn.fetch.side_effect = Exception("Network error")
        self._setup_mock_connection(monitor, mock_conn)

        with patch('monitor.email_monitor.logger') as mock_logger:
            result = monitor._fetch_new_emails()

        assert result == []
        assert mock_logger.warning.called
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any('解析邮件失败' in c for c in warning_calls)

    def test_two_unread_one_fails_other_succeeds(self, monitor):
        """两封邮件中 fetch 第一封成功，第二封失败 → 返回列表长度 1"""
        mock_conn = MagicMock()
        raw1 = make_raw_email(subject='Good Email')
        mock_conn.search.return_value = ('OK', [b'1 2'])
        mock_conn.fetch.side_effect = [
            ('OK', [(b'1 (RFC822 {100})', raw1)]),
            Exception("Fetch failed for msg 2"),
        ]
        self._setup_mock_connection(monitor, mock_conn)

        with patch('monitor.email_monitor.logger'):
            result = monitor._fetch_new_emails()

        assert len(result) == 1
        assert result[0]['subject'] == 'Good Email'


# ──────────────────────────────────────────────────────────────
# 测试类 3: _parse_email() — 真实 MIME 构造（不 mock imaplib）
# ──────────────────────────────────────────────────────────────

class TestParseEmail:
    """集成测试：使用真实 email.message.Message 对象，直接调用 _parse_email"""

    def test_parse_chinese_subject_utf8(self, monitor):
        """UTF-8 base64 编码主题 → 正确解码为中文"""
        raw = make_raw_email(subject='测试邮件', subject_charset='utf-8')
        msg = email.message_from_bytes(raw)
        result = monitor._parse_email(msg, '1')
        assert result is not None
        assert '测试邮件' in result['subject']

    def test_parse_gb2312_subject(self, monitor):
        """GB2312 编码主题 → 正确解码为中文"""
        raw = make_raw_email(subject='诈骗检测', subject_charset='gb2312')
        msg = email.message_from_bytes(raw)
        result = monitor._parse_email(msg, '1')
        assert result is not None
        # 解码后应包含中文字符（不是乱码）
        assert result['subject'] != ''
        # 中文字符应能被识别
        assert any('\u4e00' <= c <= '\u9fff' for c in result['subject'])

    def test_parse_image_attachment_saved(self, monitor):
        """含 image/png 附件 → attachments 非空，文件已写入 attachment_save_dir"""
        raw = make_raw_email(
            subject='Image Test',
            has_image=True,
            image_filename='test.png',
        )
        msg = email.message_from_bytes(raw)
        result = monitor._parse_email(msg, '42')

        assert result is not None
        assert len(result['attachments']) == 1
        att = result['attachments'][0]
        assert att['is_image'] is True
        assert att['filename'] == 'test.png'
        assert att['content_type'] == 'image/png'

        # 文件应写入 attachment_save_dir，文件名格式为 {msg_id}_{filename}
        save_path = monitor.attachment_save_dir / '42_test.png'
        assert save_path.exists(), f"附件文件不存在: {save_path}"

    def test_parse_text_only_no_attachments(self, monitor):
        """纯文本邮件 → body_text 非空，attachments == []"""
        raw = make_raw_email(
            subject='Text Only',
            body='This is plain text body.',
            has_image=False,
        )
        msg = email.message_from_bytes(raw)
        result = monitor._parse_email(msg, '1')

        assert result is not None
        assert result['body_text'] != ''
        assert 'This is plain text body.' in result['body_text']
        assert result['attachments'] == []

    def test_parse_returns_dict_with_required_keys(self, monitor):
        """_parse_email() 返回值包含所有必需字段"""
        raw = make_raw_email(subject='Full Test', from_addr='user@example.com')
        msg = email.message_from_bytes(raw)
        result = monitor._parse_email(msg, '99')

        assert result is not None
        required_keys = {'msg_id', 'subject', 'sender', 'date', 'body_text', 'attachments'}
        assert required_keys.issubset(result.keys())
        assert result['msg_id'] == '99'
        assert result['sender'] == 'user@example.com'

    def test_parse_multipart_with_text_and_image(self, monitor):
        """multipart 邮件含 text/plain + image/png → body_text 和 attachments 均正确"""
        raw = make_raw_email(
            subject='Multipart',
            body='Multipart body',
            has_image=True,
            image_filename='photo.png',
        )
        msg = email.message_from_bytes(raw)
        result = monitor._parse_email(msg, '10')

        assert result is not None
        assert 'Multipart body' in result['body_text']
        assert len(result['attachments']) == 1
        assert result['attachments'][0]['is_image'] is True


# ──────────────────────────────────────────────────────────────
# 测试类 4: _create_task() — 任务创建逻辑
# ──────────────────────────────────────────────────────────────

class TestCreateTask:
    """测试 _create_task() 回调和 task_input 结构"""

    def _make_email_data(self, has_image: bool = False):
        """构造 email_data dict，模拟 _fetch_new_emails() 的输出"""
        attachments = []
        if has_image:
            attachments = [{
                'filename': 'test.png',
                'path': '/tmp/test.png',
                'content_type': 'image/png',
                'is_image': True,
            }]
        return {
            'msg_id': 'test-msg-001',
            'subject': '紧急通知',
            'sender': 'fraud@example.com',
            'date': 'Sat, 14 Mar 2026 10:00:00 +0800',
            'body_text': '您的账户存在风险',
            'attachments': attachments,
        }

    def test_create_task_calls_callback(self, monitor):
        """传入 email_data → task_callback 被调用 1 次"""
        email_data = self._make_email_data(has_image=False)
        monitor._create_task(email_data)
        assert monitor.task_callback.call_count == 1

    def test_create_task_source_is_email(self, monitor):
        """task_input['source'] == 'email'"""
        email_data = self._make_email_data(has_image=False)
        monitor._create_task(email_data)
        task_input = monitor.task_callback.call_args[0][0]
        assert task_input['source'] == 'email'

    def test_create_task_has_images_true(self, monitor):
        """email_data 含 image 附件 → task_input['has_images'] == True"""
        email_data = self._make_email_data(has_image=True)
        monitor._create_task(email_data)
        task_input = monitor.task_callback.call_args[0][0]
        assert task_input['has_images'] is True

    def test_create_task_has_images_false(self, monitor):
        """email_data 无附件 → task_input['has_images'] == False"""
        email_data = self._make_email_data(has_image=False)
        monitor._create_task(email_data)
        task_input = monitor.task_callback.call_args[0][0]
        assert task_input['has_images'] is False

    def test_create_task_writes_input_json(self, monitor):
        """pipeline_dir 内出现 email-*/input.json"""
        email_data = self._make_email_data()
        monitor._create_task(email_data)
        # 查找 pipeline_dir 下所有 input.json 文件
        json_files = list(monitor.pipeline_dir.glob('email-*/input.json'))
        assert len(json_files) == 1, f"期望 1 个 input.json，找到: {json_files}"

    def test_create_task_input_json_content(self, monitor):
        """input.json 内容包含 subject 和 sender"""
        import json
        email_data = self._make_email_data(has_image=False)
        monitor._create_task(email_data)
        json_files = list(monitor.pipeline_dir.glob('email-*/input.json'))
        assert len(json_files) == 1
        with open(json_files[0], encoding='utf-8') as f:
            content = json.load(f)
        assert content['subject'] == '紧急通知'
        assert content['sender'] == 'fraud@example.com'
        assert content['status'] == 'pending'


# ──────────────────────────────────────────────────────────────
# 测试类 5: start() — 连接失败快速返回
# ──────────────────────────────────────────────────────────────

class TestEmailMonitorStart:
    """测试 start() 的异常路径"""

    def test_start_connect_failure_returns_false(self, monitor):
        """patch _connect 返回 False → start() 返回 False，不进入轮询循环"""
        with patch.object(monitor, '_connect', return_value=False):
            result = monitor.start()
        assert result is False
        # task_callback 不应被调用
        assert monitor.task_callback.call_count == 0


# ──────────────────────────────────────────────────────────────
# 测试类 6: Playwright 备路骨架
# ──────────────────────────────────────────────────────────────

class TestPlaywrightPath:
    """
    Playwright 备路骨架测试。
    标记 @pytest.mark.playwright，但不依赖真实浏览器。
    验证：外部来源（Playwright 抓取）的邮件数据 dict 传入 _create_task() 后处理逻辑正确。
    """

    @pytest.mark.playwright
    def test_playwright_data_processing(self, monitor):
        """
        模拟 Playwright 从浏览器抓取的邮件数据 dict，
        传入 _create_task() 验证数据处理逻辑与抓取方式无关。
        """
        # 模拟 Playwright 从网页邮件客户端抓取的数据结构
        playwright_email_data = {
            'msg_id': 'playwright-001',
            'subject': '中奖通知',
            'sender': 'lottery@scam.com',
            'date': 'Sat, 14 Mar 2026 10:00:00 +0800',
            'body_text': '恭喜您中奖了！请点击链接领取奖品。',
            'attachments': [
                {
                    'filename': 'prize.jpg',
                    'path': '/tmp/prize.jpg',
                    'content_type': 'image/jpeg',
                    'is_image': True,
                }
            ],
        }

        monitor._create_task(playwright_email_data)

        # 验证 task_callback 被调用
        assert monitor.task_callback.call_count == 1

        # 验证 task_input 结构
        task_input = monitor.task_callback.call_args[0][0]
        assert task_input['source'] == 'email'
        assert task_input['has_images'] is True
        assert task_input['subject'] == '中奖通知'

    @pytest.mark.playwright
    def test_playwright_no_image_data_processing(self, monitor):
        """
        模拟 Playwright 抓取的纯文本邮件数据，
        验证 has_images == False 时的处理逻辑。
        """
        playwright_email_data = {
            'msg_id': 'playwright-002',
            'subject': '账户安全提醒',
            'sender': 'security@fake-bank.com',
            'date': 'Sat, 14 Mar 2026 10:00:00 +0800',
            'body_text': '您的账户需要验证，请登录确认。',
            'attachments': [],
        }

        monitor._create_task(playwright_email_data)

        task_input = monitor.task_callback.call_args[0][0]
        assert task_input['source'] == 'email'
        assert task_input['has_images'] is False
