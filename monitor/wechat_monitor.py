"""
WeChat 文件夹监控器
支持新版 xwechat 目录结构：
  - msg/attach/{联系人hash}/{日期}/Img/*.dat  → 图片（XOR 加密，由 Agent1 解密）
  - msg/file/{日期}/*                         → 文档
兼容旧版 WeChat FileStorage 结构（Image/ File/ Fav/）
"""
import os
import time
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from loguru import logger

from utils.ocr import extract_text_from_image


class WeChatFileHandler(FileSystemEventHandler):
    """处理微信新文件事件"""

    SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    SUPPORTED_DOC_EXTS = {'.pdf', '.doc', '.docx', '.txt', '.xlsx', '.xls'}
    # xwechat 新版：图片以 .dat 存储（XOR 加密），由 Agent1 负责解密
    XWECHAT_IMAGE_EXT = '.dat'

    def __init__(
        self,
        task_callback: Callable[[dict], None],
        pipeline_dir: str = ".pipeline/tasks"
    ):
        """
        Args:
            task_callback: 新任务触发回调函数
            pipeline_dir: 任务中间状态目录
        """
        self.task_callback = task_callback
        self.pipeline_dir = Path(pipeline_dir)
        self.pipeline_dir.mkdir(parents=True, exist_ok=True)

        # 防重复：记录最近处理的文件
        self._processed_files: set = set()
        self._cooldown_seconds = 2  # 同一文件 2 秒内不重复处理

    def on_created(self, event: FileCreatedEvent):
        """文件创建事件"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        ext = file_path.suffix.lower()

        # 检查是否支持的文件类型
        # xwechat 新版：Img/ 子目录下的 .dat 文件视为图片
        is_xwechat_image = (ext == self.XWECHAT_IMAGE_EXT and 'Img' in file_path.parts)
        if ext not in (self.SUPPORTED_IMAGE_EXTS | self.SUPPORTED_DOC_EXTS) and not is_xwechat_image:
            return

        # 防重复处理
        path_str = str(file_path)
        if path_str in self._processed_files:
            return
        self._processed_files.add(path_str)

        # 等待文件写入完成
        time.sleep(0.5)
        if not file_path.exists() or file_path.stat().st_size == 0:
            self._processed_files.discard(path_str)
            return

        logger.info(f"[WeChat] 检测到新文件: {file_path.name}")
        # xwechat .dat 图片统一归为 image 类型
        effective_ext = '.jpg' if (ext == self.XWECHAT_IMAGE_EXT and 'Img' in file_path.parts) else ext
        self._handle_new_file(file_path, effective_ext)

    def _handle_new_file(self, file_path: Path, ext: str):
        """处理新文件，生成分析任务"""
        task_id = f"wechat-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        file_type = "image" if ext in self.SUPPORTED_IMAGE_EXTS else "document"

        # 创建任务目录
        task_dir = self.pipeline_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        # 写入任务输入信息
        task_input = {
            "task_id": task_id,
            "source": "wechat",
            "file_type": file_type,
            "file_path": str(file_path),
            "file_name": file_path.name,
            "file_size": file_path.stat().st_size,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }

        with open(task_dir / "input.json", "w", encoding="utf-8") as f:
            json.dump(task_input, f, ensure_ascii=False, indent=2)

        logger.info(f"[WeChat] 任务创建: {task_id}")

        # 触发管线处理
        try:
            self.task_callback(task_input)
        except Exception as e:
            logger.error(f"[WeChat] 任务触发失败: {task_id} - {e}")
            self._update_task_status(task_dir, "failed", str(e))

    def _update_task_status(self, task_dir: Path, status: str, error: str = None):
        """更新任务状态"""
        status_file = task_dir / "status.json"
        status_data = {
            "status": status,
            "updated_at": datetime.now().isoformat()
        }
        if error:
            status_data["error"] = error
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)


class WeChatMonitor:
    """
    WeChat 文件夹监控主类

    监控路径：
    - Image/  → 图片触发OCR分析
    - File/   → 文档触发文本提取
    """

    def __init__(
        self,
        wechat_path: str,
        task_callback: Callable[[dict], None],
        pipeline_dir: str = ".pipeline/tasks"
    ):
        """
        Args:
            wechat_path: 微信根路径
                新版 xwechat 例: C:\\Users\\xxx\\Documents\\xwechat_files\\wxid_xxx
                旧版 WeChat  例: C:\\Users\\xxx\\Documents\\WeChat Files\\wxid_xxx\\FileStorage
            task_callback: 新任务触发回调
            pipeline_dir: 任务状态目录
        """
        self.wechat_path = Path(wechat_path)
        self.pipeline_dir = pipeline_dir
        self.task_callback = task_callback
        self.observer = Observer()
        self._running = False

        # 自动识别新版/旧版目录结构
        if (self.wechat_path / "msg").exists():
            # 新版 xwechat 结构
            self.watch_dirs = [
                self.wechat_path / "msg" / "attach",  # .dat 图片（含 Img/ 子目录）
                self.wechat_path / "msg" / "file",    # 普通文档
            ]
        else:
            # 旧版 WeChat FileStorage 结构
            self.watch_dirs = [
                self.wechat_path / "Image",
                self.wechat_path / "File",
                self.wechat_path / "Fav",
            ]

    def start(self):
        """启动监控"""
        handler = WeChatFileHandler(
            task_callback=self.task_callback,
            pipeline_dir=self.pipeline_dir
        )

        active_watch_count = 0
        for watch_dir in self.watch_dirs:
            if watch_dir.exists():
                self.observer.schedule(handler, str(watch_dir), recursive=True)
                logger.info(f"[WeChat] 监控目录: {watch_dir}")
                active_watch_count += 1
            else:
                logger.warning(f"[WeChat] 目录不存在，跳过: {watch_dir}")

        if active_watch_count == 0:
            logger.error(f"[WeChat] 未找到可监控目录，请检查路径: {self.wechat_path}")
            return False

        self.observer.start()
        self._running = True
        logger.info(f"[WeChat] 监控启动，共监控 {active_watch_count} 个目录")
        return True

    def stop(self):
        """停止监控"""
        if self._running:
            self.observer.stop()
            self.observer.join()
            self._running = False
            logger.info("[WeChat] 监控已停止")

    def is_running(self) -> bool:
        return self._running

    @staticmethod
    def get_default_wechat_path(wxid: Optional[str] = None) -> str:
        """获取默认微信路径（Windows），优先查找新版 xwechat，回退旧版 WeChat"""
        username = os.environ.get("USERNAME", "User")

        # 新版 xwechat 路径（wxid 目录以 wxid_ 开头）
        xwechat_base = Path(f"C:/Users/{username}/Documents/xwechat_files")
        if xwechat_base.exists():
            if wxid:
                candidate = xwechat_base / wxid
                if candidate.exists():
                    return str(candidate)
            wxids = [d for d in xwechat_base.iterdir() if d.is_dir() and d.name.startswith("wxid_")]
            if wxids:
                return str(wxids[0])

        # 旧版 WeChat FileStorage 路径
        old_base = Path(f"C:/Users/{username}/Documents/WeChat Files")
        if wxid:
            return str(old_base / wxid / "FileStorage")
        if old_base.exists():
            wxids = [d for d in old_base.iterdir() if d.is_dir()]
            if wxids:
                return str(wxids[0] / "FileStorage")
        return str(old_base)


# 使用示例
if __name__ == "__main__":
    from loguru import logger

    def dummy_callback(task: dict):
        logger.info(f"新任务: {task['task_id']} | {task['file_name']}")

    monitor = WeChatMonitor(
        wechat_path=WeChatMonitor.get_default_wechat_path(),
        task_callback=dummy_callback
    )

    if monitor.start():
        logger.info("按 Ctrl+C 停止监控...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            monitor.stop()
