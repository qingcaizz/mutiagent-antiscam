"""
pytest 配置文件 — 注册自定义 marks
"""
import pytest


def pytest_configure(config):
    """注册自定义 pytest marks，避免 PytestUnknownMarkWarning"""
    config.addinivalue_line(
        "markers",
        "playwright: 标记 Playwright 备路测试（可在无浏览器环境跳过）"
    )
