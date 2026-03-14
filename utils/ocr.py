"""
PaddleOCR 封装工具
- extract_text: 从图片提取纯文字
- extract_text_with_regions: 提取文字并携带位置信息
- 懒加载：首次调用时才初始化 OCR 实例
- 错误处理：图片不存在或 OCR 失败时返回空字符串/列表并记录日志
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

# 全局懒加载实例
_ocr_instance: Optional[object] = None


def _get_ocr():
    """懒加载 PaddleOCR 实例（首次调用时初始化）。"""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR  # type: ignore

            logger.info("[OCR] 正在初始化 PaddleOCR（首次调用）...")
            _ocr_instance = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            logger.info("[OCR] PaddleOCR 初始化完成")
        except ImportError:
            logger.error("[OCR] paddleocr 未安装，请执行: pip install paddleocr")
            raise
        except Exception as exc:
            logger.error(f"[OCR] PaddleOCR 初始化失败: {exc}")
            raise
    return _ocr_instance


def extract_text(image_path: str) -> str:
    """
    从图片提取全部文字，拼接为单一字符串。

    Args:
        image_path: 图片文件路径

    Returns:
        提取到的文字字符串；图片不存在或 OCR 失败时返回空字符串。
    """
    path = Path(image_path)
    if not path.exists():
        logger.warning(f"[OCR] 图片文件不存在: {image_path}")
        return ""

    try:
        ocr = _get_ocr()
        result = ocr.ocr(str(path), cls=True)

        if not result or result == [None]:
            logger.debug(f"[OCR] 未识别到文字: {image_path}")
            return ""

        lines: list[str] = []
        for page in result:
            if page is None:
                continue
            for line in page:
                # line 结构: [[坐标], (文字, 置信度)]
                if line and len(line) >= 2:
                    text_info = line[1]
                    if text_info and len(text_info) >= 1:
                        lines.append(text_info[0])

        extracted = "\n".join(lines)
        logger.debug(f"[OCR] 提取完成: {len(extracted)} 字符，来自 {image_path}")
        return extracted

    except Exception as exc:
        logger.error(f"[OCR] 提取失败 ({image_path}): {exc}")
        return ""


# agent1_preprocessor.py 中使用的别名
extract_text_from_image = extract_text


def extract_text_with_regions(image_path: str) -> list[dict]:
    """
    从图片提取文字并携带位置信息。

    Args:
        image_path: 图片文件路径

    Returns:
        列表，每个元素为::

            {
                "text": "识别到的文字",
                "confidence": 0.98,
                "box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            }

        图片不存在或 OCR 失败时返回空列表。
    """
    path = Path(image_path)
    if not path.exists():
        logger.warning(f"[OCR] 图片文件不存在: {image_path}")
        return []

    try:
        ocr = _get_ocr()
        result = ocr.ocr(str(path), cls=True)

        if not result or result == [None]:
            logger.debug(f"[OCR] 未识别到文字: {image_path}")
            return []

        regions: list[dict] = []
        for page in result:
            if page is None:
                continue
            for line in page:
                # line 结构: [[坐标], (文字, 置信度)]
                if line and len(line) >= 2:
                    box = line[0]
                    text_info = line[1]
                    if text_info and len(text_info) >= 2:
                        regions.append(
                            {
                                "text": text_info[0],
                                "confidence": float(text_info[1]),
                                "box": box,
                            }
                        )

        logger.debug(
            f"[OCR] 带位置提取完成: {len(regions)} 区域，来自 {image_path}"
        )
        return regions

    except Exception as exc:
        logger.error(f"[OCR] 带位置提取失败 ({image_path}): {exc}")
        return []
