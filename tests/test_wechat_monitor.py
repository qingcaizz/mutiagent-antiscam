"""
WeChat 文件监控器 TDD 测试套件

覆盖：
- MONITOR-01: 文件类型过滤（只处理支持的扩展名）
- MONITOR-03: 去重防止重复触发

测试策略：
- 单元测试：mock task_callback + mock logger，直接调用 on_created
- 集成测试：真实 watchdog Observer + tmp_path（Windows-only）
"""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from watchdog.events import FileCreatedEvent
from monitor.wechat_monitor import WeChatFileHandler, WeChatMonitor


# ──────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────

def make_event(file_path: Path, is_directory: bool = False) -> FileCreatedEvent:
    """构造 FileCreatedEvent"""
    event = FileCreatedEvent(str(file_path))
    # watchdog FileCreatedEvent.is_directory 是属性，需要直接赋值
    object.__setattr__(event, 'is_directory', is_directory)
    return event


def make_handler(tmp_path: Path) -> WeChatFileHandler:
    """创建带 MagicMock callback 的 handler，pipeline_dir 指向 tmp_path"""
    callback = MagicMock()
    pipeline_dir = tmp_path / ".pipeline" / "tasks"
    handler = WeChatFileHandler(
        task_callback=callback,
        pipeline_dir=str(pipeline_dir)
    )
    return handler


# ──────────────────────────────────────────────────────────────
# 单元测试组：WeChatFileHandler 行为
# ──────────────────────────────────────────────────────────────

class TestWeChatFileHandlerUnit:
    """WeChatFileHandler 单元测试，mock callback 和 logger"""

    def test_image_extensions_trigger_callback(self, tmp_path):
        """支持的图片扩展名 .jpg/.png/.gif 触发 callback（MONITOR-01）"""
        for ext in ['.jpg', '.png', '.gif']:
            # 每次用独立的 handler 避免去重干扰
            handler = make_handler(tmp_path)
            callback = handler.task_callback

            # 创建真实文件（on_created 内部会检查 file_path.exists()）
            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(b"fake-image-content")

            event = make_event(test_file)
            handler.on_created(event)

            assert callback.call_count == 1, f"{ext} 应触发 callback，但 call_count={callback.call_count}"

    def test_image_bmp_webp_trigger_callback(self, tmp_path):
        """支持的图片扩展名 .bmp/.webp 触发 callback"""
        for ext in ['.bmp', '.webp']:
            handler = make_handler(tmp_path)
            callback = handler.task_callback

            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(b"fake-image-content")

            event = make_event(test_file)
            handler.on_created(event)

            assert callback.call_count == 1, f"{ext} 应触发 callback"

    def test_doc_extensions_trigger_callback(self, tmp_path):
        """支持的文档扩展名 .pdf/.doc/.docx/.txt/.xlsx 触发 callback（MONITOR-01）"""
        for ext in ['.pdf', '.doc', '.docx', '.txt', '.xlsx']:
            handler = make_handler(tmp_path)
            callback = handler.task_callback

            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(b"fake-doc-content")

            event = make_event(test_file)
            handler.on_created(event)

            assert callback.call_count == 1, f"{ext} 应触发 callback"

    def test_unsupported_extension_no_callback(self, tmp_path):
        """不支持的扩展名 .exe/.mp4/.zip → callback 不被调用（MONITOR-01）"""
        for ext in ['.exe', '.mp4', '.zip']:
            handler = make_handler(tmp_path)
            callback = handler.task_callback

            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(b"binary-content")

            event = make_event(test_file)
            handler.on_created(event)

            assert callback.call_count == 0, f"{ext} 不应触发 callback，但 call_count={callback.call_count}"

    def test_directory_event_ignored(self, tmp_path):
        """event.is_directory=True → callback 不被调用"""
        handler = make_handler(tmp_path)
        callback = handler.task_callback

        # 创建目录事件，路径随便（不需要真实文件，因为 is_directory 检查在前）
        test_dir = tmp_path / "subdir"
        test_dir.mkdir()
        event = make_event(test_dir, is_directory=True)
        handler.on_created(event)

        assert callback.call_count == 0, "目录事件不应触发 callback"

    def test_dedup_same_path_callback_once(self, tmp_path):
        """同一路径连续调用 on_created 两次 → callback 仅被调用 1 次（MONITOR-03）"""
        handler = make_handler(tmp_path)
        callback = handler.task_callback

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake-image-content")

        event = make_event(test_file)
        # 第一次调用
        handler.on_created(event)
        # 第二次调用（相同路径，_processed_files 已记录）
        handler.on_created(event)

        assert callback.call_count == 1, (
            f"同一路径两次触发，callback 应只调用 1 次，但 call_count={callback.call_count}"
        )

    def test_logger_info_on_detection(self, tmp_path):
        """成功处理后 logger.info 被调用，消息包含 '检测到新文件'"""
        handler = make_handler(tmp_path)

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake-image-content")

        event = make_event(test_file)

        with patch('monitor.wechat_monitor.logger') as mock_logger:
            handler.on_created(event)

        # 检查 logger.info 至少有一次调用包含 '检测到新文件'
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        detection_calls = [c for c in info_calls if '检测到新文件' in c]
        assert len(detection_calls) >= 1, (
            f"logger.info 应包含 '检测到新文件'，实际调用: {info_calls}"
        )

    def test_callback_exception_logs_error(self, tmp_path):
        """callback 抛出异常 → logger.error 被调用，含 '任务触发失败'"""
        # 创建抛出异常的 callback
        bad_callback = MagicMock(side_effect=RuntimeError("test error"))
        pipeline_dir = tmp_path / ".pipeline" / "tasks"
        handler = WeChatFileHandler(
            task_callback=bad_callback,
            pipeline_dir=str(pipeline_dir)
        )

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake-image-content")

        event = make_event(test_file)

        with patch('monitor.wechat_monitor.logger') as mock_logger:
            handler.on_created(event)  # 不应抛出，内部 try/except

        # 检查 logger.error 被调用，消息含 '任务触发失败'
        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        failure_calls = [c for c in error_calls if '任务触发失败' in c]
        assert len(failure_calls) >= 1, (
            f"logger.error 应包含 '任务触发失败'，实际调用: {error_calls}"
        )

    def test_empty_file_not_processed(self, tmp_path):
        """文件大小为 0 → callback 不被调用（on_created 内有 st_size == 0 检查）"""
        handler = make_handler(tmp_path)
        callback = handler.task_callback

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"")  # 空文件

        event = make_event(test_file)
        handler.on_created(event)

        assert callback.call_count == 0, "空文件不应触发 callback"

    def test_nonexistent_file_not_processed(self, tmp_path):
        """文件不存在 → callback 不被调用"""
        handler = make_handler(tmp_path)
        callback = handler.task_callback

        # 构造不存在的文件路径
        nonexistent = tmp_path / "ghost.jpg"
        event = make_event(nonexistent)
        handler.on_created(event)

        assert callback.call_count == 0, "不存在的文件不应触发 callback"


