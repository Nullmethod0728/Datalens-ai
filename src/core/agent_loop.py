"""
Agent 核心循环 — Function Calling 模式
----------------------------------------
阶段二的核心：LLM 自己决定要不要查数据库、什么时候查、查什么。

流程:
  while True:
      用户输入 → 追加到消息列表
      while True:
          调 LLM（带工具定义）
          if LLM 返回 tool_call → 执行工具 → 结果追加回消息 → 继续循环
          if LLM 返回普通文本 → 输出 → 结束本轮

对比阶段一:
  阶段一: 用户问题 → 强制走 SQL（说"你好"也硬查）
  阶段二: 用户说"你好" → LLM 判断无需工具 → 直接回复
         用户问数据 → LLM 返回 tool_call → Python 执行 → 喂回结果
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
from src.core.tool_registry import TOOL_DEFINITIONS, execute_tool
from src.tools.sql_executor import list_tables, get_table_schema


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
# System Prompt
# ============================================================
def _build_system_prompt() -> str:
    """
    构建 system prompt: 告诉 LLM 它是谁、有什么工具、数据库长什么样。
    """
    tables = list_tables(DATABASE_PATH)
    schema_parts = []
    for t in tables:
        schema_sql = get_table_schema(DATABASE_PATH, t)
        schema_parts.append(f"### {t}\n```sql\n{schema_sql}\n```")

    schema_text = "\n\n".join(schema_parts) if schema_parts else "（暂无表）"

    return f"""\
你是一个智能数据分析助手，专门帮用户查询和分析应用商店数据。

## 数据库结构
{schema_text}

## 你的能力
你有以下工具可用（无需向用户确认，直接调用）：
- `execute_sql`: 执行 SQL 查询，获取数据
- `get_table_schema`: 查看某张表的字段结构
- `list_tables`: 列出所有表名

## 行为规则
1. **需要查数据时** → 直接调用工具，拿到结果后翻译成人话
2. **不需要查数据时** → 直接文字回复，不调用任何工具
   - 用户说"你好""谢谢""你是什么模型"之类的话 → 直接回复
   - 用户的问题和数据库完全无关 → 直接回复
3. 调用 execute_sql 时，只生成 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DROP/ALTER
4. 日期函数使用 SQLite 语法（date('now')、strftime 等）
5. 用户可能用模糊时间词（"昨天""上周""最近7天"），你需要转换为具体 SQL 条件
6. 拿到数据后，用中文简洁地告诉用户结论，不需要解释你用了什么 SQL
"""


# ============================================================
# 核心循环
# ============================================================
MAX_TOOL_ROUNDS = 5  # 每轮对话最多调用工具次数，防止死循环


def run_conversation():
    """
    启动交互式对话（在终端里跑）。
    """
    messages = [{"role": "system", "content": _build_system_prompt()}]

    print("=" * 50)
    print("  DataLens AI — Agent 模式（阶段二）")
    print("  LLM 自主判断：闲聊直接回 / 数据问题自动查库")
    print("  输入 exit 退出")
    print("=" * 50)

    try:
        while True:
            user_input = input("\n👤 你: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("再见!")
                break

            messages.append({"role": "user", "content": user_input})

            # ---- 内层循环：工具调用 ----
            for _ in range(MAX_TOOL_ROUNDS):
                response = _get_client().chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                msg = response.choices[0].message

                # 情况 A: LLM 要调工具
                if msg.tool_calls:
                    # 先把 assistant 消息（含 tool_calls）加入历史
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    })

                    had_error = False
                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            args = {}

                        print(f"  🔧 调用工具: {tool_name}")

                        result_str = execute_tool(tool_name, args)

                        if result_str.startswith("SQL 执行失败") or result_str.startswith("未知工具"):
                            had_error = True

                        # 工具结果追加到消息列表
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str,
                        })

                    # 如果工具执行报错，让 LLM 修正后重试；否则就继续
                    if not had_error:
                        continue

                # 情况 B: LLM 直接回复文字
                else:
                    messages.append({"role": "assistant", "content": msg.content})
                    print(f"\n🤖: {msg.content}")
                    break

            else:
                # for 循环没 break → 工具调用轮次耗尽
                print("\n⚠️ 工具调用次数过多，已终止本轮。请换个方式提问。")
    except KeyboardInterrupt:
        print("\n再见!")
