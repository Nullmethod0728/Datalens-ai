"""
Agent 核心循环 — Function Calling 模式（阶段三增强）
----------------------------------------------------
阶段二: LLM 自己决定要不要查数据库
阶段三: + Schema 精简 + Few-shot 示例 + SQL 安全校验 + 错误重试

流程:
  while True:
      用户输入 → 追加到消息列表
      while True:
          调 LLM（带工具定义）
          if LLM 返回 tool_call → 执行工具（含安全校验） → 结果追加回消息 → 继续
          if LLM 返回普通文本 → 输出 → 结束本轮
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
)
from src.core.tool_registry import TOOL_DEFINITIONS, execute_tool


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
    """从 prompts/ 目录加载文本文件，文件不存在则返回空字符串。"""
    filepath = _PROMPTS_DIR / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


# ============================================================
# System Prompt
# ============================================================
def _build_system_prompt() -> str:
    """构建 system prompt: LLM 身份 + 数据库结构 + Few-shot + 行为规则。"""
    from datetime import date
    today = date.today().isoformat()

    schema_prompt = _load_prompt_file("schema_prompt.txt")
    fewshot_prompt = _load_prompt_file("fewshot_examples.txt")

    return f"""\
你是一个智能数据分析助手，专门帮用户查询和分析应用商店数据。

今天是 {today}。用户说的「昨天」「上周」「本月」「去年」等时间词请基于这个日期计算。

## 数据库结构
{schema_prompt}

## 查询示例（请模仿以下 SQL 风格）
{fewshot_prompt}

## 你的工具
你有以下工具可用（无需向用户确认，直接调用）：
- `execute_sql`: 执行 SQL 查询，获取数据。只支持 SELECT。
- `get_table_schema`: 查看某张表的字段结构
- `list_tables`: 列出所有表名

## 行为规则
1. **需要查数据时** → 直接调用 execute_sql，拿到结果后翻译成人话
2. **不需要查数据时** → 直接文字回复，不调用任何工具
3. 只生成 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DROP/ALTER
4. 日期函数使用 SQLite 语法（date('now')、strftime 等）
5. 如果 SQL 执行报错，仔细看错误信息，修正后重试（最多重试 3 次）
6. 拿到数据后，用中文简洁地告诉用户结论
"""


# ============================================================
# 核心循环
# ============================================================
MAX_TOOL_ROUNDS = 5          # 每轮最多调工具次数
MAX_SQL_RETRIES = 3          # SQL 执行失败最多重试次数


def run_conversation():
    """启动交互式对话。"""
    messages = [{"role": "system", "content": _build_system_prompt()}]

    print("=" * 50)
    print("  DataLens AI — Agent 模式（阶段三）")
    print("  SQL 安全校验 + Few-shot + 错误重试")
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

            sql_error_count = 0  # 本轮的 SQL 错误计数

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

                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            args = {}

                        print(f"  🔧 调用工具: {tool_name}")

                        result_str = execute_tool(tool_name, args)

                        # 阶段三: 统计 SQL 错误，超限则终止
                        is_sql_error = (
                            tool_name == "execute_sql"
                            and ("SQL 执行失败" in result_str
                                 or "禁止使用" in result_str
                                 or "只允许 SELECT" in result_str
                                 or "禁止执行多条" in result_str)
                        )
                        if is_sql_error:
                            sql_error_count += 1
                            if sql_error_count >= MAX_SQL_RETRIES:
                                result_str += (
                                    f"\n\n⚠️ 这已经是第 {sql_error_count} 次 SQL 错误了。"
                                    "请不要再重试，直接告诉用户「这个问题我暂时查不了」。"
                                )

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str,
                        })

                # 情况 B: LLM 直接回复文字
                else:
                    messages.append({"role": "assistant", "content": msg.content})
                    print(f"\n🤖: {msg.content}")
                    break

            else:
                print("\n⚠️ 工具调用次数过多，已终止本轮。请换个方式提问。")
    except KeyboardInterrupt:
        print("\n再见!")
