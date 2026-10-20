"""一轮买家消息的上下文：意图、实体、商品、工具统一传递。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .gateway import Decision


@dataclass
class TurnContext:
    conv: dict[str, Any]
    buyer: dict[str, Any]
    item: dict[str, Any] | None
    text: str
    decision: Decision
    toolbox: Any
    slots: dict[str, Any] = field(default_factory=dict)

    @property
    def conversation_id(self) -> str:
        return self.conv["id"]
