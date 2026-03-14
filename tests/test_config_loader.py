"""
配置加载模块的 TDD 测试套件 (01-02 Task 1 RED)
测试 config/load_config.py 中的 load_config() 和 AppConfig
"""
import os
from pathlib import Path

import pytest


def test_load_config_returns_required_keys(tmp_path):
    """load_config() 返回包含所有必需键的 AppConfig 对象"""
    # 在临时目录创建包含所有必需键的 .env 文件
    env_file = tmp_path / ".env"
    log_dir = tmp_path / "logs"
    env_file.write_text(
        f"ANTHROPIC_API_KEY=test_key_12345\n"
        f"LOG_LEVEL=DEBUG\n"
        f"LOG_DIR={log_dir}\n"
        f"LANCEDB_PATH=cases/lancedb\n"
        f"EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2\n"
        f"RAG_TOP_K=5\n"
        f"RAG_SIMILARITY_THRESHOLD=0.65\n",
        encoding="utf-8",
    )

    from config.load_config import load_config

    config = load_config(env_path=str(env_file))

    assert config.anthropic_api_key == "test_key_12345"
    assert config.log_level == "DEBUG"
    assert config.lancedb_path == "cases/lancedb"
    assert config.embedding_model != ""
    assert config.rag_top_k == 5
    assert config.rag_similarity_threshold == pytest.approx(0.65)


def test_missing_anthropic_key_raises_error(tmp_path):
    """缺少 ANTHROPIC_API_KEY 时 load_config() 抛出 ValueError，错误信息包含 'ANTHROPIC_API_KEY'"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LOG_LEVEL=INFO\n"
        "LOG_DIR=logs/\n"
        "LANCEDB_PATH=cases/lancedb\n",
        encoding="utf-8",
    )

    # 确保环境变量中也没有该 key
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        from config.load_config import load_config

        with pytest.raises((ValueError, KeyError)) as exc_info:
            load_config(env_path=str(env_file))

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)
    finally:
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original


def test_logs_dir_auto_created(tmp_path):
    """load_config() 自动创建 LOG_DIR 中指定的目录"""
    log_dir = tmp_path / "auto_created_logs"
    assert not log_dir.exists(), "前置条件：目录尚不存在"

    env_file = tmp_path / ".env"
    env_file.write_text(
        f"ANTHROPIC_API_KEY=test_key_for_logs\n"
        f"LOG_DIR={log_dir}\n",
        encoding="utf-8",
    )

    from config.load_config import load_config

    config = load_config(env_path=str(env_file))

    assert Path(config.log_dir).exists(), f"LOG_DIR '{config.log_dir}' 应被自动创建"


def test_config_reads_env_example_keys(tmp_path):
    """使用 .env.example 中的键格式，验证所有键均可被正确加载"""
    # 读取真实的 .env.example 模板，替换真实 API key 为测试 key
    env_example = Path("config/.env.example")
    if not env_example.exists():
        pytest.skip("config/.env.example 不存在")

    content = env_example.read_text(encoding="utf-8")
    # 替换占位符为可测试的值
    content = content.replace("your_anthropic_api_key_here", "test_key_from_example")

    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")

    from config.load_config import load_config

    config = load_config(env_path=str(env_file))

    assert config.anthropic_api_key == "test_key_from_example"
    assert config.log_level in ("DEBUG", "INFO", "WARNING", "ERROR")
    assert config.lancedb_path != ""


def test_monitor_dedup_infrastructure_exists():
    """
    MONITOR-03 基础设施验证：
    monitor/wechat_monitor.py 中必须存在去重机制代码
    （存在性验证，运行时行为在 Phase 2 验证）
    """
    source_path = Path("monitor/wechat_monitor.py")
    assert source_path.exists(), "monitor/wechat_monitor.py 文件不存在"

    source = source_path.read_text(encoding="utf-8")
    assert "_processed_files" in source or "cooldown" in source, (
        "monitor/wechat_monitor.py 中未找到去重机制（_processed_files 或 cooldown）"
    )
    assert "logs" in source or "logger" in source, (
        "monitor/wechat_monitor.py 中未找到日志记录逻辑"
    )
