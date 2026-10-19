"""反检测 / 风控熔断。

平台写动作出现"被挤爆/滑块/验证码/频繁"等信号时：
- 立即熔断该账号的写队列（默认 30 分钟）；
- 记 P0 告警 + 事件；
- 期间任何写操作 fail-fast，不带病重试放大风控。

配合 WriteQueue 的串行、2–5s 抖动、指数退避与账号错开刷新。
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from yuxiaoer.core import config
from yuxiaoer.seller.notifications.alerts import AlertService
from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.core.util import human_time, iso, now_utc, parse_iso

log = logging.getLogger("yuxiaoer.risk")


class RiskControlOpen(Exception):
    def __init__(self, until: str | None = None, reason: str = ""):
        self.until = until
        self.reason = reason
        super().__init__(f"风控熔断中，暂停平台写操作至 {human_time(until) if until else '稍后'}（{reason}）")


class RiskGuard:
    def __init__(self, db: Database, bus: EventBus):
        self.db = db
        self.bus = bus
        self.alerts: AlertService | None = None
        self.open_until: str | None = None
        self.reason: str = ""
        self.triggered_at: str | None = None
        self.count: int = 0
        self._loaded = False

    async def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self.open_until = await self.db.fetchval("SELECT value FROM settings WHERE key='risk_open_until'")
        self.reason = await self.db.fetchval("SELECT value FROM settings WHERE key='risk_reason'") or ""
        self.triggered_at = await self.db.fetchval("SELECT value FROM settings WHERE key='risk_triggered_at'")
        self.count = int(await self.db.fetchval("SELECT value FROM settings WHERE key='risk_count'", default=0) or 0)

    async def _persist(self) -> None:
        pairs = {
            "risk_open_until": self.open_until or "",
            "risk_reason": self.reason or "",
            "risk_triggered_at": self.triggered_at or "",
            "risk_count": str(self.count),
        }
        for key, value in pairs.items():
            await self.db.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value)
            )

    async def is_open(self) -> bool:
        await self.load()
        if not self.open_until:
            return False
        if parse_iso(self.open_until) <= now_utc():
            await self.reset(reason="cooldown_elapsed", silent=True)
            return False
        return True

    async def ensure_closed(self) -> None:
        if await self.is_open():
            raise RiskControlOpen(self.open_until, self.reason)

    async def trigger(self, reason: str, *, minutes: int | None = None) -> dict[str, Any]:
        await self.load()
        minutes = minutes or int(await self.db.fetchval(
            "SELECT value FROM settings WHERE key='risk_cooldown_minutes'", default=30
        ) or 30)
        until = iso(now_utc() + timedelta(minutes=max(1, minutes)))
        self.open_until = until
        self.reason = reason[:300]
        self.triggered_at = iso()
        self.count += 1
        await self._persist()
        await self.bus.emit(
            "risk.triggered",
            {"reason": self.reason, "until": until, "count": self.count},
        )
        if self.alerts:
            await self.alerts.create(
                "P0", "risk_control", "风控熔断：平台写操作已暂停",
                f"检测到风控信号：{self.reason}。已暂停写操作至 {human_time(until)}，"
                "期间不会重试放大风险。请检查账号或手动过验证后再恢复。",
                dedupe_minutes=10,
            )
        return await self.status()

    async def observe_error(self, exc: Exception) -> None:
        text = f"{type(exc).__name__}: {exc}"
        if any(p.lower() in text.lower() for p in config.RISK_SIGNAL_PATTERNS):
            await self.trigger(text)

    async def reset(self, reason: str = "manual", *, silent: bool = False) -> dict[str, Any]:
        await self.load()
        self.open_until = ""
        self.reason = ""
        self.triggered_at = ""
        await self._persist()
        if not silent:
            await self.bus.emit("risk.reset", {"reason": reason})
        return await self.status()

    async def status(self) -> dict[str, Any]:
        opened = await self.is_open()
        if not opened:
            until = None
        else:
            until = self.open_until
        return {
            "open": opened,
            "until": until,
            "until_human": human_time(until) if until else "—",
            "reason": self.reason if opened else "",
            "triggered_at": self.triggered_at,
            "triggered_human": human_time(self.triggered_at) if self.triggered_at else "—",
            "count": self.count,
            "cooldown_minutes": int(await self.db.fetchval(
                "SELECT value FROM settings WHERE key='risk_cooldown_minutes'", default=30
            ) or 30),
            "write_interval_seconds": 2.0,
            "write_jitter_seconds": 1.5,
            "refresh_jitter_hours": list(config.SESSION_H5_REFRESH_HOURS),
            "ws_refresh_hours": list(config.SESSION_WS_REFRESH_HOURS),
            "account_stagger_seconds": list(config.SESSION_ACCOUNT_STAGGER_SECONDS),
            "human_typing": str(await self.db.fetchval(
                "SELECT value FROM settings WHERE key='human_typing'", default="0"
            ) or "0") in ("1", "true", "on"),
            "signals": list(config.RISK_SIGNAL_PATTERNS),
        }

    async def recent_events(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT * FROM events WHERE topic LIKE 'risk.%' ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]
