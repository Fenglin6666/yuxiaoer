"""业务状态机：所有状态迁移 = 条件 UPDATE + events + audit。

乐观锁：
    UPDATE ... SET status='shipped' WHERE id=? AND status='paid'
影响行数为 0 = 状态已变（例如退款已受理），动作被拒绝，不做“先查后写”。
"""

from __future__ import annotations

from typing import Any, Iterable

from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.core.util import dumps, iso

ITEM_STATUSES = {
    "draft", "pending_confirm", "live", "sold_out", "offline",
}
ORDER_STATUSES = {
    "new", "paid", "shipped", "delivered", "done", "refund_open", "refund_resolved", "cancelled",
}

_ITEM_FIELDS = {
    "title", "description", "price_cents", "floor_price_cents", "max_discount_pct",
    "category", "condition", "delivery_mode", "stock", "card_content", "link_url",
    "platform_item_id", "image_hint", "relist_count", "sold_count", "offline_reason",
    "listed_at", "meta_json",
}
_ORDER_FIELDS = {
    "address", "buyer_note", "tracking_company", "tracking_no", "refund_reason",
    "refund_note", "amount_cents", "platform_order_id", "paid_at", "shipped_at",
    "delivered_at", "done_at",
}


async def _audit(db: Database, actor: str, action: str, target: str, detail: dict, result: str) -> None:
    await db.execute(
        "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
        (iso(), actor, action, target, dumps(detail), result),
    )


def _set_clause(to_status: str, now: str, fields: dict[str, Any]) -> tuple[str, list[Any]]:
    parts = ["status=?", "updated_at=?"]
    values: list[Any] = [to_status, now]
    for key, value in fields.items():
        if key not in _ITEM_FIELDS and key not in _ORDER_FIELDS:
            continue
        parts.append(f"{key}=?")
        values.append(value)
    return ", ".join(parts), values


async def transition_item(
    db: Database,
    bus: EventBus,
    item_id: str,
    from_statuses: Iterable[str],
    to_status: str,
    *,
    fields: dict[str, Any] | None = None,
    actor: str = "system",
    reason: str = "",
) -> bool:
    assert to_status in ITEM_STATUSES, to_status
    from_list = [s for s in from_statuses if s in ITEM_STATUSES]
    if not from_list:
        return False
    now = iso()
    fields = dict(fields or {})
    if to_status == "live" and "listed_at" not in fields:
        fields["listed_at"] = now
    if to_status == "offline" and reason:
        fields["offline_reason"] = reason
    set_sql, values = _set_clause(to_status, now, fields)
    placeholders = ",".join("?" for _ in from_list)
    sql = f"UPDATE items SET {set_sql} WHERE id=? AND status IN ({placeholders})"
    rowcount, _ = await db.execute(sql, [*values, item_id, *from_list])
    if rowcount <= 0:
        await _audit(db, actor, "item.transition.rejected", item_id,
                     {"to": to_status, "from": from_list, "reason": reason}, "conflict")
        return False

    item = await db.fetchone("SELECT title,price_cents,status FROM items WHERE id=?", (item_id,))
    await _audit(db, actor, "item.transition", item_id,
                 {"to": to_status, "from": from_list, "reason": reason}, "ok")
    await bus.emit(
        "item.status_changed",
        {
            "item_id": item_id,
            "title": item["title"] if item else None,
            "price_cents": item["price_cents"] if item else None,
            "from": from_list,
            "to": to_status,
            "reason": reason,
        },
        actor=actor,
    )
    return True


async def transition_order(
    db: Database,
    bus: EventBus,
    order_id: str,
    from_statuses: Iterable[str],
    to_status: str,
    *,
    fields: dict[str, Any] | None = None,
    actor: str = "system",
    reason: str = "",
) -> bool:
    assert to_status in ORDER_STATUSES, to_status
    from_list = [s for s in from_statuses if s in ORDER_STATUSES]
    if not from_list:
        return False
    now = iso()
    fields = dict(fields or {})
    if to_status == "paid":
        fields.setdefault("paid_at", now)
    elif to_status == "shipped":
        fields.setdefault("shipped_at", now)
    elif to_status == "delivered":
        fields.setdefault("delivered_at", now)
    elif to_status in ("done", "refund_resolved"):
        fields.setdefault("done_at", now)
    set_sql, values = _set_clause(to_status, now, fields)
    placeholders = ",".join("?" for _ in from_list)
    sql = f"UPDATE orders SET {set_sql} WHERE id=? AND status IN ({placeholders})"
    rowcount, _ = await db.execute(sql, [*values, order_id, *from_list])
    if rowcount <= 0:
        await _audit(db, actor, "order.transition.rejected", order_id,
                     {"to": to_status, "from": from_list, "reason": reason}, "conflict")
        return False

    order = await db.fetchone(
        "SELECT item_id,buyer_id,amount_cents,status FROM orders WHERE id=?", (order_id,)
    )
    await _audit(db, actor, "order.transition", order_id,
                 {"to": to_status, "from": from_list, "reason": reason}, "ok")
    payload = {
        "order_id": order_id,
        "item_id": order["item_id"] if order else None,
        "buyer_id": order["buyer_id"] if order else None,
        "amount_cents": order["amount_cents"] if order else None,
        "from": from_list,
        "to": to_status,
        "reason": reason,
    }
    topic = "order.paid" if to_status == "paid" else "order.status_changed"
    await bus.emit(topic, payload, actor=actor)
    return True
