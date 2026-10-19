"""通道层：只保留原生闲鱼通道。

没有 mock 回退。未配置真实账号/协议能力时，操作会明确失败，而不是返回假成功。
"""

from __future__ import annotations

from typing import Any

from yuxiaoer.core.db import Database


class ChannelError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class BaseChannel:
    name = "base"
    label = "未配置"

    async def health(self) -> dict[str, Any]:
        raise NotImplementedError

    async def send_message(self, buyer_id: str, text: str, *, conversation_id: str, item_id: str | None = None) -> str:
        raise NotImplementedError

    async def publish_item(self, item: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def offline_item(self, item: dict[str, Any]) -> None:
        raise NotImplementedError

    async def change_price(self, item: dict[str, Any], price_cents: int) -> None:
        raise NotImplementedError

    async def polish_items(self, items: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    async def relist_item(self, item: dict[str, Any]) -> None:
        raise NotImplementedError

    async def check_link(self, url: str | None) -> bool:
        return True

    async def replace_link(self, item: dict[str, Any]) -> str:
        raise NotImplementedError


def build_channel(db: Database) -> BaseChannel:
    from yuxiaoer.seller.platform.xianyu.channel import NativeXianyuChannel

    return NativeXianyuChannel(db)