# ──────────────────────────────────────────────────────────────
# WeChatMonitor 单元测试
# ──────────────────────────────────────────────────────────────

class TestWeChatMonitorUnit:
    """WeChatMonitor 单元测试，mock Observer"""

    def test_start_no_dirs_returns_false(self, tmp_path):
        """所有 watch_dirs 不存在 → start() 返回 False（MONITOR-01）"""
        callback = MagicMock()
        # 使用不存在的路径
        nonexistent_path = tmp_path / "nonexistent" / "WeChat"

        with patch('monitor.wechat_monitor.Observer'):
            monitor = WeChatMonitor(
                wechat_path=str(nonexistent_path),
                task_callback=callback
            )
            result = monitor.start()

        assert result is False, "所有目录不存在时 start() 应返回 False"

    def test_start_no_dirs_logs_error(self, tmp_path):
        """所有 watch_dirs 不存在 → logger.error 被调用"""
        callback = MagicMock()
        nonexistent_path = tmp_path / "nonexistent" / "WeChat"

        with patch('monitor.wechat_monitor.Observer'), \
             patch('monitor.wechat_monitor.logger') as mock_logger:
            monitor = WeChatMonitor(
                wechat_path=str(nonexistent_path),
                task_callback=callback
            )
            monitor.start()

        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert len(error_calls) >= 1, "无可用目录时应调用 logger.error"

    def test_start_with_existing_dir_returns_true(self, tmp_path):
        """至少一个 watch_dirs 存在 → start() 返回 True，observer.start() 被调用

        注意：WeChatMonitor.__init__ 中直接调用 Observer()，因此需要在实例化前 patch，
        并通过 monitor.observer 属性引用 mock 实例。
        """
        callback = MagicMock()
        # 创建 Image 子目录（WeChatMonitor 监控 wechat_path/Image, /File, /Fav）
        (tmp_path / "Image").mkdir()

        with patch('monitor.wechat_monitor.Observer') as MockObserver:
            mock_observer_instance = MockObserver.return_value
            mock_observer_instance.join = MagicMock()
            monitor = WeChatMonitor(
                wechat_path=str(tmp_path),
                task_callback=callback
            )
            result = monitor.start()

        assert result is True, "有可用目录时 start() 应返回 True"
        mock_observer_instance.start.assert_called_once()

    def test_stop_sets_not_running(self, tmp_path):
        """start() 后调用 stop() → is_running() 为 False

        同样需要在实例化前 patch Observer。
        """
        callback = MagicMock()
        (tmp_path / "Image").mkdir()

        with patch('monitor.wechat_monitor.Observer') as MockObserver:
            mock_observer_instance = MockObserver.return_value
            mock_observer_instance.join = MagicMock()
            monitor = WeChatMonitor(
                wechat_path=str(tmp_path),
                task_callback=callback
            )
            monitor.start()
            assert monitor.is_running() is True

            monitor.stop()

        assert monitor.is_running() is False, "stop() 后 is_running() 应为 False"

    def test_is_running_initially_false(self, tmp_path):
        """未调用 start() 时 is_running() 返回 False"""
        callback = MagicMock()
        with patch('monitor.wechat_monitor.Observer'):
            monitor = WeChatMonitor(
                wechat_path=str(tmp_path),
                task_callback=callback
            )
        assert monitor.is_running() is False


