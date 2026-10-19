"""控制台响应序列化辅助（不注册路由）。"""

from __future__ import annotations

from typing import Any

from ..core.util import human_time, loads, yuan
from ..runtime import runtime

async def _message_out(row: Any) -> dict[str, Any]:
    data = dict(row) if not isinstance(row, dict) else dict(row)
    meta = loads(data.get("meta_json"), {}) or {}
    card = meta.get("card")
    if isinstance(card, dict) and card.get("type") == "confirmation" and card.get("confirmation_id"):
        cfm = await runtime.confirmations.get(card["confirmation_id"])
        if cfm:
            card = {**card, "status": cfm["status"], "preview": cfm["preview"], "kind": cfm["kind"]}
            meta["card"] = card
    data["meta"] = meta
    data.pop("meta_json", None)
    data["created_human"] = human_time(data.get("created_at"))
    return data


def _conv_out(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["last_human"] = human_time(data.get("last_at") or data.get("last_message_at"))
    data["status_text"] = "人工接管" if data.get("handoff") else "托管中"
    return data


def _full_item(item: Any) -> dict[str, Any]:
    data = dict(item)
    data["price_text"] = f"¥{yuan(data.get('price_cents', 0))}"
    data["floor_text"] = f"¥{yuan(data.get('floor_price_cents', 0))}"
    data["delivery_text"] = "虚拟自动发货" if data.get("delivery_mode") == "virtual" else "实物待发货"
    data["meta"] = loads(data.get("meta_json"), {})
    data.pop("meta_json", None)
    return data


async def _scheduled_reply(conversation_id: str) -> dict[str, Any] | None:
    row = await runtime.db.fetchone(
        "SELECT * FROM outbox WHERE conversation_id=? AND status='pending' ORDER BY send_after LIMIT 1",
        (conversation_id,),
    )
    if not row:
        return None
    meta = loads(row["meta_json"], {}) or {}
    return {
        "id": row["id"], "text": row["text"], "send_after": row["send_after"],
        "send_after_human": human_time(row["send_after"]), "reason": meta.get("reason"),
    }
