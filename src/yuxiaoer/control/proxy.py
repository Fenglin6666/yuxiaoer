"""控制台到闲鱼账号实例的 HTTP 代理：会话、人工回复、店主指令、确认项。"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from yuxiaoer.core import config

from .registry import Shop


def shop_auth() -> tuple[str, str] | None:
    if config.CONSOLE_USER and config.CONSOLE_PASSWORD:
        return (config.CONSOLE_USER, config.CONSOLE_PASSWORD)
    return None


class ShopProxy:
    def base_url(self, shop: Shop) -> str:
        return f"http://127.0.0.1:{shop.port}"

    async def request(
        self, shop: Shop, method: str, path: str, json: dict[str, Any] | None = None
    ) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url(shop), auth=shop_auth(), timeout=15.0
            ) as client:
                response = await client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"账号实例 {shop.id} 不可达：{exc}") from exc
        if response.status_code >= 400:
            detail = response.text[:300]
            raise HTTPException(response.status_code, detail or "账号接口失败")
        if not response.content:
            return {"ok": True}
        try:
            return response.json()
        except ValueError:
            return {"ok": True}

    async def forward(
        self, shop: Shop, method: str, path: str, *,
        params: Any = None, content: bytes | None = None, headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url(shop), auth=shop_auth(), timeout=60.0
            ) as client:
                return await client.request(
                    method, path, params=params, content=content, headers=headers
                )
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"账号实例 {shop.id} 不可达：{exc}") from exc

    async def status(self, shop: Shop) -> dict[str, Any]:
        data = await self.request(shop, "GET", "/api/status")
        return data if isinstance(data, dict) else {}

    async def accounts(self, shop: Shop) -> list[dict[str, Any]]:
        data = await self.request(shop, "GET", "/api/accounts")
        return data if isinstance(data, list) else []

    async def create_account(self, shop: Shop, nickname: str) -> dict[str, Any]:
        data = await self.request(shop, "POST", "/api/accounts", {"nickname": nickname or "闲鱼账号"})
        return data if isinstance(data, dict) else {}

    async def login_start(self, shop: Shop, account_id: str) -> dict[str, Any]:
        data = await self.request(shop, "POST", f"/api/accounts/{account_id}/login/start")
        return data if isinstance(data, dict) else {}

    async def login_status(self, shop: Shop, account_id: str) -> dict[str, Any]:
        data = await self.request(shop, "GET", f"/api/accounts/{account_id}/login/status")
        return data if isinstance(data, dict) else {}

    async def sync_account(self, shop: Shop, account_id: str) -> dict[str, Any]:
        data = await self.request(shop, "POST", f"/api/accounts/{account_id}/sync", {})
        return data if isinstance(data, dict) else {}
