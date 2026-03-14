"""
核心包 import 验证测试套件
验证所有核心依赖可正常导入，并确认 config/.env.example 完整性。
"""
import pytest
from pathlib import Path


def test_import_anthropic():
    """验证 anthropic 包可导入且包含 Anthropic 类"""
    import anthropic
    assert hasattr(anthropic, 'Anthropic'), "anthropic 模块应包含 Anthropic 类"


def test_import_lancedb():
    """验证 lancedb 包可导入"""
    import lancedb
    assert lancedb is not None, "lancedb 模块应可访问"


def test_import_watchdog():
    """验证 watchdog 包可导入"""
    import watchdog.observers
    assert watchdog.observers is not None, "watchdog.observers 模块应可访问"


def test_import_paddleocr():
    """验证 paddleocr 包可导入且包含 PaddleOCR 类"""
    try:
        import paddleocr
        assert hasattr(paddleocr, 'PaddleOCR'), "paddleocr 模块应包含 PaddleOCR 类"
    except ImportError as e:
        pytest.skip(f"paddleocr 在 Windows 环境安装可能需要额外 C++ 依赖: {e}")


def test_import_sentence_transformers():
    """验证 sentence_transformers 包可导入且包含 SentenceTransformer 类"""
    from sentence_transformers import SentenceTransformer
    assert SentenceTransformer is not None, "SentenceTransformer 类应可访问"


def test_import_python_dotenv():
    """验证 python-dotenv 包可导入且 load_dotenv 函数可调用"""
    from dotenv import load_dotenv
    assert callable(load_dotenv), "load_dotenv 应为可调用函数"


def test_import_loguru():
    """验证 loguru 包可导入且 logger 存在"""
    from loguru import logger
    assert logger is not None, "loguru logger 应存在"


def test_no_agentscope():
    """验证 agentscope 未安装（项目决策：不使用 AgentScope，改用 anthropic SDK 直接实现）"""
    with pytest.raises(ImportError):
        import agentscope


def test_env_example_exists_and_has_required_keys():
    """验证 config/.env.example 文件存在且包含所有必需配置键"""
    env_example = Path("config/.env.example")
    assert env_example.exists(), "config/.env.example 不存在，OSS-03 要求提供示例配置文件"
    content = env_example.read_text(encoding="utf-8")
    required_keys = [
        "ANTHROPIC_API_KEY",
        "LOG_LEVEL",
        "LOG_DIR",
        "LANCEDB_PATH",
        "FEISHU_WEBHOOK_URL",
    ]
    for key in required_keys:
        assert key in content, f"config/.env.example 缺少必需键: {key}"
