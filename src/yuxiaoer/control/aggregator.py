"""跨店状态、告警、日报汇总。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .registry import Shop


def shop_auth() -> tuple[str, str] | None:
    from yuxiaoer.core import config
    if config.CONSOLE_USER and config.CONSOLE_PASSWORD:
        return (config.CONSOLE_USER, config.CONSOLE_PASSWORD)
    return None


class ShopAggregator:
    def base_url(self, shop: Shop) -> str:
        return f"http://127.0.0.1:{shop.port}"

    async def _get(self, shop: Shop, path: str) -> Any:
        try:
            async with httpx.AsyncClient(timeout=4.0, auth=shop_auth()) as client:
                response = await client.get(f"{self.base_url(shop)}{path}")
                if response.status_code != 200:
                    return {"error": f"HTTP {response.status_code}"}
                return response.json()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)[:200]}

    async def shop_overview(self, shop: Shop) -> dict[str, Any]:
        status, alerts = await asyncio.gather(
            self._get(shop, "/api/status"),
            self._get(shop, "/api/alerts?status=open&limit=50"),
        )
        open_alerts = alerts if isinstance(alerts, list) else []
        return {
            "id": shop.id,
            "name": shop.name,
            "port": shop.port,
            "owner": shop.owner,
            "status": status,
            "open_alerts": open_alerts,
            "online": not (isinstance(status, dict) and status.get("error")),
        }

    async def overview(self, shops: list[Shop]) -> dict[str, Any]:
        rows = await asyncio.gather(*(self.shop_overview(shop) for shop in shops))
        return {
            "shops": rows,
            "total": len(rows),
            "online": sum(1 for row in rows if row["online"]),
            "alerts": sum(len(row["open_alerts"]) for row in rows),
        }

    async def alerts(self, shops: list[Shop], status: str = "open") -> list[dict[str, Any]]:
        async def fetch(shop: Shop) -> list[dict[str, Any]]:
            data = await self._get(shop, f"/api/alerts?status={status}&limit=50")
            if not isinstance(data, list):
                return []
            return [{**item, "shop_id": shop.id, "shop_name": shop.name} for item in data]

        groups = await asyncio.gather(*(fetch(shop) for shop in shops))
        return [item for group in groups for item in group]

    async def daily(self, shops: list[Shop]) -> dict[str, Any]:
        async def fetch(shop: Shop) -> dict[str, Any]:
            overview = await self._get(shop, "/api/overview")
            today = overview.get("today") if isinstance(overview, dict) else {}
            return {
                "shop_id": shop.id,
                "shop_name": shop.name,
                "today": today if isinstance(today, dict) else {},
                "error": overview.get("error") if isinstance(overview, dict) else None,
            }

        rows = await asyncio.gather(*(fetch(shop) for shop in shops))
        return {"shops": rows, "total": len(rows)}
