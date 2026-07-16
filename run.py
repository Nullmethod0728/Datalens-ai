"""
DataLens AI — 阶段一测试入口
=============================
用法:
    python run.py "昨天的 PV 是多少"
    python run.py     # 不带参数进入交互模式
"""

import sys

# 确保项目根目录在 Python Path 中
from pathlib import Path
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.core.config import validate
from src.agents.sql_agent import ask


def main():
    # 启动校验
    validate()

    # 交互模式
    if len(sys.argv) < 2:
        print("=" * 50)
        print("  DataLens AI — Text-to-SQL  (阶段一)")
        print("  输入问题，按 Enter 发送，Ctrl+C 退出")
        print("=" * 50)
        try:
            while True:
                question = input("\n> ").strip()
                if not question:
                    continue
                if question.lower() in ("exit", "quit", "q"):
                    print("再见!")
                    break
                print()
                answer = ask(question)
                print(answer)
                print()
        except KeyboardInterrupt:
            print("\n再见!")
    else:
        # 单次问答
        question = " ".join(sys.argv[1:])
        answer = ask(question)
        print(answer)


if __name__ == "__main__":
    main()
