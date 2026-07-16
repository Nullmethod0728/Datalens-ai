"""
DataLens AI — 测试入口
=======================
用法:
    python run.py                              # 交互模式（Function Calling）
    python run.py "昨天的 PV 是多少"            # 单次问答
    python run.py --analyze "为什么下载量跌了"  # 分析模式（SQL→分析→结论）
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
    validate()

    args = sys.argv[1:]

    if not args:
        # 交互模式 → agent_loop
        from src.core.agent_loop import run_conversation
        run_conversation()

    elif args[0] == "--analyze":
        # 分析模式 → orchestrator（阶段四）
        if len(args) < 2:
            print("用法: python run.py --analyze \"为什么下载量下跌了\"")
            return
        from src.core.orchestrator import run_analysis
        question = " ".join(args[1:])
        answer = run_analysis(question)
        print(answer)

    else:
        # 单次问答 → sql_agent（轻量）
        from src.agents.sql_agent import ask
        question = " ".join(args)
        answer = ask(question)
        print(answer)


if __name__ == "__main__":
    main()
