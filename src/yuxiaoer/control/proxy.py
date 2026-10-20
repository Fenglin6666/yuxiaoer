"""控制面到店铺实例的 HTTP 代理：会话、人工回复、店主指令、确认项。"""

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
            raise HTTPException(502, f"店铺 {shop.id} 不可达：{exc}") from exc
        if response.status_code >= 400:
            detail = response.text[:300]
            raise HTTPException(response.status_code, detail or "店铺接口失败")
        if not response.content:
            return {"ok": True}
        try:
            return response.json()
        except ValueError:
            return {"ok": True}

    async def conversations(self, shop: Shop, filter_: str = "active") -> list[dict[str, Any]]:
        data = await self.request(shop, "GET", f"/api/conversations?filter={filter_}")
        return data if isinstance(data, list) else []

    async def conversation(self, shop: Shop, conversation_id: str) -> dict[str, Any]:
        data = await self.request(shop, "GET", f"/api/conversations/{conversation_id}")
        return data if isinstance(data, dict) else {}

    async def reply(self, shop: Shop, conversation_id: str, text: str) -> dict[str, Any]:
        return await self.request(
            shop, "POST", f"/api/conversations/{conversation_id}/reply", {"text": text}
        )

    async def takeover(self, shop: Shop, conversation_id: str) -> dict[str, Any]:
        return await self.request(shop, "POST", f"/api/conversations/{conversation_id}/takeover")

    async def resume(self, shop: Shop, conversation_id: str) -> dict[str, Any]:
        return await self.request(shop, "POST", f"/api/conversations/{conversation_id}/resume")

    async def seller_messages(self, shop: Shop) -> dict[str, Any]:
        data = await self.request(shop, "GET", "/api/seller/messages")
        return data if isinstance(data, dict) else {}

    async def seller_send(self, shop: Shop, text: str) -> dict[str, Any]:
        data = await self.request(shop, "POST", "/api/seller/message", {"text": text})
        return data if isinstance(data, dict) else {}

    async def confirm(self, shop: Shop, confirmation_id: str, action: str) -> dict[str, Any]:
        if action not in ("confirm", "cancel"):
            raise HTTPException(400, "未知确认操作")
        data = await self.request(
            shop, "POST", f"/api/confirmations/{confirmation_id}/{action}"
        )
        return data if isinstance(data, dict) else {}