# ──────────────────────────────────────────────────────────────
# 集成测试组：真实 watchdog Observer + tmp_path（Windows-only）
# ──────────────────────────────────────────────────────────────

@pytest.mark.skipif(sys.platform != 'win32', reason="WeChat monitor is Windows-only")
class TestWeChatMonitorIntegration:
    """集成测试：真实 watchdog + 文件系统事件，Windows only"""

    def _wait_for_callback(self, callback: MagicMock, expected_count: int = 1, timeout: float = 5.0) -> bool:
        """轮询等待 callback 被调用 expected_count 次，最多等 timeout 秒"""
        for _ in range(int(timeout / 0.1)):
            if callback.call_count >= expected_count:
                return True
            time.sleep(0.1)
        return False

    def test_new_image_triggers_callback_within_5s(self, tmp_path):
        """向监控目录写入 .jpg 文件 → 5 秒内 task_callback 被调用（MONITOR-01）"""
        callback = MagicMock()
        image_dir = tmp_path / "Image"
        image_dir.mkdir()

        monitor = WeChatMonitor(
            wechat_path=str(tmp_path),
            task_callback=callback
        )

        started = monitor.start()
        assert started is True, "监控启动应成功"

        try:
            # 写入真实图片文件（非空）
            test_file = image_dir / "test.jpg"
            test_file.write_bytes(b"fake-image-content-for-integration-test")

            # 等待 watchdog 检测到文件创建事件（最多 5 秒）
            triggered = self._wait_for_callback(callback, expected_count=1, timeout=5.0)

            assert triggered, (
                f"写入 .jpg 文件后 5 秒内 callback 未被调用，call_count={callback.call_count}"
            )
            assert callback.call_count >= 1
        finally:
            monitor.stop()

    def test_unsupported_extension_no_callback_integration(self, tmp_path):
        """向监控目录写入 .exe 文件 → callback 不被调用"""
        callback = MagicMock()
        image_dir = tmp_path / "Image"
        image_dir.mkdir()

        monitor = WeChatMonitor(
            wechat_path=str(tmp_path),
            task_callback=callback
        )

        started = monitor.start()
        assert started is True

        try:
            test_file = image_dir / "malware.exe"
            test_file.write_bytes(b"MZ-binary-content")

            # 等待 2 秒，确认 callback 不被调用
            time.sleep(2.0)
            assert callback.call_count == 0, (
                f".exe 文件不应触发 callback，但 call_count={callback.call_count}"
            )
        finally:
            monitor.stop()

    def test_duplicate_file_no_duplicate_callback(self, tmp_path):
        """同一文件路径触发两次 on_created → callback 仅被调用 1 次（MONITOR-03）

        通过直接操作 handler._processed_files 来模拟去重场景
        （集成测试中 watchdog 对同一路径通常只发一次 created 事件）
        """
        callback = MagicMock()
        image_dir = tmp_path / "Image"
        image_dir.mkdir()

        # 使用单元测试方式验证去重（集成层面的去重通过单元测试已覆盖）
        pipeline_dir = tmp_path / ".pipeline" / "tasks"
        handler = WeChatFileHandler(
            task_callback=callback,
            pipeline_dir=str(pipeline_dir)
        )

        test_file = image_dir / "test.jpg"
        test_file.write_bytes(b"fake-image-content")

        event = make_event(test_file)
        handler.on_created(event)  # 第一次
        handler.on_created(event)  # 第二次（相同路径）

        # callback 仅被调用 1 次（_processed_files 去重）
        assert handler.task_callback.call_count == 1, (
            f"去重机制应使 callback 只调用 1 次，实际 call_count={handler.task_callback.call_count}"
        )
