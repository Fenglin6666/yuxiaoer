"""小二 Agent 对话与确认项操作。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..core.util import dumps, iso, loads, yuan
from ..runtime import runtime
from ._models import PublishConfirmEditIn, SellerMessageIn
from ._views import _conv_out, _full_item, _message_out

router = APIRouter()

@router.get("/seller/messages")
async def seller_messages() -> dict[str, Any]:
    conv = await runtime.messaging.seller_conversation()
    messages = [await _message_out(m) for m in await runtime.messaging.messages(conv["id"], 200)]
    pending = await runtime.confirmations.list("pending", 20)
    return {"messages": messages, "pending": pending, "conversation": _conv_out(conv)}


@router.post("/seller/message")
async def seller_send(payload: SellerMessageIn) -> dict[str, Any]:
    result = await runtime.seller.handle(payload.text, images=payload.images)
    conv = await runtime.messaging.seller_conversation()
    messages = [await _message_out(m) for m in await runtime.messaging.messages(conv["id"], 200)]
    return {"ok": result.get("ok", True), "result": result, "messages": messages}


@router.post("/confirmations/{confirmation_id}/confirm")
async def confirm_action(confirmation_id: str) -> dict[str, Any]:
    ok = await runtime.seller.resolve(confirmation_id, True)
    return {"ok": ok}


@router.post("/confirmations/{confirmation_id}/cancel")
async def cancel_action(confirmation_id: str) -> dict[str, Any]:
    ok = await runtime.seller.resolve(confirmation_id, False)
    return {"ok": ok}


@router.patch("/confirmations/{confirmation_id}")
async def edit_confirmation(confirmation_id: str, payload: PublishConfirmEditIn) -> dict[str, Any]:
    cfm = await runtime.confirmations.get(confirmation_id)
    if not cfm or cfm["kind"] != "publish_listing":
        raise HTTPException(404, "发布确认项不存在")
    if cfm["status"] != "pending":
        raise HTTPException(409, "确认项已处理")
    item_id = (cfm.get("payload") or {}).get("item_id")
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品草稿不存在")
    data = payload.model_dump(exclude_unset=True)
    title = (data.get("title") or item["title"]).strip()
    description = data.get("description", item["description"])
    price = int(data.get("price_cents") or item["price_cents"])
    floor = int(data.get("floor_price_cents") or item["floor_price_cents"])
    if not title:
        raise HTTPException(400, "标题不能为空")
    if floor > price:
        raise HTTPException(400, "底价不能高于售价")
    mode = data.get("delivery_mode") or item["delivery_mode"]
    stock = int(data.get("stock") if data.get("stock") is not None else item["stock"])
    await runtime.db.execute(
        """UPDATE items SET title=?,description=?,price_cents=?,floor_price_cents=?,
           delivery_mode=?,stock=?,updated_at=? WHERE id=?""",
        (title, description, price, floor, mode, stock, iso(), item_id),
    )
    meta = loads(item["meta_json"], {}) or {}
    publish = meta.get("publish") if isinstance(meta.get("publish"), dict) else {}
    images = data.get("images") if data.get("images") is not None else (publish.get("images") or [])
    images = [str(x).strip() for x in images if str(x).strip()]
    if "images" in data and not images:
        raise HTTPException(400, "至少保留一张图片")
    category = dict(publish.get("category") or {})
    for field, key in (
        ("category_id", "cat_id"), ("category_name", "cat_name"),
        ("channel_cat_id", "channel_cat_id"), ("tb_cat_id", "tb_cat_id"),
        ("leaf_id", "leaf_id"),
    ):
        if field in data:
            category[key] = data[field]
    publish.update({
        "images": images,
        "category": category,
        "address": data.get("address", publish.get("address") or ""),
        "shipping_method": data.get("shipping_method", publish.get("shipping_method") or "free"),
        "mode": data.get("mode", publish.get("mode") or "personal"),
        "quantity": stock,
    })
    meta["publish"] = publish
    await runtime.db.execute("UPDATE items SET meta_json=?,updated_at=? WHERE id=?", (dumps(meta), iso(), item_id))
    preview = dict(cfm.get("preview") or {})
    preview.update({
        "title": title, "description": description, "price_cents": price,
        "floor_price_cents": floor, "price_text": f"¥{yuan(price)}",
        "delivery_mode": mode, "images": images,
        "publish_category": category.get("cat_name") or preview.get("publish_category"),
        "publish_category_id": category.get("cat_id") or "",
        "publish_channel_cat_id": category.get("channel_cat_id") or "",
        "publish_tb_cat_id": category.get("tb_cat_id") or "",
        "publish_leaf_id": category.get("leaf_id") or "",
        "publish_address": publish.get("address"), "publish_shipping_method": publish.get("shipping_method"),
        "publish_mode": publish.get("mode"), "stock": stock,
    })
    updated = await runtime.confirmations.update_pending(
        confirmation_id,
        title=f"发布商品：{title}",
        preview=preview,
        payload=cfm.get("payload") or {"item_id": item_id},
    )
    if not updated:
        raise HTTPException(409, "确认项已处理")
    return {"ok": True, "confirmation": updated, "item": _full_item(await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,)))}
