"""
生成 demo 应用商店数据集
------------------------
创建 data/demo_app_store.sqlite，包含应用商店模拟数据。
"""

import sqlite3
import random
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "demo_app_store.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

random.seed(42)  # 可复现

# ============================================================
# 数据定义
# ============================================================
APPS = [
    ("抖音",     "视频",  [800000, 1200000], [600000, 900000], [30000, 80000], [50000, 150000]),
    ("王者荣耀", "游戏",  [500000, 900000],  [350000, 600000], [15000, 50000], [20000, 80000]),
    ("微信",     "社交",  [900000, 1500000], [750000, 1100000],[50000, 120000], [80000, 200000]),
    ("滴滴出行", "工具",  [200000, 400000],  [120000, 250000], [8000, 25000],  [10000, 35000]),
    ("QQ音乐",   "音乐",  [350000, 550000],  [250000, 400000], [20000, 45000],  [30000, 70000]),
]

CITIES = ["北京", "上海", "广州", "深圳", "杭州"]
DEVICES = ["iOS", "Android"]
START_DATE = date(2026, 6, 16)
DAYS = 30

# ============================================================
# 建表
# ============================================================
conn = sqlite3.connect(str(DB_PATH))
conn.execute("DROP TABLE IF EXISTS app_metrics")

conn.execute("""
    CREATE TABLE app_metrics (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        date        TEXT    NOT NULL,  -- YYYY-MM-DD
        app_name    TEXT    NOT NULL,  -- 应用名称
        category    TEXT    NOT NULL,  -- 分类
        city        TEXT    NOT NULL,  -- 城市
        device_type TEXT    NOT NULL,  -- iOS / Android
        pv          INTEGER NOT NULL,  -- 页面浏览量
        uv          INTEGER NOT NULL,  -- 独立访客数
        downloads   INTEGER NOT NULL,  -- 下载量
        revenue     REAL    NOT NULL,  -- 收入（元）
        new_users   INTEGER NOT NULL,  -- 新增用户
        active_users INTEGER NOT NULL  -- 活跃用户
    )
""")

conn.execute("""
    CREATE TABLE apps (
        app_name TEXT PRIMARY KEY,
        category TEXT NOT NULL
    )
""")

# ============================================================
# 造数据
# ============================================================
rows = []
for i in range(DAYS):
    d = START_DATE + timedelta(days=i)
    day_of_week = d.weekday()  # 0=Monday, 6=Sunday
    is_weekend = 1.3 if day_of_week >= 5 else 1.0  # 周末流量更高
    trend = 1.0 + i * 0.005  # 微幅上升趋势

    for app_name, category, pv_range, uv_range, dl_range, rev_range in APPS:
        for city in CITIES:
            for device in DEVICES:
                base_pv = random.randint(*pv_range)
                base_uv = random.randint(*uv_range)
                base_dl = random.randint(*dl_range)
                base_rev = random.randint(*rev_range)

                city_factor = {
                    "北京": 1.0, "上海": 1.05, "广州": 0.85,
                    "深圳": 0.9, "杭州": 0.75
                }[city]
                device_factor = 0.7 if device == "Android" else 0.3
                noise = random.uniform(0.85, 1.15)

                factor = is_weekend * trend * city_factor * noise

                pv = max(0, int(base_pv * factor))
                uv = max(0, int(base_uv * factor * device_factor / 0.5))
                downloads = max(0, int(base_dl * factor * device_factor / 0.5))
                revenue = round(max(0, base_rev * factor * device_factor / 0.5), 2)
                new_users = max(0, int(downloads * random.uniform(0.3, 0.7)))
                active_users = max(0, int(uv * random.uniform(0.6, 0.9)))

                rows.append((
                    d.isoformat(), app_name, category, city, device,
                    pv, uv, downloads, revenue, new_users, active_users
                ))

conn.executemany(
    "INSERT INTO app_metrics (date, app_name, category, city, device_type, pv, uv, downloads, revenue, new_users, active_users) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    rows,
)

conn.executemany(
    "INSERT INTO apps (app_name, category) VALUES (?, ?)",
    [(name, cat) for name, cat, *_ in APPS],
)

conn.commit()

# ============================================================
# 验证
# ============================================================
count = conn.execute("SELECT COUNT(*) FROM app_metrics").fetchone()[0]
print(f"[OK] 已创建 {DB_PATH}")
print(f"   app_metrics 表: {count} 行")
print(f"   apps 表: {conn.execute('SELECT COUNT(*) FROM apps').fetchone()[0]} 行")
print(f"   日期范围: {START_DATE} ~ {START_DATE + timedelta(days=DAYS-1)}")

# 预览几条
print("\n前 3 行预览:")
conn.row_factory = sqlite3.Row
for row in conn.execute(
    "SELECT date, app_name, city, device_type, pv, uv, downloads, revenue "
    "FROM app_metrics LIMIT 3"
):
    print(f"   {row['date']} | {row['app_name']:6s} | {row['city']:4s} | "
          f"{row['device_type']:7s} | PV={row['pv']:>10,} | UV={row['uv']:>9,} | "
          f"DL={row['downloads']:>7,} | 收入={row['revenue']:>10,.2f}")

conn.close()
