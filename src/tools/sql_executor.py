"""
SQL 执行器
----------
连接 SQLite 数据库，执行 SQL 语句，返回结构化的结果。
只负责「执行」这件事，不做任何校验或分析。
"""

import sqlite3
from typing import Any
from dataclasses import dataclass


@dataclass
class QueryResult:
    """查询结果的统一封装。"""
    success: bool
    columns: list[str]          # 列名列表
    rows: list[tuple[Any, ...]] # 数据行列表
    row_count: int
    error: str | None = None


def execute(database_path: str, sql: str) -> QueryResult:
    """
    执行一条 SQL 语句，返回 QueryResult。

    参数:
        database_path: SQLite 数据库文件的绝对路径
        sql: 要执行的 SQL 语句（只应执行 SELECT）

    返回:
        QueryResult: 包含列名、数据行、行数，或错误信息
    """
    try:
        conn = sqlite3.connect(database_path)
        conn.row_factory = sqlite3.Row  # 让结果可以用列名访问
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()

        return QueryResult(
            success=True,
            columns=columns,
            rows=[tuple(row) for row in rows],
            row_count=len(rows),
        )

    except sqlite3.Error as e:
        return QueryResult(
            success=False,
            columns=[],
            rows=[],
            row_count=0,
            error=str(e),
        )


def get_table_schema(database_path: str, table_name: str) -> str:
    """
    获取一张表的 CREATE TABLE 语句（即表结构）。

    用于拼进 LLM prompt 里，让模型知道有哪些表和字段。
    """
    conn = sqlite3.connect(database_path)
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""


def list_tables(database_path: str) -> list[str]:
    """
    列出数据库中所有用户表的名字。
    """
    conn = sqlite3.connect(database_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables
