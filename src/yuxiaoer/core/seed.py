"""首启只写真实运行所需的默认配置，不生成演示账号/商品/订单/会话。"""

from __future__ import annotations

from yuxiaoer.core import config
from yuxiaoer.core.db import Database
from yuxiaoer.core.util import dumps, iso, next_local_time


async def seed_once(db: Database) -> None:
    now = iso()
    for key, value in config.DEFAULT_SETTINGS.items():
        await db.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
            (key, str(value)),
        )
    jobs = (
        ("heartbeat", "账号心跳 / 掉线重连", 1800, None, iso(next_local_time("09:00"))),
        ("link_check", "链接巡检", 21600, None, iso(next_local_time("03:00"))),
        ("polish", "每日擦亮", None, {"local_time": config.DEFAULT_SETTINGS["polish_time"]},
         iso(next_local_time(config.DEFAULT_SETTINGS["polish_time"]))),
        ("daily_report", "每日经营日报", None,
         {"local_time": config.DEFAULT_SETTINGS["daily_report_time"]},
         iso(next_local_time(config.DEFAULT_SETTINGS["daily_report_time"]))),
    )
    for name, title, interval, schedule, next_run in jobs:
        await db.execute(
            """INSERT OR IGNORE INTO patrol_jobs(name,title,enabled,interval_seconds,schedule_json,
               next_run_at,last_status,last_detail)
               VALUES(?,?,1,?,?,?,?,?)""",
            (name, title, interval, dumps(schedule) if schedule else None, next_run, None, None),
        )
    # 站内日志渠道是唯一永远可用的真实投递通道
    await db.execute(
        """INSERT OR IGNORE INTO notify_channels(id,kind,name,config_json,enabled,min_level,created_at,updated_at)
           VALUES('ch_log','log','站内投递日志','{}',1,'P1',?,?)""",
        (now, now),
    )
