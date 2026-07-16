"""
工具注册中心
------------
把系统中所有可用工具注册在这里，每个工具带「说明书」。
LLM 看到说明书后，自己决定：要不要调用、调哪个、传什么参数。

工具说明书格式: OpenAI Function Calling 兼容格式
"""

import json
from typing import Any

from src.core.config import DATABASE_PATH
from src.tools.sql_executor import execute, list_tables, get_table_schema


# ============================================================
# 工具定义（说明书）
# ============================================================
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": (
                "在应用商店数据库中执行一条 SQL 查询，返回结果数据。"
                "只支持 SELECT 语句。"
                "使用前你应该先了解数据库中有哪些表和字段。"
                "日期函数使用 SQLite 语法，如 date('now')、date('now', '-1 day') 等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的 SQL SELECT 语句",
                    }
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": (
                "获取数据库中指定表的完整结构（CREATE TABLE 语句），"
                "包括字段名、类型。当你需要知道表有哪些列时调用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名",
                    }
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "列出数据库中所有的表名。当你第一次接触数据库或不确定有哪些表时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ============================================================
# 工具执行分发
# ============================================================
def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """
    根据工具名和参数执行对应工具，返回结果字符串（喂给 LLM）。
    """
    if name == "execute_sql":
        sql = arguments.get("sql", "")
        result = execute(DATABASE_PATH, sql)
        if result.success:
            if result.row_count == 0:
                return "查询成功，但没有返回任何数据。"
            # 格式化为表格文本
            lines = [" | ".join(result.columns)]
            lines.append("-" * 40)
            for row in result.rows[:50]:
                lines.append(" | ".join(str(v) for v in row))
            if result.row_count > 50:
                lines.append(f"... 还有 {result.row_count - 50} 行")
            return "\n".join(lines)
        else:
            return f"SQL 执行失败: {result.error}"

    elif name == "get_table_schema":
        table_name = arguments.get("table_name", "")
        schema = get_table_schema(DATABASE_PATH, table_name)
        if schema:
            return schema
        else:
            available = list_tables(DATABASE_PATH)
            return f"表 '{table_name}' 不存在。数据库中有以下表: {', '.join(available)}"

    elif name == "list_tables":
        tables = list_tables(DATABASE_PATH)
        return f"数据库中的表: {', '.join(tables)}"

    else:
        return f"未知工具: {name}"
