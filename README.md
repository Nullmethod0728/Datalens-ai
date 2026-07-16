# DataLens AI

**Multi-Agent 智能数据分析系统** — 输入自然语言，自动查数据、做分析、画图表、写报告。

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![LLM](https://img.shields.io/badge/LLM-DeepSeek%20%7C%20OpenAI-orange)](#配置-api-key)

## 效果展示

**输入**：`为什么最近一周下载量暴跌，是哪个应用导致的`

**输出**：

> **核心发现**：最近一周下载量波动主要来自微信，贡献了 38.4% 的变化。微信 Z-score=1.54，为异常值。
>
> | 应用 | 下载量 | 贡献占比 | 异常检测 |
> |------|--------|----------|----------|
> | 微信 | 709 万 | **38.4%** | ⚠️ Z=1.54 |
> | 抖音 | 453 万 | 24.5% | 正常 |
> | 王者荣耀 | 275 万 | 14.9% | 正常 |
>
> **建议**：排查微信是否存在版本更新或异常刷量行为；对 Z-score > 1.5 的渠道建立告警。

**输入**：`你好`

**输出**：`你好！我是数据分析助手，有什么想查的吗？😊`

## 架构

```
用户说 "为什么下载量跌了"
  │
  ▼
┌─ Orchestrator（Supervisor，纯代码状态机）──────────┐
│                                                     │
│  State: NEED_DATA → NEED_ANALYSIS → DONE            │
│                                                     │
│  Step 1: SQL Agent      → 查多维度数据               │
│  Step 2: Analysis Agent  → Pandas 归因 + 异常检测    │
│  Step 3: Chart Agent     → 生成 ECharts JSON        │
│  Step 4: Report Agent    → 撰写 Markdown 报告       │
│                                                     │
└─────────────────────────────────────────────────────┘
  │
  ▼
Streamlit Web — 对话界面 + 图表渲染 + 报告展示
```

## 快速开始

### 1. 环境

```bash
git clone https://github.com/Nullmethod0728/Datalens-ai.git
cd datalens-ai
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key
```

> 默认使用 DeepSeek。换成 OpenAI 只需改 `.env` 里两行，代码不动。

### 3. 运行

```bash
# 网页版（推荐）
streamlit run src/web/app.py

# 终端交互模式
python -X utf8 run.py

# 单次问答
python -X utf8 run.py "昨天的 PV 是多少"

# 归因分析
python -X utf8 run.py --analyze "为什么下载量下跌了"

# 完整报告
python -X utf8 run.py --report "最近一个月下载量趋势"
```

## 核心设计

### 1. 不是调 API，是给 LLM 装手

```
裸 LLM = 困在聊天框里的天才 → 碰不到任何系统外的东西

Agent = LLM + 工具（手）
  → execute_sql: 查数据库的手
  → pandas_analyzer: 做计算的手
  → chart_agent: 画图的手
  → report_agent: 写报告的手
```

### 2. Supervisor 是代码，不是 LLM

业界两种做法：

- ❌ 让 LLM 自己决定下一步干什么 → 幻觉、死循环、不可控
- ✅ 你写代码决定 → `orchestrator.py` 里写死状态机，LLM 负责任务执行

### 3. 安全不是信任 LLM

`sql_validator.py` 在执行前拦一道：不管 LLM 生成什么，先过黑名单。`DELETE`、`DROP`、`UPDATE` 一律拦截，没有任何例外。

### 4. 数据源一行切换

```python
# config.py — 改这一行，系统就跑在你自己的数据上
DATABASE_PATH = "data/demo_app_store.sqlite"  # → "/path/to/real.db"
```

## 项目结构

```
datalens-ai/
├── run.py                      # CLI 入口（问答/分析/报告/交互）
├── requirements.txt            # openai + streamlit + pandas + sklearn
├── .env.example                # 配置模板（.env 是真实 Key，不入库）
│
├── src/
│   ├── core/
│   │   ├── config.py           # 全局配置（LLM / 数据库路径）
│   │   ├── agent_loop.py       # Agent 核心循环（Function Calling）
│   │   ├── orchestrator.py     # Supervisor + 多 Agent 编排
│   │   ├── tool_registry.py    # 工具注册中心（说明书 + 执行分发）
│   │   └── memory.py           # 对话记忆管理
│   │
│   ├── agents/
│   │   ├── sql_agent.py        # Text-to-SQL（问题 → SQL → 翻译）
│   │   ├── analysis_agent.py   # 分析 Agent（数据 → 归因结论）
│   │   ├── chart_agent.py      # 图表 Agent（数据 → ECharts JSON）
│   │   └── report_agent.py     # 报告 Agent（分析+图表 → Markdown）
│   │
│   ├── tools/
│   │   ├── sql_executor.py     # SQLite 执行器
│   │   ├── sql_validator.py    # SQL 安全校验（黑名单 + 注入检测）
│   │   ├── pandas_analyzer.py  # Pandas 分析函数库（贡献度/异常/趋势）
│   │   └── generate_demo_db.py # Demo 数据生成器（2年，36500行）
│   │
│   └── web/
│       └── app.py              # Streamlit 前端（Chat + 图表 + 报告）
│
├── data/
│   └── demo_app_store.sqlite   # 模拟应用商店数据（5App × 5城市 × 730天）
│
├── prompts/
│   ├── schema_prompt.txt       # 表结构描述
│   └── fewshot_examples.txt    # Few-shot 示例库
│
└── tests/                      # 测试目录
```

## 开发路线（六阶段）

| 阶段 | 内容 | 核心文件 |
|------|------|------|
| 一 | 单轮 Text-to-SQL：人话 → SQL → 执行 → 翻译 | `sql_executor.py` `sql_agent.py` |
| 二 | Function Calling 改造：LLM 自己判断要不要查库 | `tool_registry.py` `agent_loop.py` |
| 三 | SQL 深度打磨：安全校验 + Schema 精简 + Few-shot + 错误重试 | `sql_validator.py` `schema_prompt.txt` |
| 四 | 分析 Agent 加入：查数据 → Pandas 归因 → 给结论 | `orchestrator.py` `analysis_agent.py` `pandas_analyzer.py` |
| 五 | 图表 + 报告：数据 → ECharts JSON → Markdown 报告 | `chart_agent.py` `report_agent.py` |
| 六 | Streamlit 前端：对话界面 + 图表渲染 + 报告展示 | `app.py` |

## 技术栈

| 层 | 技术 |
|------|------|
| LLM | DeepSeek（OpenAI 协议兼容，可任意切换） |
| SDK | openai Python SDK（Function Calling 模式） |
| 数据库 | SQLite + sqlite3 |
| 分析 | Pandas + scikit-learn |
| 图表 | LLM → ECharts JSON → streamlit-echarts |
| 前端 | Streamlit |
| 安全 | 关键词黑名单 + 注入检测 |

## 关键设计决策

如果你在面试中被问到「这个项目你设计了什么」，这些是值得展开的点：

| 决策 | 问题 | 方案 |
|------|------|------|
| 为什么 Supervisor 是代码不是 LLM | LLM 决策会幻觉、死循环、不可控 | `orchestrator.py` 写死状态机，LLM 只负责任务内部 |
| 为什么 Function Calling 不等同于 Agent | FC 只解决「LLM 调工具」，不解决「多步协作」 | 在 FC 之上加了 Supervisor 编排层 |
| 为什么 SQL 校验器不依赖 LLM 自查 | LLM 可能绕过自己说的规则 | 额外加一层关键词黑名单 + 注入检测 |
| 为什么 demo 数据造了 2 年 | 同比分析需要跨年对比 | 730 天，36500 行，支持所有分析维度 |
| 为什么 Chart Agent 生成 JSON 而不是图片 | JSON 可被前端灵活渲染，图片不能交互 | ECharts option JSON → streamlit-echarts 渲染 |

## License

MIT
