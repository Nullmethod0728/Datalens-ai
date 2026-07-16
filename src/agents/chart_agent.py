"""
图表 Agent
----------
输入: 数据 + 图表类型提示
输出: ECharts 配置 JSON

不是让 LLM 画图——是让它生成 ECharts 的 option 配置 JSON。
前端拿到这个 JSON 后用自己的 ECharts 引擎渲染。

支持的图表类型: bar（柱状图）, line（折线图）, pie（饼图）, scatter（散点图）
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
from src.tools.pandas_analyzer import build_dataframe

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
# ECharts 配置模板
# ============================================================
ECHART_SCHEMA = """\
你是一个 ECharts 图表配置专家。根据提供的数据，生成一个 ECharts option JSON。

## ECharts option 基本结构
```json
{
  "title": {"text": "图表标题", "subtext": "副标题"},
  "tooltip": {"trigger": "axis"},
  "legend": {"data": ["系列名1", "系列名2"]},
  "xAxis": {"type": "category", "data": ["A", "B", "C"]},
  "yAxis": {"type": "value"},
  "series": [
    {"name": "系列名", "type": "bar", "data": [1, 2, 3]}
  ]
}
```

## 图表类型选择
- 数据维度是一个(如 x=城市, y=下载量) → type: "bar"
- 数据是时间序列 → type: "line", xAxis.data 放日期
- 数据是占比 → type: "pie", 不需要 xAxis/yAxis, series 放 [{name, value}]
- 有多个系列 → legend.data 列出所有系列名

## 颜色（浅色主题）
color: ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4']

## 规则
1. 输出必须是合法的 JSON，不要包含注释
2. title.text 用中文
3. 数据值保持原始精度
4. 如果数据超过 20 条，只取前 20 条
"""


# ============================================================
# 公共方法
# ============================================================
def generate_chart(
    data,
    chart_type: str = "auto",
    title: str = "",
    subtitle: str = "",
) -> dict | None:
    """
    根据数据生成 ECharts 配置。

    参数:
        data: QueryResult 或 list[dict] 或 pd.DataFrame
        chart_type: "bar" / "line" / "pie" / "auto"
        title: 图表标题
        subtitle: 副标题

    返回:
        ECharts option dict，失败返回 None
    """
    # 统一转为可序列化的格式
    if hasattr(data, 'columns') and hasattr(data, 'rows'):
        # QueryResult
        records = [_row_to_dict(data.columns, row) for row in data.rows[:20]]
    elif hasattr(data, 'to_dict'):
        # DataFrame
        records = data.head(20).to_dict(orient="records")
    elif isinstance(data, list):
        records = data[:20]
    else:
        records = []

    if not records:
        return None

    # 列信息
    columns = list(records[0].keys()) if records else []

    # 构造 prompt
    type_hint = f"使用 {chart_type} 图表类型。" if chart_type != "auto" else "根据数据自动选择最合适的图表类型（bar/line/pie）。"
    title_hint = f'标题: "{title}"。' if title else "根据数据内容自动生成标题。"
    sub_hint = f'副标题: "{subtitle}"。' if subtitle else ""

    prompt = f"""\
{type_hint}
{title_hint}
{sub_hint}

数据列: {', '.join(columns)}
数据预览（前 10 行）:
{json.dumps(records[:10], ensure_ascii=False, indent=2)}

请生成 ECharts option JSON。只输出 JSON，不要其他文字。"""

    response = _get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": ECHART_SCHEMA},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=MAX_TOKENS,
    )
    raw = response.choices[0].message.content or ""

    # 解析 JSON
    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
        return json.loads(raw)
    except json.JSONDecodeError:
        # 尝试提取 {...} 块
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        return None


def generate_multi_chart(
    data,
    dimensions: list[str] | None = None,
    title_prefix: str = "",
) -> list[dict]:
    """
    为一个数据集生成多张图表（每个维度一张）。

    返回: [{"title": "...", "chart": {...}}, ...]
    """
    df = build_dataframe(data) if hasattr(data, 'columns') else None
    if df is None and isinstance(data, list):
        import pandas as pd
        df = pd.DataFrame(data)

    if df is None or df.empty:
        return []

    if dimensions is None:
        # 自动选择分类列
        dimensions = [c for c in df.columns if df[c].dtype == 'object'][:3]

    charts = []
    for dim in dimensions:
        if dim not in df.columns:
            continue
        # 按维度聚合
        grouped = df.groupby(dim).sum(numeric_only=True)
        if grouped.empty:
            continue
        metric_col = grouped.columns[0]
        records = grouped.reset_index()[[dim, metric_col]].to_dict(orient="records")

        chart = generate_chart(
            records,
            chart_type="bar",
            title=f"{title_prefix}{dim}维度分析",
        )
        if chart:
            charts.append({"title": f"{dim}维度分析", "chart": chart})

    return charts


def _row_to_dict(columns: list[str], row: tuple) -> dict:
    return {col: val for col, val in zip(columns, row)}
