"""
对话记忆管理
------------
存住关键上下文，让多轮对话不「失忆」。

结构是一个全局 dict，会话级别（不持久化到磁盘，重启就清空）。

key 设计:
  - "last_topic":    用户上一轮问的主题（如 "PV"）
  - "last_date":     用户上一轮提的时间（如 "昨天"）
  - "last_sql":      上一轮执行的 SQL
  - "last_result":   上一轮的查询结果（QueryResult 或 DataFrame）
  - "last_analysis": 上一轮的分析结果（dict）
  - "history":       最近 N 轮的对话摘要列表
"""

from typing import Any


class Memory:
    """简单的键值存储，记录对话关键信息。"""

    def __init__(self):
        self._store: dict[str, Any] = {
            "last_topic": "",
            "last_date": "",
            "last_sql": "",
            "last_result": None,
            "last_analysis": None,
            "history": [],  # 列表，每个元素 {"question": ..., "answer_summary": ...}
        }

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def add_history(self, question: str, summary: str) -> None:
        """追加一轮对话记录，最多保留 10 轮。"""
        self._store["history"].append({
            "question": question,
            "answer_summary": summary,
        })
        if len(self._store["history"]) > 10:
            self._store["history"].pop(0)

    def get_context_for_llm(self) -> str:
        """
        从记忆中构建一段文本，可以拼进 LLM 的 system prompt，
        让 LLM「记住」之前的对话。
        """
        if not self._store["history"]:
            return "（这是第一轮对话，无历史记录）"

        lines = ["## 对话历史（最近几轮）"]
        for h in self._store["history"][-5:]:
            lines.append(f"- 用户问: {h['question']}")
            lines.append(f"  回答摘要: {h['answer_summary']}")
        return "\n".join(lines)

    def clear(self) -> None:
        """重置记忆。"""
        self._store = {
            "last_topic": "",
            "last_date": "",
            "last_sql": "",
            "last_result": None,
            "last_analysis": None,
            "history": [],
        }


# 全局单例
_memory = Memory()


def get_memory() -> Memory:
    return _memory
