"""订单履约、发货、退款、补发与评价。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..core.util import yuan
from ..runtime import runtime
from ._models import OrderReviewIn, RefundResolveIn, ShipIn

router = APIRouter()

@router.get("/orders")
async def orders(status: str | None = None) -> list[dict[str, Any]]:
    if status:
        rows = await runtime.db.fetchall(
            "SELECT o.*,i.title,i.delivery_mode,b.nick AS buyer_nick FROM orders o "
            "JOIN items i ON i.id=o.item_id LEFT JOIN buyers b ON b.id=o.buyer_id "
            "WHERE o.status=? ORDER BY o.created_at DESC", (status,)
        )
    else:
        rows = await runtime.db.fetchall(
            "SELECT o.*,i.title,i.delivery_mode,b.nick AS buyer_nick FROM orders o "
            "JOIN items i ON i.id=o.item_id LEFT JOIN buyers b ON b.id=o.buyer_id "
            "ORDER BY o.created_at DESC LIMIT 100"
        )
    return [dict(r) | {"amount_text": f"¥{yuan(r['amount_cents'])}"} for r in rows]


@router.post("/orders/{order_id}/ship")
async def ship_order(order_id: str, payload: ShipIn) -> dict[str, Any]:
    result = await runtime.orders.fill_tracking(order_id, payload.company, payload.tracking_no, actor="owner")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "发货失败")
    return {"ok": True}


@router.post("/orders/{order_id}/refund")
async def resolve_refund(order_id: str, payload: RefundResolveIn) -> dict[str, Any]:
    result = await runtime.orders.resolve_refund(order_id, approve=payload.approve, note=payload.note, actor="owner")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "处理失败")
    return {"ok": True}


@router.post("/orders/{order_id}/complete")
async def complete_order(order_id: str) -> dict[str, Any]:
    result = await runtime.orders.confirm_receipt(order_id, actor="owner")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "操作失败")
    return {"ok": True}

@router.get("/orders/{order_id}")
async def order_detail(order_id: str) -> dict[str, Any]:
    order = await runtime.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
    if not order:
        raise HTTPException(404, "订单不存在")
    order = dict(order)
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (order["item_id"],))
    buyer = await runtime.db.fetchone("SELECT * FROM buyers WHERE id=?", (order["buyer_id"],))
    conv = await runtime.db.fetchone(
        "SELECT * FROM conversations WHERE buyer_id=? AND item_id=? ORDER BY created_at DESC LIMIT 1",
        (order["buyer_id"], order["item_id"]),
    )
    audits = await runtime.db.fetchall(
        "SELECT * FROM audit_logs WHERE target=? ORDER BY id DESC LIMIT 50", (order_id,)
    )
    events = await runtime.db.fetchall(
        "SELECT * FROM events WHERE payload_json LIKE ? ORDER BY id DESC LIMIT 30", (f"%{order_id}%",)
    )
    return {
        "order": order,
        "item": dict(item) if item else None,
        "buyer": dict(buyer) if buyer else None,
        "conversation": dict(conv) if conv else None,
        "delivery_attempts": await runtime.delivery.attempts(order_id),
        "audits": [dict(a) for a in audits],
        "events": [dict(e) for e in events],
    }


@router.post("/orders/{order_id}/resend")
async def order_resend(order_id: str) -> dict[str, Any]:
    result = await runtime.delivery.resend(order_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "补发失败")
    return {"ok": True}


@router.post("/orders/{order_id}/review")
async def order_review(order_id: str, payload: OrderReviewIn) -> dict[str, Any]:
    result = await runtime.orders.review(order_id, text=payload.text, actor="owner")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "评价失败")
    return {"ok": True}
