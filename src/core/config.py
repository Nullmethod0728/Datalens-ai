"""
DataLens AI 全局配置
-------------------
API Key 优先从环境变量读取，其次从项目根目录的 .env 文件加载。
其他配置（模型名、数据库路径等）集中在这里管理。
"""

import os
from pathlib import Path

# 优先加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

# ============================================================
# 项目根目录
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ============================================================
# LLM 配置
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

# ============================================================
# 调用参数
# ============================================================
TEMPERATURE = 0.1        # SQL 生成需要确定性，温度设低
MAX_TOKENS = 4096

# ============================================================
# 数据库配置
# ============================================================
DATABASE_PATH = str(PROJECT_ROOT / "data" / "demo_app_store.sqlite")

# ============================================================
# 验证配置有效性
# ============================================================
def validate():
    """启动时校验必要配置是否齐全。"""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "未设置 OPENAI_API_KEY，请在环境变量中配置或创建 .env 文件。\n"
            "  export OPENAI_API_KEY=sk-xxxx"
        )
    if not Path(DATABASE_PATH).exists():
        raise FileNotFoundError(f"数据库文件不存在: {DATABASE_PATH}")
