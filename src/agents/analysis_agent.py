"""
分析 Agent
----------
职责: 拿到数据 → Pandas 计算 → 找规律 → LLM 总结 → 给结论

不是直接面向用户，而是被 Orchestrator 调用。
输入: 数据 + 用户原始问题
输出: 结构化的中文分析结论
"""

import json
import pandas as pd
from openai import OpenAI

from src.core.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    MODEL_NAME,
    TEMPERATURE,
    MAX_TOKENS,
)
from src.tools.pandas_analyzer import (
    build_dataframe,
    describe,
    calc_contribution,
    detect_anomalies,
    calc_trend,
    calc_period_change,
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
# 核心分析方法
# ============================================================
def analyze(query_result, user_question: str) -> str:
    """
    对查询结果做分析，返回中文结论。

    参数:
        query_result: sql_executor.QueryResult（SQL 查询的输出）
        user_question: 用户原始问题（如"为什么转化率下降了"）

    返回:
        结构化的中文分析文本
    """
    df = build_dataframe(query_result)
    if df is None or df.empty:
        return "数据为空，无法分析。"

    # ---- 第一步: 自动选择合适的分析 ----
    findings = _run_numerical_analysis(df, user_question)

    # ---- 第二步: LLM 把分析结果翻译成人话 ----
    return _summarize(findings, user_question, df)


def _run_numerical_analysis(df: pd.DataFrame, question: str) -> dict:
    """
    自动选择分析策略:
    - 如果数据包含 app_name → 按应用拆贡献度 + 异常检测
    - 如果数据包含 city → 按城市拆贡献度
    - 如果数据包含 date → 趋势分析
    - 总是做描述性统计
    """
    findings = {}

    # 描述性统计（总是做）
    findings["summary"] = describe(df)

    # 按维度拆贡献度
    dim_candidates = ["app_name", "city", "device_type", "category"]
    metric_candidates = ["downloads", "pv", "uv", "revenue", "active_users", "new_users"]

    # 找一个合适的指标列（fuzzy match，因为 SQL 可能有别名如 total_downloads）
    def _find_metric_col(df_cols: list[str], candidates: list[str]) -> str | None:
        for col in df_cols:
            for candidate in candidates:
                if candidate in col.lower():
                    return col
        return None

    metric = _find_metric_col(
        [c.lower() for c in df.columns], metric_candidates
    )
    # 还原为真实的列名
    for col in df.columns:
        if col.lower() == metric:
            metric = col
            break
    if metric is None:
        # 回退: 取第一个数值列
        for col in df.columns:
            if df[col].dtype in ('int64', 'float64'):
                metric = col
                break
    if metric is None:
        findings["error"] = "无法找到数值列进行分析"
        return findings

    # 按各维度做贡献度分析
    for dim in dim_candidates:
        if dim in df.columns:
            findings[f"contribution_by_{dim}"] = calc_contribution(df, metric, dim)

    # 异常检测
    for dim in dim_candidates:
        if dim in df.columns and df[dim].nunique() >= 3:
            anomalies = detect_anomalies(df, metric, dim, threshold=1.5)
            if anomalies:
                findings[f"anomalies_by_{dim}"] = anomalies

    # 趋势分析（如果有时间列）
    if "date" in df.columns:
        findings["trend"] = calc_trend(df, metric)

    # 环比（如果数据涉及两个时间段）
    if "date" in df.columns and df["date"].nunique() == 2:
        dates = sorted(df["date"].unique())
        if len(dates) == 2:
            cur = df[df["date"] == dates[1]][metric]
            prev = df[df["date"] == dates[0]][metric]
            findings["period_change"] = calc_period_change(cur, prev)

    return findings


def _summarize(findings: dict, question: str, df: pd.DataFrame) -> str:
    """
    把 Pandas 分析结果 + 原始问题一起发给 LLM，让它翻译成人话。
    """
    # 精简 findings 给 LLM（去掉过长的 list）
    findings_compact = {}
    for key, value in findings.items():
        if isinstance(value, list) and len(value) > 10:
            findings_compact[key] = value[:10]
        else:
            findings_compact[key] = value

    prompt = f"""\
你是一个数据分析专家。以下是针对用户问题的分析结果，请用中文写一份简洁的根因分析。

## 用户问题
{question}

## 数据概况
- 行数: {len(df)}
- 列: {', '.join(df.columns)}

## 分析结果
```json
{json.dumps(findings_compact, ensure_ascii=False, indent=2)}
```

## 请回答
1. 核心发现（1-2 句话）
2. 贡献度最高的是谁（列具体数字）
3. 有没有异常点
4. 趋势是上升还是下降
5. 给出 1-2 条建议

直接输出给用户看，不要解释过程。关键数字用粗体。"""

    response = _get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "你是数据分析专家，把分析结果翻译成用户能看懂的中文。简洁有力。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=MAX_TOKENS,
    )
    return response.choices[0].message.content or ""
