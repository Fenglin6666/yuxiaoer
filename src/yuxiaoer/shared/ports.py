"""跨域窄接口（Protocol）：买家域只声明自己用到的方法。

这样 buyer 不再 import seller 的具体实现，运行时仍由 runtime.py 注入真实服务。
"""

from __future__ import annotations

from typing import Any, Protocol


class AlertPort(Protocol):
    async def create(self, *args: Any, **kwargs: Any) -> Any: ...


class MessagingPort(Protocol):
    async def ensure_conversation(self, *args: Any, **kwargs: Any) -> Any: ...

    async def add_inbound(self, *args: Any, **kwargs: Any) -> Any: ...

    async def pending_inbound(self, *args: Any, **kwargs: Any) -> Any: ...

    async def mark_processed(self, *args: Any, **kwargs: Any) -> Any: ...

    async def mark_owner_unread(self, *args: Any, **kwargs: Any) -> Any: ...

    async def send_reply(self, *args: Any, **kwargs: Any) -> Any: ...

    async def set_handoff(self, *args: Any, **kwargs: Any) -> Any: ...

    async def resume(self, *args: Any, **kwargs: Any) -> Any: ...
