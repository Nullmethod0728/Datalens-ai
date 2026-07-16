"""
DataLens AI — Streamlit 前端
=============================
阶段六: 用户对话界面 + 图表嵌入 + 报告展示

启动:
    streamlit run src/web/app.py
"""

import sys
from pathlib import Path

# 确保项目根在 path 中
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

# ---- 页面配置 ----
st.set_page_config(
    page_title="DataLens AI",
    page_icon="📊",
    layout="wide",
)

# ---- 标题栏 ----
st.title("📊 DataLens AI")
st.caption("Multi-Agent 智能数据分析系统 — 输入问题，自动查数据、分析、出图、写报告")

# ---- 侧边栏 ----
with st.sidebar:
    st.header("⚙️ 功能模式")
    st.markdown("""
    - **普通对话**: 随便问，AI 判断要不要查库
    - **深度分析**: 含"为什么/原因/趋势"等自动归因
    - **完整报告**: /report 开头 → 图表 + 报告
    """)

    st.divider()
    st.header("📋 示例问题")
    if st.button("昨天的 PV 是多少"):
        st.session_state.pending_question = "昨天的 PV 是多少"
    if st.button("各城市下载量排行"):
        st.session_state.pending_question = "各城市下载量排行"
    if st.button("为什么最近一个月下载量下跌"):
        st.session_state.pending_question = "为什么最近一个月下载量下跌了"
    if st.button("最近一周各应用下载量趋势如何"):
        st.session_state.pending_question = "最近一周各应用下载量趋势如何"

    st.divider()
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = [
            {"role": "assistant", "content": "你好！我是 DataLens AI，可以帮你查询和分析应用商店数据。想问什么？"}
        ]


# ---- 懒加载后端模块 ----
@st.cache_resource
def load_agents():
    """缓存后端模块，避免每次重载。"""
    from src.core.config import validate
    validate()
    from src.agents.sql_agent import ask as sql_ask
    from src.core.orchestrator import run_analysis, run_report
    return sql_ask, run_analysis, run_report


sql_ask, run_analysis, run_report = load_agents()


# ---- 聊天历史 ----
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "你好！我是 DataLens AI，可以帮你查询和分析应用商店数据。想问什么？"}
    ]
if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""


# ---- 处理输入 ----
def handle_question(question: str):
    """根据问题类型调度到不同后端。"""
    if question.startswith("/report"):
        # 报告模式
        q = question.replace("/report", "").strip()
        if not q:
            return {"type": "text", "content": "用法: /report 你的问题"}
        with st.spinner("正在生成完整报告..."):
            output = run_report(q)
        return {"type": "report", "content": output}

    elif any(kw in question for kw in
            ["为什么", "原因", "趋势", "异常", "下跌", "上涨", "波动", "贡献", "占比"]):
        # 分析模式
        with st.spinner("正在分析..."):
            result = run_analysis(question)
        return {"type": "analysis", "content": result}

    else:
        # 普通问答
        with st.spinner("查询中..."):
            result = sql_ask(question)
        return {"type": "text", "content": result}


# ---- 渲染图表 ----
def render_chart(chart_config: dict, key: str = ""):
    """用 ECharts 渲染图表。"""
    try:
        from streamlit_echarts import st_echarts
        st_echarts(
            options=chart_config,
            height="400px",
            key=key or str(hash(str(chart_config))),
        )
    except ImportError:
        st.info("💡 安装 streamlit-echarts 后可渲染图表: `pip install streamlit-echarts`")
        with st.expander("📊 ECharts 配置 (JSON)", expanded=False):
            import json
            st.json(chart_config)


# ---- 渲染消息 ----
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        # 报告类型消息
        if msg.get("msg_type") == "report":
            output = msg["report_data"]
            st.markdown(output.get("report", ""))

            charts = output.get("charts", [])
            if charts:
                st.subheader("📈 图表")
                cols = st.columns(min(len(charts), 2))
                for j, chart_info in enumerate(charts):
                    with cols[j % 2]:
                        st.caption(chart_info.get("title", ""))
                        render_chart(chart_info["chart"], key=f"chart_{i}_{j}")

            if output.get("analysis"):
                with st.expander("查看分析过程"):
                    st.text(output["analysis"][:500])

        # 分析类型消息
        elif msg.get("msg_type") == "analysis":
            st.markdown(msg["content"])

        # 普通文本
        else:
            st.markdown(msg["content"])


# ---- 输入框 ----
question = st.chat_input("输入你的问题...", key="chat_input")

# 处理侧边栏示例按钮
if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = ""

if question:
    # 添加用户消息
    st.session_state.messages.append({"role": "user", "content": question})

    # 显示用户消息
    with st.chat_message("user"):
        st.markdown(question)

    # 处理后端
    result = handle_question(question)

    # 添加 AI 回复
    if result["type"] == "report":
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"**完整分析报告已生成**\n\n{result['content'].get('report', '')[:200]}...",
            "msg_type": "report",
            "report_data": result["content"],
        })
    elif result["type"] == "analysis":
        st.session_state.messages.append({
            "role": "assistant",
            "content": result["content"],
            "msg_type": "analysis",
        })
    else:
        st.session_state.messages.append({
            "role": "assistant",
            "content": result["content"],
        })

    # 重新渲染
    st.rerun()
