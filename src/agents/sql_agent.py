"""
SQL Agent — 单轮 Text-to-SQL（阶段三增强）
-------------------------------------------
阶段一: 表结构+问题 → LLM 生成 SQL → 执行 → 翻译
阶段三: + Schema 精简 + Few-shot + SQL 校验 + 错误重试

用于 python run.py "单个问题" 模式，轻量快速。
"""

import json
from pathlib import Path
from openai import OpenAI

from src.core.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    MODEL_NAME,
    TEMPERATURE,
    MAX_TOKENS,
    DATABASE_PATH,
)
from src.tools.sql_executor import execute
from src.tools.sql_validator import validate


# ============================================================
# 初始化（懒加载）
# ============================================================
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    return _client


# ============================================================
# 加载 prompt 资源文件
# ============================================================
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def _load_prompt_file(filename: str) -> str:
    filepath = _PROMPTS_DIR / filename
    return filepath.read_text(encoding="utf-8") if filepath.exists() else ""


# ============================================================
# Prompt 构建
# ============================================================
SYSTEM_PROMPT_TEMPLATE = """\
你是一个数据分析助手，专门负责将用户的自然语言问题转换为 SQLite 查询。

今天是 {today}。用户说的「昨天」「上周」等时间词请基于这个日期计算。

## 数据库结构
{schema}

## 查询示例（请模仿以下 SQL 风格）
{fewshot}

## 规则
1. 只生成 SELECT 语句，禁止 INSERT / UPDATE / DELETE / DROP / ALTER
2. 输出格式必须是合法的 JSON:
   {{"sql": "你的 SQL", "explanation": "一句话说明在查什么"}}
3. 用户问题无法用 SQL 回答时，sql 设为空字符串 ""
4. 日期函数使用 SQLite 语法: date('now')、strftime 等
"""


def _build_user_prompt(question: str) -> str:
    return f"用户问题: {question}\n请生成 SQL:"


# ============================================================
# LLM 调用
# ============================================================
def _call_llm(system_prompt: str, user_prompt: str) -> str:
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


def _parse_sql_response(llm_response: str) -> tuple[str, str]:
    """解析 LLM 返回的 JSON，提取 sql 和 explanation。"""
    try:
        raw = llm_response.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
        parsed = json.loads(raw)
        return parsed.get("sql", "").strip(), parsed.get("explanation", "")
    except json.JSONDecodeError:
        return "", ""


# ============================================================
# 核心流程
# ============================================================
MAX_RETRIES = 3   # 阶段三: SQL 错误最多重试 3 次


def ask(question: str) -> str:
    """
    用户问一句话 → 返回中文结论。

    流程: 问题 → LLM 生成 SQL → 校验 → 执行 → 失败则重试 → 翻译
    """
    from datetime import date

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        today=date.today().isoformat(),
        schema=_load_prompt_file("schema_prompt.txt"),
        fewshot=_load_prompt_file("fewshot_examples.txt"),
    )

    # ---- 第一步: 生成 SQL（含重试） ----
    last_sql = ""
    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt == 1:
            user_prompt = _build_user_prompt(question)
        else:
            # 重试: 告诉 LLM 上次哪里错了
            user_prompt = (
                f"用户问题: {question}\n\n"
                f"你上一次生成的 SQL 是:\n```sql\n{last_sql}\n```\n"
                f"执行时报错: {last_error}\n\n"
                f"请修正 SQL 后重新输出 JSON。"
            )

        llm_response = _call_llm(system_prompt, user_prompt)
        sql, explanation = _parse_sql_response(llm_response)

        if not sql:
            return f"⚠️ 这个问题我无法转换为 SQL 查询。{explanation}"

        last_sql = sql

        # ---- 校验 ----
        passed, reason = validate(sql)
        if not passed:
            last_error = f"校验不通过: {reason}"
            continue

        # ---- 执行 ----
        result = execute(DATABASE_PATH, sql)
        if result.success:
            break  # 成功了，跳出重试循环
        else:
            last_error = result.error
    else:
        # 重试耗尽
        return f"❌ 这个问题我暂时查不了，SQL 经过 {MAX_RETRIES} 次修正仍然失败。\n最后的错误: {last_error}\n最后的 SQL: {last_sql}"

    # ---- 第二步: 翻译结果 ----
    if result.row_count == 0:
        return f"📭 查询没有返回数据。{explanation}"

    data_text = _format_result(result)
    translate_prompt = f"""\
用户问题: {question}
SQL 查询: {sql}
查询结果:
{data_text}

请把以上查询结果翻译成简洁的中文人话回答。用数字说话，例如「昨天全站 PV 为 102.3 万」。"""

    answer = _call_llm(
        "你是数据分析助手，把查询结果翻译成用户能看懂的中文。只输出结论。",
        translate_prompt,
    )
    return answer.strip()


def _format_result(result) -> str:
    """把 QueryResult 格式化为易读的表格文本。"""
    lines = [" | ".join(result.columns)]
    lines.append("-" * 40)
    for row in result.rows[:50]:
        lines.append(" | ".join(str(v) for v in row))
    if result.row_count > 50:
        lines.append(f"... 还有 {result.row_count - 50} 行未显示")
    return "\n".join(lines)
