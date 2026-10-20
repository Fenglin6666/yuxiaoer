"""跨店排期：给每店分配带抖动的擦亮/日报时间，并触发每日同步。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any

import httpx

from yuxiaoer.core import config

from .registry import Shop, ShopRegistry

log = logging.getLogger("yuxiaoer.control.scheduler")


def shop_auth() -> tuple[str, str] | None:
    if config.CONSOLE_USER and config.CONSOLE_PASSWORD:
        return (config.CONSOLE_USER, config.CONSOLE_PASSWORD)
    return None


def jittered_time(base: str, shop_id: str, *, jitter_minutes: int = 20) -> str:
    """按 shop_id 确定性偏移，保证重启后时间不变，且各店错开。"""
    try:
        hour, minute = (int(part) for part in base.split(":", 1))
    except (ValueError, AttributeError):
        hour, minute = 10, 5
    digest = hashlib.sha1(shop_id.encode("utf-8")).digest()
    offset = int.from_bytes(digest[:2], "big") % (jitter_minutes * 2 + 1) - jitter_minutes
    total = (hour * 60 + minute + offset) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


class ShopScheduler:
    def __init__(self, registry: ShopRegistry):
        self.registry = registry
        self._applied: set[str] = set()
        self._last_sync: dict[str, str] = {}
        self._task: asyncio.Task | None = None
        self._stopping = False

    def invalidate(self, shop_id: str) -> None:
        self._applied.discard(shop_id)

    def base_url(self, shop: Shop) -> str:
        return f"http://127.0.0.1:{shop.port}"

    async def _request(self, shop: Shop, method: str, path: str, json: dict | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0, auth=shop_auth()) as client:
            response = await client.request(method, f"{self.base_url(shop)}{path}", json=json)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {"ok": True}

    async def apply_schedule(self, shop: Shop) -> dict[str, Any]:
        polish = jittered_time(shop.polish_time, shop.id)
        report = jittered_time(shop.daily_report_time, shop.id)
        await self._request(shop, "PATCH", "/api/patrol/jobs/polish", {"local_time": polish})
        await self._request(shop, "PATCH", "/api/patrol/jobs/daily_report", {"local_time": report})
        self._applied.add(shop.id)
        return {"shop": shop.id, "polish": polish, "daily_report": report}

    async def sync_shop_items(self, shop: Shop) -> dict[str, Any]:
        status = await self._request(shop, "GET", "/api/status")
        account = (status.get("account") or {}) if isinstance(status, dict) else {}
        account_id = account.get("id")
        if not account_id:
            return {"shop": shop.id, "ok": False, "error": "no active account"}
        await self._request(shop, "POST", f"/api/accounts/{account_id}/sync", {})
        return {"shop": shop.id, "ok": True, "account": account_id}

    async def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(config.TZ)
        for shop in self.registry.list(is_admin=True):
            if not shop.enabled:
                continue
            try:
                if shop.id not in self._applied:
                    await self.apply_schedule(shop)
                sync_at = jittered_time(shop.sync_time, shop.id, jitter_minutes=30)
                hour, minute = (int(part) for part in sync_at.split(":", 1))
                due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                today = now.strftime("%Y-%m-%d")
                if now >= due and self._last_sync.get(shop.id) != today:
                    result = await self.sync_shop_items(shop)
                    if result.get("ok"):
                        self._last_sync[shop.id] = today
                    else:
                        log.warning("auto sync skipped: %s", result)
            except Exception as exc:  # noqa: BLE001
                log.warning("schedule shop %s failed: %s", shop.id, exc)

    async def loop(self) -> None:
        while not self._stopping:
            await self.tick()
            await asyncio.sleep(60)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self.loop(), name="shop-scheduler")

    async def shutdown(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
