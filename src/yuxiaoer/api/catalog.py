"""商品、知识库与卡券库存。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..core.util import dumps, iso, loads, new_id, snippet
from ..runtime import runtime
from ._helpers import audit, full_item, item_or_404
from ._models import (
    CardIn,
    FloorIn,
    ItemCreateIn,
    ItemUpdateIn,
    PlatformItemIn,
    PriceIn,
    PublishOptionsIn,
)
from ._views import _full_item

router = APIRouter()

@router.get("/items")
async def items(status: str | None = None) -> list[dict[str, Any]]:
    if status:
        rows = await runtime.db.fetchall(
            "SELECT * FROM items WHERE status=? ORDER BY updated_at DESC", (status,)
        )
    else:
        rows = await runtime.db.fetchall("SELECT * FROM items ORDER BY updated_at DESC")
    out = []
    for row in rows:
        item = _full_item(row)
        item["order_count"] = await runtime.db.count("orders", "item_id=?", (row["id"],))
        out.append(item)
    return out


@router.post("/items")
async def create_item(payload: ItemCreateIn) -> dict[str, Any]:
    item_id = new_id("item")
    now = iso()
    floor = payload.floor_price_cents or max(1, int(payload.price_cents * 0.85))
    if floor > payload.price_cents:
        raise HTTPException(400, "底价不能高于售价")
    await runtime.db.execute(
        """INSERT INTO items(id,title,description,price_cents,floor_price_cents,max_discount_pct,
           category,condition,delivery_mode,stock,status,card_content,link_url,image_hint,
           knowledge_version,relist_count,relist_limit,sold_count,created_at,updated_at,meta_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item_id, payload.title.strip(), payload.description.strip(), payload.price_cents, floor,
            max(0, 100 - int(floor * 100 / payload.price_cents)), payload.category.strip() or "闲置好物",
            payload.condition.strip() or "全新", payload.delivery_mode, payload.stock, "draft",
            None, None, "📦", 0, 0, 3, 0, now, now, dumps({"source": "manual"}),
        ),
    )
    await runtime.knowledge.sync_item(item_id)
    return {"ok": True, "item": await full_item(item_id)}


@router.post("/items/{item_id}/publish")
async def publish_item(item_id: str, payload: PublishOptionsIn) -> dict[str, Any]:
    item = await item_or_404(item_id)
    if item["status"] == "live" and item["platform_item_id"]:
        raise HTTPException(400, "商品已经是上架状态")
    if item["platform_item_id"]:
        raise HTTPException(400, "商品已有平台 ID；重新上架请在闲鱼手动操作，避免重复发布")
    meta = loads(item["meta_json"], {}) or {}
    meta["publish"] = payload.model_dump(exclude_none=True)
    await runtime.db.execute("UPDATE items SET meta_json=?,updated_at=? WHERE id=?", (dumps(meta), iso(), item_id))
    item = await item_or_404(item_id)
    try:
        published = await runtime.queue.run(
            lambda: runtime.channel.publish_item(dict(item)), label=f"publish:{item_id}"
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)[:300])
    await runtime.db.execute(
        """UPDATE items SET platform_item_id=?,status='live',listed_at=?,updated_at=? WHERE id=?""",
        (published.get("platform_item_id"), iso(), iso(), item_id),
    )
    await runtime.knowledge.sync_item(item_id)
    await runtime.delivery.ensure_item_cards(item_id)
    await audit("item.publish", item_id, published)
    return {"ok": True, "item": await full_item(item_id)}


@router.post("/items/{item_id}/offline")
async def offline_item(item_id: str) -> dict[str, Any]:
    item = await item_or_404(item_id)
    if not item["platform_item_id"]:
        raise HTTPException(400, "商品还没有平台商品 ID")
    try:
        await runtime.queue.run(
            lambda: runtime.channel.offline_item(dict(item)), label=f"offline:{item_id}"
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)[:300])
    await runtime.db.execute(
        "UPDATE items SET status='offline',updated_at=? WHERE id=?", (iso(), item_id)
    )
    await runtime.knowledge.tombstone(f"item:{item_id}")
    await audit("item.offline", item_id)
    return {"ok": True}


@router.post("/items/{item_id}/relist")
async def relist_item(item_id: str) -> dict[str, Any]:
    item = await item_or_404(item_id)
    if item["status"] not in ("offline", "sold_out"):
        raise HTTPException(400, f"当前状态 {item['status']} 不能重新上架")
    meta = loads(item["meta_json"], {}) or {}
    if not isinstance(meta.get("publish"), dict) or not meta["publish"].get("images"):
        raise HTTPException(400, "缺少发布参数（图片/分类/地址）；请先编辑商品重新发布，或对小二说「重新上架 商品名」自动补参数")
    try:
        published = await runtime.queue.run(
            lambda: runtime.channel.publish_item(dict(item)), label=f"relist:{item_id}"
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)[:300])
    await runtime.db.execute(
        """UPDATE items SET platform_item_id=?,status='live',listed_at=?,relist_count=relist_count+1,
           updated_at=? WHERE id=?""",
        (published.get("platform_item_id"), iso(), iso(), item_id),
    )
    await runtime.knowledge.sync_item(item_id)
    await runtime.delivery.ensure_item_cards(item_id)
    await audit("item.relist", item_id, published)
    return {"ok": True, "item": await full_item(item_id)}


