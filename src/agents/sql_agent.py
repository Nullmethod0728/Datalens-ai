"""
SQL Agent — 单轮 Text-to-SQL
------------------------------
把表结构 + 用户自然语言问题拼成 prompt → 调 LLM 生成 SQL
→ 执行 SQL → 把查询结果再喂给 LLM 翻译成人话。

这是阶段一的实现，只做「一轮问答」，没有 Function Calling。
"""

import json
from openai import OpenAI

from src.core.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    MODEL_NAME,
    TEMPERATURE,
    MAX_TOKENS,
    DATABASE_PATH,
)
from src.tools.sql_executor import execute, list_tables, get_table_schema


# ============================================================
# 初始化（懒加载：只在第一次调用时创建 client，避免无 API Key 时导入失败）
# ============================================================
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    return _client


# ============================================================
# Prompt 构建
# ============================================================
def _build_schema_description() -> str:
    """把数据库所有表的结构拼成一段文字，塞进 system prompt。"""
    tables = list_tables(DATABASE_PATH)
    parts = []
    for t in tables:
        schema_sql = get_table_schema(DATABASE_PATH, t)
        parts.append(f"### 表: {t}\n```sql\n{schema_sql}\n```")
    return "\n\n".join(parts)


SYSTEM_PROMPT_TEMPLATE = """\
你是一个数据分析助手，专门负责将用户的自然语言问题转换为 SQLite 查询。

## 数据库结构
{schema}

## 规则
1. 只生成 SELECT 语句，禁止 INSERT / UPDATE / DELETE / DROP / ALTER
2. 输出格式必须是合法的 JSON，包含以下字段：
   {{"sql": "你生成的 SQL 语句", "explanation": "这句 SQL 在查什么，一句话说明"}}
3. 如果用户的问题无法用 SQL 回答，sql 字段设为空字符串 ""
4. SQL 必须能在 SQLite 中执行，注意日期函数用 date('now')、strftime 等
5. 用户可能用「昨天」「上周」「最近7天」等模糊时间词，你需要转换为具体条件

## 示例
用户: 昨天全站 PV 是多少
输出: {{"sql": "SELECT SUM(pv) as total_pv FROM app_metrics WHERE date = date('now', '-1 day')", "explanation": "查询昨天全站页面浏览总量"}}

用户: 各城市下载量排行
输出: {{"sql": "SELECT city, SUM(downloads) as total FROM app_metrics GROUP BY city ORDER BY total DESC", "explanation": "按城市统计下载量并降序排列"}}
"""


def _build_user_prompt(question: str) -> str:
    return f"用户问题: {question}\n请生成 SQL:"


# ============================================================
# LLM 调用
# ============================================================
def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """调用 LLM，返回文本响应。"""
    response = _get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    return response.choices[0].message.content or ""


# ============================================================
# 核心流程
# ============================================================
def ask(question: str) -> str:
    """
    用户问一句话 → 返回中文结论。

    这是阶段一的入口，完整流程:
      问题 → LLM 生成 SQL → 执行 SQL → LLM 翻译结果 → 返回
    """
    # ---- 第一步: 生成 SQL ----
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        schema=_build_schema_description()
    )
    user_prompt = _build_user_prompt(question)

    llm_response = _call_llm(system_prompt, user_prompt)

    # 解析 LLM 返回的 JSON
    try:
        # 处理可能的 markdown 代码块包裹
        raw = llm_response.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]  # 去掉 ```json
            if raw.endswith("```"):
                raw = raw[:-3]
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return f"❌ LLM 返回格式异常，无法解析:\n{llm_response[:500]}"

    sql = parsed.get("sql", "").strip()
    explanation = parsed.get("explanation", "")

    if not sql:
        return f"⚠️ 这个问题我无法转换为 SQL 查询。{explanation}"

    # ---- 第二步: 执行 SQL ----
    result = execute(DATABASE_PATH, sql)

    if not result.success:
        return f"❌ SQL 执行失败: {result.error}\n执行的 SQL: {sql}"

    # ---- 第三步: 翻译结果 ----
    if result.row_count == 0:
        return f"📭 查询没有返回数据。{explanation}"

    # 格式化结果给 LLM 翻译
    data_text = _format_result(result)
    translate_prompt = f"""\
用户问题: {question}
SQL 查询: {sql}
查询结果:
{data_text}

请把以上查询结果翻译成简洁的中文人话回答。用数字说话，例如「昨天全站 PV 为 102.3 万」。"""

    answer = _call_llm(
        "你是数据分析助手，把查询结果翻译成用户能看懂的中文。只输出结论，不要解释过程。",
        translate_prompt,
    )
    return answer.strip()


def _format_result(result) -> str:
    """把 QueryResult 格式化为易读的文本。"""
    lines = []
    # 表头
    lines.append(" | ".join(result.columns))
    lines.append("-" * 40)
    # 数据行（最多 50 行，避免 token 爆炸）
    for row in result.rows[:50]:
        lines.append(" | ".join(str(v) for v in row))
    if result.row_count > 50:
        lines.append(f"... 还有 {result.row_count - 50} 行未显示")
    return "\n".join(lines)
