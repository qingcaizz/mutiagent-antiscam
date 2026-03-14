"""
配置加载模块——读取 .env 文件，验证必需变量，自动创建 logs/ 目录。

Usage:
    from config.load_config import load_config, AppConfig

    config = load_config()  # 从当前目录 .env 加载
    config = load_config(env_path="path/to/.env")  # 指定路径
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 必须存在的环境变量列表
REQUIRED_KEYS = ["ANTHROPIC_API_KEY"]


@dataclass
class AppConfig:
    """应用配置数据类，包含所有运行时所需参数。"""

    anthropic_api_key: str
    log_level: str
    log_dir: str
    lancedb_path: str
    embedding_model: str
    rag_top_k: int
    rag_similarity_threshold: float


def load_config(env_path: str | None = None) -> AppConfig:
    """
    加载 .env 配置文件，验证必需变量，自动创建 log_dir。

    Args:
        env_path: .env 文件路径，默认加载当前工作目录下的 .env。

    Returns:
        AppConfig 实例，包含所有配置项。

    Raises:
        ValueError: 若 ANTHROPIC_API_KEY 等必需变量未设置或为空。
    """
    if env_path:
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)

    # 验证必需变量
    for key in REQUIRED_KEYS:
        if not os.environ.get(key):
            raise ValueError(
                f"必需的环境变量 {key!r} 未设置，请检查 .env 文件"
            )

    # 自动创建日志目录
    log_dir = os.environ.get("LOG_DIR", "logs/")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    return AppConfig(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        log_dir=log_dir,
        lancedb_path=os.environ.get("LANCEDB_PATH", "cases/lancedb"),
        embedding_model=os.environ.get(
            "EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
        rag_top_k=int(os.environ.get("RAG_TOP_K", "5")),
        rag_similarity_threshold=float(
            os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.65")
        ),
    )
