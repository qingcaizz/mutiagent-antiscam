"""
LanceDB 初始化脚本的 TDD 测试套件 (01-02 Task 2 RED)
测试 scripts/init_lancedb.py 中的 init_case_database()
"""
import pytest


def test_init_loads_all_sample_cases(tmp_path):
    """init_case_database() 从 sample-cases.json 加载全部 8 条案例，返回 8"""
    from scripts.init_lancedb import init_case_database

    count = init_case_database(
        db_path=str(tmp_path / "lancedb"),
        cases_path="cases/sample-cases.json",
    )
    assert count == 8, f"期望 8 条案例，实际得到 {count} 条"


def test_output_contains_success_message(tmp_path, capsys):
    """init_case_database() 成功后输出包含'案例库初始化成功'和'8'字样"""
    from scripts.init_lancedb import init_case_database

    init_case_database(
        db_path=str(tmp_path / "lancedb"),
        cases_path="cases/sample-cases.json",
    )

    captured = capsys.readouterr()
    assert "案例库初始化成功" in captured.out, (
        f"输出中未找到'案例库初始化成功'，实际输出: {captured.out!r}"
    )
    assert "8" in captured.out, (
        f"输出中未找到案例数量'8'，实际输出: {captured.out!r}"
    )


def test_idempotent_init(tmp_path, capsys):
    """对同一 db_path 调用两次 init_case_database()，第二次不重复插入，返回仍为 8"""
    from scripts.init_lancedb import init_case_database

    db_path = str(tmp_path / "lancedb")
    cases_path = "cases/sample-cases.json"

    # 第一次初始化
    count_first = init_case_database(db_path=db_path, cases_path=cases_path)
    assert count_first == 8

    # 清除第一次的输出
    capsys.readouterr()

    # 第二次初始化（幂等性）
    count_second = init_case_database(db_path=db_path, cases_path=cases_path)
    assert count_second == 8, f"第二次调用应返回 8，而非 {count_second}（重复插入）"

    captured = capsys.readouterr()
    assert "已存在" in captured.out or "跳过" in captured.out, (
        f"第二次调用应输出'已存在'或'跳过'，实际输出: {captured.out!r}"
    )


def test_missing_cases_file_raises(tmp_path):
    """cases_path 指向不存在的文件时，抛出 FileNotFoundError"""
    from scripts.init_lancedb import init_case_database

    with pytest.raises(FileNotFoundError):
        init_case_database(
            db_path=str(tmp_path / "lancedb"),
            cases_path="cases/nonexistent-file.json",
        )