@router.patch("/items/{item_id}/price")
async def change_item_price(item_id: str, payload: PriceIn) -> dict[str, Any]:
    item = await item_or_404(item_id)
    if not item["platform_item_id"]:
        raise HTTPException(400, "商品还没有平台商品 ID")
    try:
        await runtime.queue.run(
            lambda: runtime.channel.change_price(dict(item), payload.price_cents),
            label=f"price:{item_id}",
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)[:300])
    await runtime.db.execute(
        "UPDATE items SET price_cents=?,floor_price_cents=MIN(floor_price_cents,?),stock=?,updated_at=? WHERE id=?",
        (payload.price_cents, payload.price_cents, payload.stock, iso(), item_id),
    )
    await runtime.knowledge.sync_item(item_id)
    await audit("item.price", item_id, {"price_cents": payload.price_cents})
    return {"ok": True}


@router.get("/items/{item_id}")
async def item_detail(item_id: str) -> dict[str, Any]:
    row = await item_or_404(item_id)
    item = _full_item(row)
    item["knowledge"] = await runtime.knowledge.item_knowledge(item_id)
    item["orders"] = [dict(o) for o in await runtime.db.fetchall(
        "SELECT * FROM orders WHERE item_id=? ORDER BY created_at DESC LIMIT 20", (item_id,)
    )]
    if item.get("delivery_mode") == "virtual":
        item["card_counts"] = await runtime.delivery.card_counts(item_id)
        item["cards"] = await runtime.delivery.list_cards(item_id)
    return item


@router.post("/items/{item_id}/floor")
async def update_floor(item_id: str, payload: FloorIn) -> dict[str, Any]:
    item = await item_or_404(item_id)
    if payload.floor_price_cents > item["price_cents"]:
        raise HTTPException(400, "底价不能高于售价")
    await runtime.db.execute(
        "UPDATE items SET floor_price_cents=?,updated_at=? WHERE id=?",
        (payload.floor_price_cents, iso(), item_id),
    )
    await runtime.knowledge.sync_item(item_id)
    return {"ok": True}


@router.get("/knowledge/search")
async def kb_search(q: str = Query(...), namespace: str = "buyer", k: int = 5) -> list[dict[str, Any]]:
    return await runtime.knowledge.search(q, namespace=namespace, k=k)


@router.get("/knowledge/sources")
async def kb_sources(namespace: str | None = None) -> list[dict[str, Any]]:
    if namespace:
        rows = await runtime.db.fetchall(
            "SELECT * FROM kb_sources WHERE namespace=? ORDER BY updated_at DESC", (namespace,)
        )
    else:
        rows = await runtime.db.fetchall("SELECT * FROM kb_sources ORDER BY updated_at DESC")
    out = []
    for r in rows:
        data = dict(r)
        data["meta"] = loads(data.get("meta_json"), {})
        data.pop("meta_json", None)
        data["content_snippet"] = snippet(data.get("content"), 120)
        out.append(data)
    return out

@router.get("/items/{item_id}/cards")
async def item_cards(item_id: str) -> dict[str, Any]:
    await item_or_404(item_id, select="id,delivery_mode")
    cards = await runtime.delivery.list_cards(item_id)
    return {"cards": cards, "counts": await runtime.delivery.card_counts(item_id)}


@router.patch("/items/{item_id}")
async def update_item(item_id: str, payload: ItemUpdateIn) -> dict[str, Any]:
    item = await item_or_404(item_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return {"ok": True}
    price = int(values.get("price_cents", item["price_cents"]))
    floor = int(values.get("floor_price_cents", item["floor_price_cents"]))
    if floor > price:
        raise HTTPException(400, "底价不能高于售价")
    values["updated_at"] = iso()
    assignments = ", ".join(f"{key}=?" for key in values)
    await runtime.db.execute(
        f"UPDATE items SET {assignments} WHERE id=?",
        tuple(values.values()) + (item_id,),
    )
    await runtime.knowledge.sync_item(item_id)
    if values.get("delivery_mode") == "virtual":
        await runtime.delivery.ensure_item_cards(item_id)
    return {"ok": True}


@router.post("/items/{item_id}/platform")
async def item_bind_platform(item_id: str, payload: PlatformItemIn) -> dict[str, Any]:
    await item_or_404(item_id)
    platform_id = payload.platform_item_id.strip()
    existing = await runtime.db.fetchone(
        "SELECT id FROM items WHERE platform_item_id=? AND id!=?", (platform_id, item_id)
    )
    if existing:
        raise HTTPException(409, "该平台商品 ID 已绑定到另一个商品")
    await runtime.db.execute(
        "UPDATE items SET platform_item_id=?,updated_at=? WHERE id=?", (platform_id, iso(), item_id)
    )
    # 订单同步可能先创建了占位商品，绑定后把订单迁到真实商品
    placeholder = f"xyitem_{platform_id}"
    if placeholder != item_id:
        await runtime.db.execute("UPDATE orders SET item_id=? WHERE item_id=?", (item_id, placeholder))
        await runtime.db.execute("UPDATE conversations SET item_id=? WHERE item_id=?", (item_id, placeholder))
        await runtime.db.execute("DELETE FROM items WHERE id=? AND status='live'", (placeholder,))
    await runtime.knowledge.sync_item(item_id)
    return {"ok": True, "platform_item_id": platform_id}


@router.post("/items/{item_id}/cards")
async def item_card_add(item_id: str, payload: CardIn) -> dict[str, Any]:
    item = await item_or_404(item_id, select="id,delivery_mode")
    if item["delivery_mode"] != "virtual":
        raise HTTPException(400, "只有虚拟商品可以添加卡券")
    try:
        card = await runtime.delivery.add_card(item_id, payload.content, payload.note)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "card": card, "counts": await runtime.delivery.card_counts(item_id)}


@router.post("/cards/{card_id}/disable")
async def card_disable(card_id: str) -> dict[str, Any]:
    ok = await runtime.delivery.disable_card(card_id)
    if not ok:
        raise HTTPException(400, "卡券不可用或已使用")
    return {"ok": True}
