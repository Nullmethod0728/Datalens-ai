"""
DataLens AI — 测试入口
=======================
用法:
    python run.py "昨天的 PV 是多少"   # 单次问答
    python run.py                      # 交互模式（阶段二 Function Calling）
"""

import sys
import os

# Windows 终端 GBK → UTF-8，否则中文乱码
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# 确保项目根目录在 Python Path 中
from pathlib import Path
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.core.config import validate


def main():
    # 启动校验
    validate()

    if len(sys.argv) < 2:
        # 交互模式 → 使用 agent_loop（阶段二）
        from src.core.agent_loop import run_conversation
        run_conversation()
    else:
        # 单次问答 → 使用 sql_agent（轻量，一轮结束）
        from src.agents.sql_agent import ask
        question = " ".join(sys.argv[1:])
        answer = ask(question)
        print(answer)


if __name__ == "__main__":
    main()
