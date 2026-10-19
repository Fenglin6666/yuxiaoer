"""卖家指令共享助手：查询词清洗、确认卡提案。

三个写操作（下架/重新上架/改价）的流程完全一致：
清洗商品名 → 生成 preview → 建确认项 → 记一次工具调用 → 返回确认卡。
把这段收成 `propose()`，新增写操作时只需要准备 preview 和文案。
"""

from __future__ import annotations

import re
from typing import Any

from yuxiaoer.shared.toolbox import ToolBox

_PREFIX = re.compile(r"^(把|请|帮我|麻烦|给|将)\s*")
_FILLER = re.compile(r"(那个|这件|商品|一下|的)")
_TRIM = " ，,。"


def clean_query(text: str, verbs: str, extra: str | None = None) -> str:
    """去掉指令动词、前缀敬语、商品名里的口语填充词。"""
    query = re.sub(verbs, " ", text)
    if extra:
        query = re.sub(extra, " ", query)
    query = _PREFIX.sub("", query.strip())
    return _FILLER.sub(" ", query).strip(_TRIM)


async def propose(
    confirmations: Any,
    toolbox: ToolBox,
    *,
    kind: str,
    title: str,
    preview: dict[str, Any],
    payload: dict[str, Any],
    text: str,
    tool_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建一个待确认动作，并返回可直接回复店主的确认卡。"""
    cfm = await confirmations.create(kind, title, preview, payload, source="seller_agent")
    await toolbox.call(kind, tool_args or payload, lambda: {"preview": True})
    return {
        "ok": True,
        "text": text,
        "card": {"type": "confirmation", "confirmation_id": cfm["id"], "preview": preview},
    }
