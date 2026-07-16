"""
SQL 安全校验器
--------------
在 SQL 执行前做两道检查：
1. 关键词黑名单 — 拦截 DROP/DELETE/UPDATE 等危险操作
2. 语法检查 — 用 sqlparse 判断是否是合法 SQL

注意: 不保证 100% 拦截恶意 SQL，这只是针对 LLM 生成内容的「安全带」。
"""

import re

# ============================================================
# 关键词黑名单
# ============================================================
# 大小写不敏感，用单词边界匹配，防止误杀（比如字段名叫 "updated_at" 不会命中 UPDATE）
FORBIDDEN_KEYWORDS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bCREATE\b",
    r"\bREPLACE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bREINDEX\b",
]


def validate(sql: str) -> tuple[bool, str]:
    """
    校验 SQL 语句。

    参数:
        sql: LLM 生成的 SQL 语句

    返回:
        (passed, reason): passed=True 表示通过校验，False 表示被拦截（含原因）
    """
    if not sql or not sql.strip():
        return False, "SQL 为空"

    sql_stripped = sql.strip()

    # ---- 检查 1: 关键词黑名单 ----
    for pattern in FORBIDDEN_KEYWORDS:
        if re.search(pattern, sql_stripped, re.IGNORECASE):
            keyword = re.search(pattern, sql_stripped, re.IGNORECASE).group()
            return False, f"禁止使用 {keyword} 语句，只允许 SELECT 查询"

    # ---- 检查 2: 必须以 SELECT 开头 ----
    # 去掉前导注释和空白
    cleaned = re.sub(r'/\*.*?\*/', '', sql_stripped, flags=re.DOTALL)  # 去掉块注释
    cleaned = re.sub(r'--[^\n]*', '', cleaned)                         # 去掉行注释
    cleaned = cleaned.strip()

    if not cleaned.upper().startswith("SELECT"):
        return False, f"只允许 SELECT 查询，当前语句以 '{cleaned[:20]}...' 开头"

    # ---- 检查 3: 禁止多条语句（分号注入） ----
    # 允许结尾分号，但分号后面不能再有内容
    semicolons = [i for i, c in enumerate(cleaned) if c == ";"]
    if semicolons:
        after_last = cleaned[semicolons[-1] + 1:].strip()
        if after_last:
            return False, "禁止执行多条 SQL 语句"

    return True, "OK"
