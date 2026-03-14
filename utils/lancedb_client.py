"""
LanceDB 向量库客户端
- 存储和检索诈骗案例
- 使用 sentence_transformers 生成多语言 embedding
- 支持语义相似度搜索
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# 数据库默认路径
_DEFAULT_DB_PATH = "D:/个人项目/mutiagent_trea/cases/lancedb"
# embedding 模型
_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
# LanceDB 表名
_TABLE_NAME = "scam_cases"


class LanceDBClient:
    """
    LanceDB 向量库客户端，封装诈骗案例的存储与语义检索。
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        self._db: Optional[Any] = None
        self._table: Optional[Any] = None
        self._embed_model: Optional[Any] = None

        logger.info(f"[LanceDB] 客户端创建，数据库路径: {self.db_path}")

    # ------------------------------------------------------------------
    # 懒加载内部组件
    # ------------------------------------------------------------------

    def _get_db(self):
        """懒加载 LanceDB 连接。"""
        if self._db is None:
            try:
                import lancedb  # type: ignore

                self._db = lancedb.connect(str(self.db_path))
                logger.info("[LanceDB] 数据库连接成功")
            except ImportError:
                logger.error("[LanceDB] lancedb 未安装，请执行: pip install lancedb")
                raise
        return self._db

    def _get_embed_model(self):
        """懒加载 sentence_transformers 模型。"""
        if self._embed_model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                logger.info(f"[LanceDB] 加载 embedding 模型: {_EMBEDDING_MODEL}")
                self._embed_model = SentenceTransformer(_EMBEDDING_MODEL)
                logger.info("[LanceDB] embedding 模型加载完成")
            except ImportError:
                logger.error(
                    "[LanceDB] sentence_transformers 未安装，"
                    "请执行: pip install sentence-transformers"
                )
                raise
        return self._embed_model

    def _embed(self, text: str) -> list[float]:
        """将文本转换为 embedding 向量。"""
        model = self._get_embed_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    # ------------------------------------------------------------------
    # 表结构初始化
    # ------------------------------------------------------------------

    def init_schema(self) -> None:
        """
        初始化 LanceDB 表结构。
        若表已存在则跳过，否则创建含示例数据的空表。
        """
        db = self._get_db()
        existing_tables = db.table_names()

        if _TABLE_NAME in existing_tables:
            logger.info(f"[LanceDB] 表 '{_TABLE_NAME}' 已存在，跳过初始化")
            self._table = db.open_table(_TABLE_NAME)
            return

        # 用一条占位数据建表（LanceDB 建表需要至少一条数据以推断 schema）
        # features 必须包含至少一个字符串，否则 Arrow 推断为 null 类型，
        # 导致后续插入真实 features 时出现类型不匹配错误
        placeholder_vector = self._embed("初始化占位数据")
        placeholder = {
            "id": "init-placeholder",
            "type": "init",
            "text": "初始化占位数据",
            "label": "init",
            "risk_level": "低",
            "features": ["placeholder"],
            "source": "system",
            "vector": placeholder_vector,
        }

        self._table = db.create_table(_TABLE_NAME, data=[placeholder])
        logger.info(f"[LanceDB] 表 '{_TABLE_NAME}' 创建成功")

    def _get_table(self):
        """获取表实例，若未初始化则自动调用 init_schema。"""
        if self._table is None:
            db = self._get_db()
            existing_tables = db.table_names()
            if _TABLE_NAME in existing_tables:
                self._table = db.open_table(_TABLE_NAME)
            else:
                self.init_schema()
        return self._table

    # ------------------------------------------------------------------
    # 数据操作接口
    # ------------------------------------------------------------------

    def add_case(self, case: dict) -> str:
        """
        添加诈骗案例（自动生成 embedding）。

        Args:
            case: 案例字典，需包含 "text" 字段，其余字段可选::

                {
                    "id": "case-001",        # 可选，自动生成
                    "type": "冒充公检法",
                    "text": "...",           # 必填，用于生成 embedding
                    "label": "scam",
                    "risk_level": "极高",
                    "features": [...],
                    "source": "sample"
                }

        Returns:
            案例 ID 字符串。
        """
        if not case.get("text"):
            raise ValueError("[LanceDB] add_case: 'text' 字段不能为空")

        case_id = case.get("id") or str(uuid.uuid4())
        vector = self._embed(case["text"])

        record = {
            "id": case_id,
            "type": case.get("type", "unknown"),
            "text": case["text"],
            "label": case.get("label", "unknown"),
            "risk_level": case.get("risk_level", "未知"),
            "features": case.get("features", []),
            "source": case.get("source", "manual"),
            "vector": vector,
        }

        table = self._get_table()
        table.add([record])
        logger.info(f"[LanceDB] 案例已添加: {case_id} (type={record['type']})")
        return case_id

    def search_similar(self, text: str, top_k: int = 5) -> list[dict]:
        """
        语义搜索 TOP-K 最相似案例。

        Args:
            text: 查询文本
            top_k: 返回案例数量上限

        Returns:
            相似案例列表，每个元素为原始案例字典加 "_distance" 字段。
            搜索失败时返回空列表。
        """
        if not text:
            logger.warning("[LanceDB] search_similar: 查询文本为空")
            return []

        try:
            query_vector = self._embed(text)
            table = self._get_table()

            results = (
                table.search(query_vector)
                .limit(top_k)
                .to_list()
            )

            # 过滤掉初始化占位数据
            filtered = [r for r in results if r.get("id") != "init-placeholder"]

            logger.debug(
                f"[LanceDB] 检索完成: 查询长度={len(text)}，命中={len(filtered)} 条"
            )
            return filtered

        except Exception as exc:
            logger.error(f"[LanceDB] 检索失败: {exc}")
            return []

    def delete_case(self, case_id: str) -> bool:
        """
        根据 ID 删除案例。

        Args:
            case_id: 案例 ID

        Returns:
            成功返回 True，失败返回 False。
        """
        try:
            table = self._get_table()
            table.delete(f"id = '{case_id}'")
            logger.info(f"[LanceDB] 案例已删除: {case_id}")
            return True
        except Exception as exc:
            logger.error(f"[LanceDB] 删除失败 ({case_id}): {exc}")
            return False

    def count(self) -> int:
        """返回表中案例总数（不含占位记录）。"""
        try:
            table = self._get_table()
            total = table.count_rows()
            return max(0, total - 1)  # 减去占位数据
        except Exception as exc:
            logger.error(f"[LanceDB] 计数失败: {exc}")
            return 0
