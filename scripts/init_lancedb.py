"""
LanceDB 案例库初始化脚本——从 sample-cases.json 导入所有案例。

Usage:
    python scripts/init_lancedb.py

    或在代码中调用：
    from scripts.init_lancedb import init_case_database
    count = init_case_database()
"""
import json
import sys
from pathlib import Path


def init_case_database(
    db_path: str = "cases/lancedb",
    cases_path: str = "cases/sample-cases.json",
) -> int:
    """
    从 JSON 文件初始化 LanceDB 案例库。

    幂等：若案例已存在（count > 0）则跳过重复插入，输出跳过信息。

    Args:
        db_path: LanceDB 存储路径（支持相对或绝对路径）。
        cases_path: sample-cases.json 路径。

    Returns:
        案例总数（不含占位记录）。

    Raises:
        FileNotFoundError: 若 cases_path 指定的文件不存在。
    """
    cases_file = Path(cases_path)
    if not cases_file.exists():
        raise FileNotFoundError(f"案例文件不存在: {cases_path}")

    # 导入放在函数内部，避免 import 时触发模型加载（加速测试收集）
    from utils.lancedb_client import LanceDBClient

    client = LanceDBClient(db_path=db_path)
    client.init_schema()

    current_count = client.count()
    if current_count > 0:
        print(f"案例库已存在，共 {current_count} 条记录，跳过初始化")
        return current_count

    with open(cases_file, encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        client.add_case(case)

    total = client.count()
    print(f"案例库初始化成功，共 {total} 条记录")
    return total


if __name__ == "__main__":
    count = init_case_database()
    sys.exit(0 if count > 0 else 1)
