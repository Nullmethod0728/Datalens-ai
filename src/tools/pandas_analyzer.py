"""
Pandas 分析函数库
-----------------
纯计算层，不调 LLM。负责:
- 趋势计算（环比、同比）
- 贡献度拆解（哪个维度贡献了变化）
- 异常检测（哪个维度偏离正常范围）
- 描述性统计

所有函数输入是 pandas DataFrame / dict，输出是结构化的分析结果（dict）。
"""

import pandas as pd
import numpy as np
from typing import Any


def build_dataframe(query_result) -> pd.DataFrame | None:
    """
    把 sql_executor.QueryResult 转为 pandas DataFrame。
    这是从 SQL 世界到分析世界的桥梁。
    """
    if not query_result.success or query_result.row_count == 0:
        return None
    return pd.DataFrame(query_result.rows, columns=query_result.columns)


# ============================================================
# 描述性统计
# ============================================================
def describe(df: pd.DataFrame) -> dict[str, Any]:
    """
    对 DataFrame 所有数值列做描述性统计。

    返回:
        { "pv": {"sum": ..., "avg": ..., "min": ..., "max": ..., "std": ...}, ... }
    """
    result = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col]
        result[col] = {
            "sum": float(series.sum()),
            "avg": float(series.mean()),
            "min": float(series.min()),
            "max": float(series.max()),
            "std": float(series.std()),
        }
    return result


# ============================================================
# 环比 / 同比计算
# ============================================================
def calc_period_change(
    current: pd.Series,
    previous: pd.Series,
) -> dict[str, float]:
    """
    计算环比变化。

    参数:
        current: 当前周期的数值序列
        previous: 上一周期的数值序列

    返回:
        {"current_sum": ..., "previous_sum": ..., "delta": ..., "pct_change": ...}
    """
    cur_sum = float(current.sum())
    prev_sum = float(previous.sum())
    delta = cur_sum - prev_sum
    pct = (delta / prev_sum * 100) if prev_sum != 0 else 0.0
    return {
        "current_sum": cur_sum,
        "previous_sum": prev_sum,
        "delta": delta,
        "pct_change": round(pct, 2),
    }


# ============================================================
# 贡献度拆解
# ============================================================

def calc_contribution(
    df: pd.DataFrame,
    metric: str,
    dimension: str,
) -> list[dict[str, Any]]:
    """
    计算每个维度值对总量变化的贡献度。

    工作原理:
      1. 按 dimension 分组，计算每组 metric 的总和
      2. 计算每组占总量的百分比
      3. 按贡献度降序排列

    参数:
        df: 数据
        metric: 指标列名（如 'downloads'）
        dimension: 维度列名（如 'app_name'）

    返回:
        [{"dim": "抖音", "value": 12345, "pct": 42.5}, ...]
    """
    if metric not in df.columns or dimension not in df.columns:
        return []

    grouped = df.groupby(dimension)[metric].sum().sort_values(ascending=False)
    total = float(grouped.sum())

    result = []
    for dim_val, metric_val in grouped.items():
        result.append({
            "dim": str(dim_val),
            "value": float(metric_val),
            "pct": round(float(metric_val) / total * 100, 1) if total > 0 else 0,
        })
    return result


# ============================================================
# 异常检测
# ============================================================
def detect_anomalies(
    df: pd.DataFrame,
    metric: str,
    dimension: str,
    threshold: float = 2.0,
) -> list[dict[str, Any]]:
    """
    用 Z-score 方法检测异常维度值。

    工作原理:
      1. 按 dimension 分组，计算每组 metric 的总和
      2. 计算各组的标准分数 (z-score)
      3. |z-score| > threshold 的组标记为异常

    返回:
        [{"dim": "抖音", "value": ..., "z_score": 3.2, "anomaly": "above"}, ...]
    """
    if metric not in df.columns or dimension not in df.columns:
        return []

    grouped = df.groupby(dimension)[metric].sum()
    if len(grouped) < 3:
        return []  # 样本太少，无法计算

    mean_val = grouped.mean()
    std_val = grouped.std()
    if std_val == 0:
        return []

    anomalies = []
    for dim_val, metric_val in grouped.items():
        z = (metric_val - mean_val) / std_val
        if abs(z) > threshold:
            anomalies.append({
                "dim": str(dim_val),
                "value": float(metric_val),
                "z_score": round(float(z), 2),
                "anomaly": "above" if z > 0 else "below",
            })

    return sorted(anomalies, key=lambda x: abs(x["z_score"]), reverse=True)


# ============================================================
# 趋势分析
# ============================================================
def calc_trend(
    df: pd.DataFrame,
    metric: str,
    time_col: str = "date",
) -> dict[str, Any]:
    """
    对时间序列做简单线性回归，判断趋势方向。

    返回:
        {"slope": ..., "direction": "上升"/"下降"/"平稳", "r_squared": ...}
    """
    if metric not in df.columns or time_col not in df.columns:
        return {"error": f"列不存在: {metric} 或 {time_col}"}

    ts = df.groupby(time_col)[metric].sum().reset_index()
    ts = ts.sort_values(time_col)

    if len(ts) < 3:
        return {"direction": "样本不足", "slope": 0, "r_squared": 0}

    try:
        from sklearn.linear_model import LinearRegression
    except ImportError:
        return {"direction": "未知（sklearn 未安装）", "slope": 0, "r_squared": 0}

    X = np.arange(len(ts)).reshape(-1, 1)
    y = ts[metric].values

    model = LinearRegression()
    model.fit(X, y)
    y_pred = model.predict(X)

    # R²
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    slope = float(model.coef_[0])
    if slope > 0.05 * y.mean() / len(y):
        direction = "上升"
    elif slope < -0.05 * y.mean() / len(y):
        direction = "下降"
    else:
        direction = "平稳"

    return {
        "slope": round(slope, 4),
        "direction": direction,
        "r_squared": round(r2, 4),
    }
