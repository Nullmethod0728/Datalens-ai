"""
Orchestrator — 多 Agent 编排器
-------------------------------
阶段四的核心: Supervisor（你写的代码）决定「什么时候调哪个 Agent」。

架构:
  用户问题
    │
    ▼
  Supervisor（决策函数）
    ├─ Step 1: SQL Agent → 查数据
    ├─ Step 2: Analysis Agent → 分析数据
    └─ Step 3: 汇总输出

Supervisor 不是 LLM，是你用代码写的一个状态机:
  - 数据还没查 → 路由到 sql_agent
  - 数据有了但没分析 → 路由到 analysis_agent
  - 分析完了 → 输出给用户
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
from src.tools.sql_executor import execute, list_tables, get_table_schema
from src.tools.sql_validator import validate
from src.agents.analysis_agent import analyze
from src.core.memory import get_memory


# ============================================================
# 懒加载
# ============================================================
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    return _client


# ============================================================
# Prompt 加载
# ============================================================
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    p = _PROMPTS_DIR / filename
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ============================================================
# 分析关键词（用于判断是否需要走分析流程）
# ============================================================
ANALYSIS_KEYWORDS = [
    "为什么", "原因", "分析", "趋势", "异常", "下降", "上升",
    "涨了", "跌了", "变化", "对比", "排行", "贡献", "占比",
    "同比", "环比", "哪个", "哪些",
]


def _needs_analysis(question: str) -> bool:
    """判断用户问题是否需要深度分析。"""
    return any(kw in question for kw in ANALYSIS_KEYWORDS)


# ============================================================
# Supervisor 状态机
# ============================================================
from enum import Enum


class State(Enum):
    NEED_DATA = "need_data"
    NEED_ANALYSIS = "need_analysis"
    DONE = "done"


def _supervisor(state: State, question: str, has_data: bool = False) -> State:
    """
    决策函数——这不是 LLM，是你用代码写死逻辑。

    规则:
    - 问题需要分析 + 还没数据 → NEED_DATA
    - 有数据 + 需要分析 → NEED_ANALYSIS
    - 否则 → DONE
    """
    if _needs_analysis(question):
        if not has_data:
            return State.NEED_DATA
        else:
            return State.NEED_ANALYSIS
    else:
        if not has_data:
            return State.NEED_DATA  # 简单查询也走 SQL
        else:
            return State.DONE       # 数据有了，翻译即可


# ============================================================
# SQL Agent（Orchestrator 内部版）
# ============================================================
def _sql_agent(question: str) -> tuple:
    """
    Orchester 调用的 SQL Agent: 问题 → SQL → 执行 → 返回 (QueryResult, sql)。
    """
    from datetime import date

    system_prompt = f"""\
你是数据分析助手，专门生成 SQLite 查询。

今天是 {date.today().isoformat()}。用户说的「昨天」「上周」请基于此日期计算。

## 数据库结构
{_load_prompt('schema_prompt.txt')}

## 查询示例
{_load_prompt('fewshot_examples.txt')}

## 规则
1. 只生成 SELECT 语句
2. 输出格式: {{"sql": "...", "explanation": "..."}}
3. ⚠️ 如果用户要做分析（含"为什么""原因""趋势""变化"），你**必须**把数据按多个维度拆分:
   - 同时包含 app_name、city、device_type、date 列
   - 不要只查 SUM，要 GROUP BY 至少 2 个维度
   - 例如: SELECT date, app_name, city, SUM(downloads) FROM ... GROUP BY date, app_name, city
   - 这样做分析 Agent 才能找出哪个应用、哪个城市贡献了变化
"""

    response = _get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户问题: {question}\n请生成 SQL:"},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    raw = response.choices[0].message.content or ""

    # 解析 JSON
    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
        parsed = json.loads(raw)
        sql = parsed.get("sql", "").strip()
    except json.JSONDecodeError:
        return None, ""

    if not sql:
        return None, ""

    # 安全校验
    passed, reason = validate(sql)
    if not passed:
        # 重试一次（简单处理）
        response2 = _get_client().chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"用户问题: {question}\n请生成 SQL:"},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"SQL 校验失败: {reason}。请修正后重新输出 JSON。"},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        raw2 = response2.choices[0].message.content or ""
        try:
            if raw2.startswith("```"):
                raw2 = raw2.split("\n", 1)[1]
                if raw2.endswith("```"):
                    raw2 = raw2[:-3]
            sql = json.loads(raw2).get("sql", "").strip()
        except json.JSONDecodeError:
            return None, ""

    if not sql:
        return None, ""

    result = execute(DATABASE_PATH, sql)
    return result, sql


# ============================================================
# 公共入口
# ============================================================
def run_analysis(question: str) -> str:
    """
    Orchestrator 入口——用户问一个问题，自动编排 SQL → 分析 → 结论。

    用法:
        from src.core.orchestrator import run_analysis
        answer = run_analysis("最近一个月各应用的下载量趋势怎么样")
    """
    memory = get_memory()
    memory.add_history(question, "")  # 先记问题

    # ---- Step 1: SQL Agent ----
    state = _supervisor(State.NEED_DATA, question, has_data=False)

    if state == State.NEED_DATA:
        result, sql = _sql_agent(question)
        if result is None:
            return "⚠️ 无法为这个问题生成 SQL 查询。"

        if not result.success:
            return f"❌ SQL 执行失败: {result.error}"

        memory.set("last_sql", sql)
        memory.set("last_result", result)

        if result.row_count == 0:
            return "📭 查询没有返回数据。"

    # ---- Step 2: Analysis Agent ----
    state = _supervisor(State.NEED_DATA, question, has_data=True)

    if state == State.NEED_ANALYSIS:
        print("  📊 正在分析数据...")
        analysis = analyze(memory.get("last_result"), question)
        memory.set("last_analysis", analysis)
        memory.add_history(question, analysis[:100])
        return analysis

    # ---- Step 3: 简单翻译 ----
    result = memory.get("last_result")
    data_text = _format_quick(result)
    translate_prompt = f"""\
用户问题: {question}
查询结果:
{data_text}

请把以上查询结果翻译成简洁的中文人话回答。"""

    response = _get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "你是数据分析助手，把查询结果翻译成用户能看懂的中文。只输出结论。"},
            {"role": "user", "content": translate_prompt},
        ],
        temperature=0.3,
        max_tokens=MAX_TOKENS,
    )
    answer = response.choices[0].message.content or ""
    memory.add_history(question, answer[:100])
    return answer.strip()


def _format_quick(result) -> str:
    """快速格式化 QueryResult。"""
    if result.row_count > 50:
        lines = [" | ".join(result.columns)]
        lines.append("-" * 40)
        for row in result.rows[:50]:
            lines.append(" | ".join(str(v) for v in row))
        lines.append(f"... 还有 {result.row_count - 50} 行")
        return "\n".join(lines)
    return "\n".join([
        " | ".join(result.columns),
        "-" * 40,
        *[" | ".join(str(v) for v in row) for row in result.rows],
    ])
