"""全局配置：路径、通道模式、护栏参数。

环境变量优先，其次读取项目根目录 `.env`。
所有时间以 UTC 存储，展示时统一转成 Asia/Shanghai（UTC+8）。
"""

from __future__ import annotations

import os
import re
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

_DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
SHOPS_DIR = Path(os.getenv("YUXIAOER_SHOPS_DIR", _DEFAULT_DATA_DIR / "shops"))


def normalize_shop_id(value: str | None) -> str:
    """店铺 ID 只允许字母/数字/下划线/短横线，避免路径穿越。"""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", (value or "").strip())[:40]
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "default"


def shop_data_dir(shop_id: str) -> Path:
    if shop_id == "default":
        return _DEFAULT_DATA_DIR
    return SHOPS_DIR / shop_id


SHOP_ID = normalize_shop_id(os.getenv("YUXIAOER_SHOP_ID", "default"))
if SHOP_ID == "default":
    DATA_DIR = Path(os.getenv("YUXIAOER_DATA_DIR", shop_data_dir("default")))
    DB_PATH = Path(os.getenv("YUXIAOER_DB", DATA_DIR / "yuxiaoer.db"))
else:
    # 非默认店不能用全局 DATA_DIR/DB 覆盖，否则所有店会写进同一个库。
    DATA_DIR = Path(os.getenv("YUXIAOER_SHOP_DATA_DIR", shop_data_dir(SHOP_ID)))
    DB_PATH = Path(os.getenv("YUXIAOER_SHOP_DB", DATA_DIR / "yuxiaoer.db"))

HOST = os.getenv("YUXIAOER_HOST", "127.0.0.1")
PORT = int(os.getenv("YUXIAOER_PORT", "8787"))
# 邮件里的确认链接使用这个地址；手机/其他设备打开时改成局域网或公网地址。
PUBLIC_BASE_URL = os.getenv("YUXIAOER_PUBLIC_URL", f"http://{HOST}:{PORT}").rstrip("/")

# 控制台 Basic Auth（可选）：两项都非空才启用；留空时仍只依赖 127.0.0.1 绑定。
CONSOLE_USER = os.getenv("YUXIAOER_CONSOLE_USER", "").strip()
CONSOLE_PASSWORD = os.getenv("YUXIAOER_CONSOLE_PASSWORD", "").strip()

TZ = timezone(timedelta(hours=8))
APP_NAME = "鱼小二"
APP_TAGLINE = "托管客服 · 24h 在线"

# ---- 通道 ----
# 只有原生闲鱼通道；没有 mock 回退
PLATFORM_MODE = "xianyu"

# ---- 原生闲鱼协议 / 公开接口 ----
# 外部系统调用 /api/v1/external/* 的共享秘钥；生产环境必须改掉。
EXTERNAL_SECRET_KEY = os.getenv("YUXIAOER_EXTERNAL_SECRET", "yx-local-secret")
EMAIL_ACTION_SECRET = os.getenv("YUXIAOER_EMAIL_SECRET", EXTERNAL_SECRET_KEY)
XY_APP_KEY = os.getenv("XY_APP_KEY", "34839810")
XY_APP_SECRET = os.getenv("XY_APP_SECRET", "")
XY_API_BASE = os.getenv("XY_API_BASE", "https://h5api.m.goofish.com").rstrip("/")
XY_WS_URL = os.getenv("XY_WS_URL", "wss://wss-goofish.dingtalk.com/")
XY_ORIGIN = os.getenv("XY_ORIGIN", "https://www.goofish.com")
XY_USER_AGENT = os.getenv(
    "XY_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)
XY_ORDER_SYNC_SECONDS = int(os.getenv("XY_ORDER_SYNC_SECONDS", "60"))
AMAP_KEY = os.getenv("AMAP_KEY", "").strip()

# ---- LLM（可选，OpenAI 兼容端点） ----
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4.6")
LLM_ENABLED = os.getenv("LLM_ENABLED", "auto").strip().lower()  # auto | on | off
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))
LLM_COOLDOWN_SECONDS = int(os.getenv("LLM_COOLDOWN_SECONDS", "300"))

# ---- 值守/护栏 ----
BUYER_MAX_STEPS = 6
SELLER_MAX_STEPS = 8
RATE_LIMIT_PER_MINUTE = int(os.getenv("YUXIAOER_REPLY_RATE_LIMIT", "12"))
NIGHT_START_HOUR = 1
NIGHT_END_HOUR = 7
NIGHT_DELAY_TO = "07:30"
CONFIRM_TTL_MINUTES = 30

# ---- 调度 ----
SCHEDULER_TICK_SECONDS = 5
OUTBOX_TICK_SECONDS = 0.8
HEARTBEAT_SECONDS = 30 * 60
LINK_CHECK_SECONDS = 6 * 60 * 60
DAILY_REPORT_HOUR = 21
POLISH_WINDOW_START = "09:30"
POLISH_WINDOW_END = "10:30"

VERSION = "0.3.1"
SHOP_NAME = os.getenv("YUXIAOER_SHOP_NAME", "我的闲鱼小店")
OWNER_NAME = os.getenv("YUXIAOER_OWNER_NAME", "店主")
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "").strip()
BARK_URL = os.getenv("BARK_URL", "").strip()
SERVERCHAN_KEY = os.getenv("SERVERCHAN_KEY", "").strip()
NTFY_URL = os.getenv("NTFY_URL", "").strip()
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "yuxiaoer").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "").strip()
GOTIFY_URL = os.getenv("GOTIFY_URL", "").strip()
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN", "").strip()

# ---- 账号 / 会话保活（参考社区 token 刷新纪律） ----
SESSION_H5_REFRESH_HOURS = (1.5, 2.5)
SESSION_WS_REFRESH_HOURS = (10.0, 14.0)
SESSION_COOKIE_CHECK_MINUTES = 30
SESSION_ACCOUNT_STAGGER_SECONDS = (2.0, 5.0)
SESSION_QR_TTL_SECONDS = 180
RISK_SIGNAL_PATTERNS = (
    "被挤爆", "挤爆", "风控", "滑块", "验证码", "频繁", "限制", "429",
    "risk", "captcha", "rate limit",
)

DEFAULT_SETTINGS: dict[str, str] = {
    "floor_discount_pct": "85",
    "publish_default_price": "990",
    "publish_default_address": "杭州市",
    "night_mode": "1",
    "llm_enabled": "1" if LLM_ENABLED == "on" and LLM_API_KEY else "0",  # UI 开关；默认规则模式保证可跑
    "shop_name": SHOP_NAME,
    "owner_name": OWNER_NAME,
    "bargain_max_rounds": "3",
    "auto_review": "0",
    "human_typing": "0",
    "risk_cooldown_minutes": "30",
    "polish_time": "10:05",
    "daily_report_time": "21:00",
}

# UI 可修改的键（白名单）
EDITABLE_SETTINGS = {
    "floor_discount_pct",
    "night_mode",
    "llm_enabled",
    "shop_name",
    "owner_name",
    "bargain_max_rounds",
    "auto_review",
    "human_typing",
    "risk_cooldown_minutes",
    "polish_time",
    "daily_report_time",
}

