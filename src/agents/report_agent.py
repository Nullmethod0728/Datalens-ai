"""
报告 Agent
----------
输入: 用户问题 + 分析结论 + 图表
输出: 结构化的 Markdown 分析报告

报告结构:
  1. 摘要（一段话概述）
  2. 关键发现（分点列出，有数据支撑）
  3. 数据明细（表格）
  4. 图表位（ECharts 配置 JSON 嵌入）
  5. 建议（1-3 条 actionable 建议）
"""

import json
from openai import OpenAI

from src.core.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    MODEL_NAME,
    TEMPERATURE,
    MAX_TOKENS,
)

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
# Report Schema
# ============================================================
REPORT_SYSTEM_PROMPT = """\
你是一个数据分析报告撰写专家。根据提供的分析材料，写一份结构化的 Markdown 分析报告。

## 报告结构
1. **## 摘要** — 一段话，概括核心结论
2. **## 关键发现** — 3-5 个 bullet point，每个带具体数字
3. **## 数据支撑** — 把原始数据整理成 Markdown 表格
4. **## 图表** — 标明哪里有图（用 `[图表: 标题]` 占位）
5. **## 建议** — 1-3 条可操作的建议

## 规则
- 只输出 Markdown，不要解释报告本身
- 数字粗体（用 **数字** 包裹关键数字）
- 建议要具体可执行，不要说"加强优化"这种废话
- 全篇用中文
"""


# ============================================================
# 公共方法
# ============================================================
def generate_report(
    question: str,
    analysis: str,
    data_summary: str = "",
    charts: list[dict] | None = None,
) -> str:
    """
    生成 Markdown 分析报告。

    参数:
        question: 用户原始问题
        analysis: 分析 Agent 的结论
        data_summary: 数据概要（列名、行数等）
        charts: 图表列表 [{"title": "...", "chart": {...}}, ...]

    返回:
        完整的 Markdown 报告文本
    """
    chart_info = ""
    if charts:
        chart_info = "## 已生成的图表\n"
        for i, c in enumerate(charts, 1):
            chart_info += f"{i}. {c.get('title', '图表')}\n"

    prompt = f"""\
## 用户问题
{question}

## 分析结论
{analysis}

## 数据概要
{data_summary if data_summary else "（数据已由分析 Agent 处理）"}

{chart_info}

请根据以上材料，写一份结构化的 Markdown 分析报告。"""

    response = _get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=MAX_TOKENS,
    )
    return response.choices[0].message.content or ""


def generate_full_report(
    question: str,
    query_result,
    analysis_result: str,
) -> dict:
    """
    一键生成完整报告: 数据分析 + 图表 + 报告。

    返回:
        {
            "analysis": "归因分析文本",
            "charts": [{"title": "...", "chart": {...}}, ...],
            "report": "Markdown 报告",
        }
    """
    from src.agents.analysis_agent import analyze
    from src.agents.chart_agent import generate_chart, generate_multi_chart

    # Step 1: 分析
    if not analysis_result:
        analysis_result = analyze(query_result, question)

    # Step 2: 图表
    charts = []
    try:
        main_chart = generate_chart(
            query_result,
            chart_type="auto",
            title=question[:30],
        )
        if main_chart:
            charts.append({"title": "主图表", "chart": main_chart})
    except Exception:
        pass

    # 多维度图表
    try:
        dim_charts = generate_multi_chart(query_result, title_prefix="")
        charts.extend(dim_charts[:3])  # 最多 4 张图
    except Exception:
        pass

    # Step 3: 报告
    report = generate_report(
        question=question,
        analysis=analysis_result,
        data_summary=f"查询返回 {query_result.row_count} 行数据" if hasattr(query_result, 'row_count') else "",
        charts=charts,
    )

    return {
        "analysis": analysis_result,
        "charts": charts,
        "report": report,
    }
