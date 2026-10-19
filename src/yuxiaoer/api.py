"""REST API：控制台、小二 Agent 对话、观测、评测、设置。"""

from __future__ import annotations

import html as html_lib
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from yuxiaoer.core import config
from yuxiaoer.seller.notifications.email_actions import token as email_action_token, verify as verify_email_action
from .runtime import runtime
from yuxiaoer.core.state import transition_item
from yuxiaoer.core.util import dumps, human_time, iso, loads, local_now, new_id, snippet, yuan

router = APIRouter(prefix="/api")


# ---------------- 请求模型 ----------------

class SellerMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    images: list[str] = Field(default_factory=list, max_length=9)


class ManualReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class ShipIn(BaseModel):
    company: str = "快递"
    tracking_no: str = Field(min_length=3, max_length=60)


class RefundResolveIn(BaseModel):
    approve: bool = True
    note: str = ""


class ConfirmIn(BaseModel):
    approve: bool = True


class SettingsIn(BaseModel):
    values: dict[str, Any]


class EvalRunIn(BaseModel):
    judge_mode: str = "rules"


class FloorIn(BaseModel):
    floor_price_cents: int = Field(ge=1)


class AccountCreateIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)
    platform: str = "xianyu"


class NotifyChannelIn(BaseModel):
    kind: str
    name: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    min_level: str = "P1"


class CardIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    note: str = ""


class PlatformItemIn(BaseModel):
    platform_item_id: str = Field(min_length=1, max_length=64)


class ItemUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    price_cents: int | None = Field(default=None, ge=1)
    floor_price_cents: int | None = Field(default=None, ge=1)
    delivery_mode: str | None = Field(default=None, pattern="^(physical|virtual)$")
    stock: int | None = Field(default=None, ge=0, le=999999)
    category: str | None = Field(default=None, max_length=120)
    condition: str | None = Field(default=None, max_length=40)


class ItemCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    price_cents: int = Field(ge=1)
    floor_price_cents: int | None = Field(default=None, ge=1)
    delivery_mode: str = Field(default="physical", pattern="^(physical|virtual)$")
    stock: int = Field(default=1, ge=0, le=999999)
    category: str = "闲置好物"
    condition: str = "全新"


class PublishOptionsIn(BaseModel):
    images: list[str] = Field(default_factory=list, max_length=9)
    category: dict[str, Any] = Field(default_factory=dict)
    address: str = ""
    address_geo: dict[str, Any] | None = None
    shipping_method: str = "free"
    postage: float = 0
    quantity: int = Field(default=1, ge=0, le=999999)
    original_price_cents: int | None = None
    mode: str = Field(default="personal", pattern="^(personal|shop)$")


class PriceIn(BaseModel):
    price_cents: int = Field(ge=1)
    stock: int = Field(default=1, ge=0, le=999999)


class PublishConfirmEditIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    price_cents: int | None = Field(default=None, ge=1)
    floor_price_cents: int | None = Field(default=None, ge=1)
    delivery_mode: str | None = Field(default=None, pattern="^(physical|virtual)$")
    stock: int | None = Field(default=None, ge=0, le=999999)
    images: list[str] | None = Field(default=None, max_length=9)
    category_id: str | None = Field(default=None, max_length=64)
    category_name: str | None = Field(default=None, max_length=120)
    channel_cat_id: str | None = Field(default=None, max_length=64)
    tb_cat_id: str | None = Field(default=None, max_length=64)
    leaf_id: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=200)
    shipping_method: str | None = Field(default=None, max_length=20)
    mode: str | None = Field(default=None, pattern="^(personal|shop)$")


class OrderReviewIn(BaseModel):
    text: str = "交易愉快，感谢信任～"


class JobUpdateIn(BaseModel):
    enabled: bool | None = None
    local_time: str | None = None
    interval_seconds: int | None = None


class TestAlertIn(BaseModel):
    level: str = "P1"
    title: str = "通知联调测试"
    body: str = "如果你收到这条消息，说明鱼小二通知渠道已打通。"


# ---------------- 序列化 ----------------

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


# ---------------- 基础 ----------------

@router.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "app": config.APP_NAME, "version": config.VERSION, "time": iso()}


@router.get("/status")
async def status() -> dict[str, Any]:
    return await runtime.system_status()


@router.get("/overview")
async def overview() -> dict[str, Any]:
    return await runtime.overview()


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    return await runtime.metrics.overview()


# ---------------- 会话 / 客服工作台 ----------------

@router.get("/conversations")
async def conversations(filter: str = Query("active")) -> list[dict[str, Any]]:
    where = "c.id!='conv_seller'"
    if filter == "handoff":
        where += " AND c.handoff=1"
    elif filter == "active":
        where += " AND c.status='active'"
    rows = await runtime.db.fetchall(
        f"""SELECT c.*,b.nick AS buyer_nick,i.title AS item_title,
            (SELECT text FROM messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC LIMIT 1) AS last_text,
            (SELECT created_at FROM messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC LIMIT 1) AS last_at,
            (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id AND m.direction='in') AS inbound_count
            FROM conversations c LEFT JOIN buyers b ON b.id=c.buyer_id LEFT JOIN items i ON i.id=c.item_id
            WHERE {where} ORDER BY c.handoff DESC,COALESCE(last_at,c.updated_at) DESC LIMIT 100"""
    )
    return [_conv_out(r) for r in rows]


@router.get("/conversations/{conversation_id}")
async def conversation_detail(conversation_id: str) -> dict[str, Any]:
    conv = await runtime.db.fetchone("SELECT * FROM conversations WHERE id=?", (conversation_id,))
    if not conv:
        raise HTTPException(404, "会话不存在")
    await runtime.messaging.mark_owner_read(conversation_id)
    buyer = await runtime.db.fetchone("SELECT * FROM buyers WHERE id=?", (conv["buyer_id"],))
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (conv["item_id"],)) if conv["item_id"] else None
    messages = [await _message_out(m) for m in await runtime.messaging.messages(conversation_id, 200)]
    turns = await runtime.db.fetchall(
        "SELECT * FROM turns WHERE conversation_id=? ORDER BY started_at DESC LIMIT 10", (conversation_id,)
    )
    turn_list = []
    for t in turns:
        data = dict(t)
        data["gateway"] = loads(data.get("gateway_json"), {})
        tools = await runtime.db.fetchall(
            "SELECT * FROM tool_calls WHERE turn_id=? ORDER BY created_at", (t["id"],)
        )
        data["tools"] = [
            {**dict(tc), "args": loads(tc["args_json"], {}), "result": loads(tc["result_json"], {})}
            for tc in tools
        ]
        turn_list.append(data)
    order = await runtime.db.fetchone(
        "SELECT * FROM orders WHERE buyer_id=? AND item_id=? ORDER BY created_at DESC LIMIT 1",
        (conv["buyer_id"], conv["item_id"]),
    ) if conv["item_id"] else None
    alerts = await runtime.db.fetchall(
        "SELECT * FROM alerts WHERE conversation_id=? ORDER BY created_at DESC LIMIT 5", (conversation_id,)
    )
    kb_hits = []
    last_in = await runtime.db.fetchone(
        "SELECT text FROM messages WHERE conversation_id=? AND direction='in' ORDER BY created_at DESC LIMIT 1",
        (conversation_id,),
    )
    if last_in:
        kb_hits = await runtime.knowledge.search(last_in["text"], namespace="buyer", k=3, types=["faq"])
    return {
        "conversation": _conv_out(conv),
        "buyer": dict(buyer) if buyer else None,
        "item": _full_item(item) if item else None,
        "messages": messages,
        "turns": turn_list,
        "order": dict(order) if order else None,
        "alerts": [dict(a) for a in alerts],
        "kb_hits": kb_hits,
        "pending_inbound": len(await runtime.messaging.pending_inbound(conversation_id)),
        "scheduled_reply": await _scheduled_reply(conversation_id),
    }


@router.post("/conversations/{conversation_id}/reply")
async def manual_reply(conversation_id: str, payload: ManualReplyIn) -> dict[str, Any]:
    conv = await runtime.messaging.conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    result = await runtime.messaging.send_reply(
        conv, payload.text, role="seller", immediate=True, meta={"manual": True, "by": "owner"}
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "发送失败")
    await runtime.messaging.set_handoff(conversation_id, "店主手动接管", minutes=120)
    await runtime.alerts.ack_related(kind="handoff", conversation_id=conversation_id)
    await runtime.db.execute(
        "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
        (iso(), "owner", "manual_reply", conversation_id, dumps({"text": snippet(payload.text, 120)}), "ok"),
    )
    return {"ok": True, "message": await _message_out(result["message"])}


@router.post("/conversations/{conversation_id}/takeover")
async def takeover(conversation_id: str) -> dict[str, Any]:
    conv = await runtime.messaging.conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    await runtime.messaging.set_handoff(conversation_id, "店主主动接管", minutes=120)
    return {"ok": True}


@router.post("/conversations/{conversation_id}/resume")
async def resume(conversation_id: str) -> dict[str, Any]:
    conv = await runtime.messaging.conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    await runtime.messaging.resume(conversation_id)
    await runtime.alerts.ack_related(kind="handoff", conversation_id=conversation_id)
    return {"ok": True}


@router.post("/media")
async def upload_media(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if not files or len(files) > 9:
        raise HTTPException(400, "一次最多上传 9 张图片")
    media_dir = Path(config.DATA_DIR) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    paths: list[str] = []
    for file in files:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in allowed:
            raise HTTPException(400, f"不支持的图片格式：{file.filename}")
        content = await file.read()
        if not content:
            raise HTTPException(400, "图片为空")
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "单张图片不能超过 10MB")
        path = media_dir / f"{uuid4().hex}{ext}"
        path.write_bytes(content)
        paths.append(str(path))
    return {"ok": True, "paths": paths}


# ---------------- 小二 Agent 对话 ----------------

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


# ---------------- 商品 / 知识 ----------------

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
    return {"ok": True, "item": _full_item(await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,)))}


@router.post("/items/{item_id}/publish")
async def publish_item(item_id: str, payload: PublishOptionsIn) -> dict[str, Any]:
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
    if item["status"] == "live" and item["platform_item_id"]:
        raise HTTPException(400, "商品已经是上架状态")
    if item["platform_item_id"]:
        raise HTTPException(400, "商品已有平台 ID；重新上架请在闲鱼手动操作，避免重复发布")
    meta = loads(item["meta_json"], {}) or {}
    meta["publish"] = payload.model_dump(exclude_none=True)
    await runtime.db.execute("UPDATE items SET meta_json=?,updated_at=? WHERE id=?", (dumps(meta), iso(), item_id))
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
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
    await runtime.db.execute(
        "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
        (iso(), "owner", "item.publish", item_id, dumps(published), "success"),
    )
    return {"ok": True, "item": _full_item(await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,)))}


@router.post("/items/{item_id}/offline")
async def offline_item(item_id: str) -> dict[str, Any]:
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
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
    await runtime.db.execute(
        "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
        (iso(), "owner", "item.offline", item_id, "{}", "success"),
    )
    return {"ok": True}


@router.post("/items/{item_id}/relist")
async def relist_item(item_id: str) -> dict[str, Any]:
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
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
    await runtime.db.execute(
        "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
        (iso(), "owner", "item.relist", item_id, dumps(published), "success"),
    )
    return {"ok": True, "item": _full_item(await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,)))}


@router.patch("/items/{item_id}/price")
async def change_item_price(item_id: str, payload: PriceIn) -> dict[str, Any]:
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
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
    await runtime.db.execute(
        "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
        (iso(), "owner", "item.price", item_id, dumps({"price_cents": payload.price_cents}), "success"),
    )
    return {"ok": True}


@router.get("/items/{item_id}")
async def item_detail(item_id: str) -> dict[str, Any]:
    row = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not row:
        raise HTTPException(404, "商品不存在")
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
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
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


# ---------------- 订单 ----------------

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


# ---------------- 值守 / 告警 ----------------

# ---------------- 多账号 / 会话保活 ----------------

def _account_public(account: dict[str, Any]) -> dict[str, Any]:
    data = dict(account)
    data.pop("refresh_policy_json", None)
    data.pop("meta_json", None)
    data.pop("cookies", None)
    data.pop("access_token", None)
    return data


@router.get("/accounts")
async def accounts() -> list[dict[str, Any]]:
    return [_account_public(a) for a in await runtime.accounts.list()]


@router.post("/accounts")
async def create_account(payload: AccountCreateIn) -> dict[str, Any]:
    try:
        account = await runtime.accounts.create(payload.nickname, payload.platform)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "account": _account_public(account)}


@router.get("/accounts/{account_id}")
async def account_detail(account_id: str) -> dict[str, Any]:
    account = await runtime.accounts.get(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    return _account_public(account)


@router.get("/accounts/{account_id}/events")
async def account_events(account_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return await runtime.accounts.events(account_id, limit)


@router.post("/accounts/{account_id}/login/start")
async def account_login_start(account_id: str) -> dict[str, Any]:
    try:
        return await runtime.accounts.start_login(account_id)
    except KeyError:
        raise HTTPException(404, "账号不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


@router.get("/accounts/{account_id}/login/status")
async def account_login_status(account_id: str) -> dict[str, Any]:
    try:
        data = await runtime.accounts.login_status(account_id)
    except KeyError:
        raise HTTPException(404, "账号不存在")
    data.pop("cookies", None)
    if data.get("account"):
        data["account"] = _account_public(data["account"])
    return data


@router.post("/accounts/{account_id}/sync")
async def account_sync(account_id: str) -> dict[str, Any]:
    sync = getattr(runtime.channel, "sync_account_for", None)
    if not sync:
        raise HTTPException(400, "当前通道不支持账号同步")
    try:
        result = await sync(account_id)
    except KeyError:
        raise HTTPException(404, "账号不存在")
    except Exception as exc:
        raise HTTPException(400, str(exc)[:300])
    return result


@router.post("/accounts/{account_id}/refresh")
async def account_refresh(account_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "account": _account_public(await runtime.accounts.refresh(account_id, kind="manual"))}
    except KeyError:
        raise HTTPException(404, "账号不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


@router.post("/accounts/{account_id}/logout")
async def account_logout(account_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "account": _account_public(await runtime.accounts.logout(account_id))}
    except KeyError:
        raise HTTPException(404, "账号不存在")


@router.post("/accounts/{account_id}/activate")
async def account_activate(account_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "account": _account_public(await runtime.accounts.activate(account_id))}
    except KeyError:
        raise HTTPException(404, "账号不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


@router.post("/accounts/tick")
async def accounts_tick() -> dict[str, Any]:
    return {"ok": True, "result": await runtime.session_keeper.tick(), "status": runtime.session_keeper.status()}


# ---------------- 风控 / 反检测 ----------------

@router.get("/risk")
async def risk_status() -> dict[str, Any]:
    return {
        "status": await runtime.risk.status(),
        "keeper": runtime.session_keeper.status(),
        "write_queue": runtime.queue.stats(),
        "events": await runtime.risk.recent_events(10),
    }


@router.post("/risk/reset")
async def risk_reset() -> dict[str, Any]:
    return {"ok": True, "status": await runtime.risk.reset("manual_reset")}


# ---------------- 通知渠道 ----------------

@router.get("/notify/channels")
async def notify_channels() -> list[dict[str, Any]]:
    return await runtime.notifications.list_channels()


@router.post("/notify/channels")
async def notify_channel_create(payload: NotifyChannelIn) -> dict[str, Any]:
    try:
        channel = await runtime.notifications.upsert(payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "channel": channel}


@router.put("/notify/channels/{channel_id}")
async def notify_channel_update(channel_id: str, payload: NotifyChannelIn) -> dict[str, Any]:
    try:
        channel = await runtime.notifications.upsert(payload.model_dump(), channel_id)
    except KeyError:
        raise HTTPException(404, "渠道不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "channel": channel}


@router.delete("/notify/channels/{channel_id}")
async def notify_channel_delete(channel_id: str) -> dict[str, Any]:
    return {"ok": await runtime.notifications.delete(channel_id)}


@router.post("/notify/channels/{channel_id}/test")
async def notify_channel_test(channel_id: str) -> dict[str, Any]:
    try:
        log = await runtime.notifications.send_test(channel_id)
    except KeyError:
        raise HTTPException(404, "渠道不存在")
    if log.get("status") != "sent":
        raise HTTPException(400, log.get("error") or "发送失败")
    return {"ok": True, "log": log}


@router.get("/notify/logs")
async def notify_logs(limit: int = 50) -> list[dict[str, Any]]:
    return await runtime.notifications.logs(limit)


@router.post("/notify/email/poll")
async def notify_email_poll() -> dict[str, Any]:
    return await runtime.email_gateway.poll_once()


def _email_action_page(*, title: str, body: str, status_code: int = 200) -> HTMLResponse:
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_lib.escape(title)} · 鱼小二</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:#f4f7f4;color:#24332d;margin:0;padding:28px}}
.card{{max-width:560px;margin:8vh auto;background:#fff;border:1px solid #dfe9e3;border-radius:16px;padding:26px;box-shadow:0 12px 40px rgba(29,64,48,.08)}}
h2{{margin:0 0 10px;font-size:20px}}p{{line-height:1.7;color:#52655c}}.meta{{background:#f6faf7;border:1px solid #e3eee7;border-radius:10px;padding:12px;margin:16px 0;white-space:pre-wrap;line-height:1.6}}
.btn{{display:inline-block;border:0;border-radius:9px;padding:11px 18px;font-size:14px;cursor:pointer;text-decoration:none;margin:6px 8px 6px 0}}
.ok{{background:#147a55;color:#fff}}.danger{{background:#b23a3a;color:#fff}}.ghost{{background:#edf5f0;color:#2d5c47}}</style></head>
<body><div class="card"><h2>{html_lib.escape(title)}</h2>{body}
<p><a class="btn ghost" href="{html_lib.escape(config.PUBLIC_BASE_URL)}/#/seller">打开控制台</a></p></div></body></html>"""
    return HTMLResponse(page, status_code=status_code, headers={"Cache-Control": "no-store"})


def _email_action_detail(cfm: dict[str, Any]) -> str:
    preview = cfm.get("preview") or {}
    lines = [f"商品：{preview.get('title') or '—'}"]
    if preview.get("price_cents"):
        lines.append(f"价格：¥{yuan(preview['price_cents'])}")
    if preview.get("old_price_cents") is not None and preview.get("new_price_cents") is not None:
        lines.append(f"改价：¥{yuan(preview['old_price_cents'])} → ¥{yuan(preview['new_price_cents'])}")
    if preview.get("publish_category"):
        lines.append(f"分类：{preview['publish_category']}")
    if preview.get("publish_address"):
        lines.append(f"所在地：{preview['publish_address']}")
    lines.append(f"确认项：{cfm['id']}")
    return "\n".join(lines)


@router.get("/email/action/{confirmation_id}/{action}", response_class=HTMLResponse)
async def email_action_landing(confirmation_id: str, action: str, token: str = Query("")) -> HTMLResponse:
    if not verify_email_action(confirmation_id, action, token):
        return _email_action_page(title="链接无效", body="<p>确认链接无效或已过期。</p>", status_code=403)
    cfm = await runtime.confirmations.get(confirmation_id)
    if not cfm or cfm["status"] != "pending":
        return _email_action_page(
            title="确认项已处理", body="<p>这个确认项已执行、取消或过期，无需重复操作。</p>"
        )
    label = "确认执行" if action == "confirm" else "确认取消"
    kind = "确认执行" if action == "confirm" else "取消操作"
    opposite = "cancel" if action == "confirm" else "confirm"
    opposite_label = "改为取消" if action == "confirm" else "改为确认"
    body = f"""<p>你正在通过邮件链接{html_lib.escape(kind)}下面这个操作。请再点击一次按钮，防止邮件客户端预加载链接误触发。</p>
<div class="meta">{html_lib.escape(_email_action_detail(cfm))}</div>
<form method="post" action="/api/email/action/{html_lib.escape(confirmation_id)}/{action}">
  <input type="hidden" name="token" value="{html_lib.escape(token)}">
  <button class="btn {'ok' if action == 'confirm' else 'danger'}" type="submit">{html_lib.escape(label)}</button>
</form>
<a class="btn ghost" href="/api/email/action/{html_lib.escape(confirmation_id)}/{opposite}?token={html_lib.escape(email_action_token(confirmation_id, opposite))}">{html_lib.escape(opposite_label)}</a>"""
    return _email_action_page(title="邮件确认", body=body)


@router.post("/email/action/{confirmation_id}/{action}", response_class=HTMLResponse)
async def email_action_execute(confirmation_id: str, action: str, token: str = Form("")) -> HTMLResponse:
    if not verify_email_action(confirmation_id, action, token):
        return _email_action_page(title="链接无效", body="<p>确认链接无效或已过期。</p>", status_code=403)
    cfm = await runtime.confirmations.get(confirmation_id)
    if not cfm or cfm["status"] != "pending":
        return _email_action_page(title="确认项已处理", body="<p>这个确认项已执行、取消或过期。</p>")
    ok = await runtime.seller.resolve(confirmation_id, action == "confirm")
    if ok:
        title = "已执行" if action == "confirm" else "已取消"
        body = "<p>操作已处理，Agent 的回复已写入「让小二做点什么」。</p>"
    else:
        title = "未执行"
        body = "<p>确认项状态已变化或执行失败，请打开控制台查看待确认项和告警。</p>"
    return _email_action_page(title=title, body=body)


@router.post("/notify/test")
async def notify_test(payload: TestAlertIn) -> dict[str, Any]:
    alert_id = await runtime.alerts.create(payload.level, "notify_test", payload.title, payload.body)
    return {"ok": True, "alert_id": alert_id}


# ---------------- 卡券库存 ----------------

@router.get("/items/{item_id}/cards")
async def item_cards(item_id: str) -> dict[str, Any]:
    item = await runtime.db.fetchone("SELECT id,delivery_mode FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
    cards = await runtime.delivery.list_cards(item_id)
    return {"cards": cards, "counts": await runtime.delivery.card_counts(item_id)}


@router.patch("/items/{item_id}")
async def update_item(item_id: str, payload: ItemUpdateIn) -> dict[str, Any]:
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
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
    item = await runtime.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
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
    item = await runtime.db.fetchone("SELECT id,delivery_mode FROM items WHERE id=?", (item_id,))
    if not item:
        raise HTTPException(404, "商品不存在")
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


# ---------------- 批量发布 ----------------

# ---------------- 订单详情 / 补发 / 评价 ----------------

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


@router.get("/patrol/jobs")
async def patrol_jobs() -> list[dict[str, Any]]:
    return await runtime.patrol.jobs()


@router.patch("/patrol/jobs/{name}")
async def patrol_update(name: str, payload: JobUpdateIn) -> dict[str, Any]:
    try:
        job = await runtime.patrol.update_job(
            name, enabled=payload.enabled, local_time=payload.local_time,
            interval_seconds=payload.interval_seconds,
        )
    except KeyError:
        raise HTTPException(404, "任务不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "job": job}


# ---------------- 值守执行 / 告警 ----------------

@router.post("/patrol/jobs/{name}/run")
async def patrol_run(name: str) -> dict[str, Any]:
    result = await runtime.patrol.run_job(name, manual=True)
    runtime._health_cache = None
    return result


@router.get("/alerts")
async def alerts(status: str = Query("open"), limit: int = 50) -> list[dict[str, Any]]:
    return await runtime.alerts.list(status, limit)


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str) -> dict[str, Any]:
    ok = await runtime.alerts.ack(alert_id)
    if not ok:
        raise HTTPException(404, "告警不存在或已处理")
    return {"ok": True}


# ---------------- 观测 / 回放 ----------------

@router.get("/events")
async def events(limit: int = 100, topic: str | None = None) -> list[dict[str, Any]]:
    if topic:
        rows = await runtime.db.fetchall(
            "SELECT * FROM events WHERE topic=? ORDER BY id DESC LIMIT ?", (topic, limit)
        )
    else:
        rows = await runtime.db.fetchall("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
    return [
        dict(r) | {"payload": loads(r["payload_json"], {}), "created_human": human_time(r["created_at"])}
        for r in rows
    ]


@router.get("/tools")
async def tool_calls(limit: int = 100) -> list[dict[str, Any]]:
    rows = await runtime.db.fetchall(
        "SELECT * FROM tool_calls ORDER BY id DESC LIMIT ?", (limit,)
    )
    return [
        dict(r) | {"args": loads(r["args_json"], {}), "result": loads(r["result_json"], {}),
                   "created_human": human_time(r["created_at"])}
        for r in rows
    ]


@router.get("/replay/sessions")
async def replay_sessions(limit: int = 30) -> list[dict[str, Any]]:
    return await runtime.replay.sessions(limit)


@router.get("/replay/{conversation_id}")
async def replay_trace(conversation_id: str) -> dict[str, Any]:
    trace = await runtime.replay.trace(conversation_id)
    if not trace:
        raise HTTPException(404, "会话不存在")
    return trace


# ---------------- 评测 ----------------

@router.get("/eval/cases")
async def eval_cases() -> list[dict[str, Any]]:
    return await runtime.eval.cases()


@router.get("/eval/runs")
async def eval_runs(limit: int = 10) -> list[dict[str, Any]]:
    return await runtime.eval.runs(limit)


@router.post("/eval/run")
async def eval_run(payload: EvalRunIn) -> dict[str, Any]:
    mode = "llm" if payload.judge_mode == "llm" and runtime.llm.available() else "rules"
    return await runtime.eval.run(judge_mode=mode)


# ---------------- 设置 ----------------

@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    return {
        "values": await runtime.settings.public(),
        "llm": runtime.llm.status(),
        "system": await runtime.system_status(),
        "editable": sorted(config.EDITABLE_SETTINGS),
    }


@router.post("/settings")
async def set_settings(payload: SettingsIn) -> dict[str, Any]:
    for key, value in payload.values.items():
        if key not in config.EDITABLE_SETTINGS:
            continue
        if key == "floor_discount_pct":
            value = max(50, min(100, int(value)))
        if key == "merge_window_seconds":
            value = max(0.0, min(30.0, float(value)))
        if key in ("night_mode", "auto_relist", "auto_review", "human_typing"):
            value = 1 if str(value).lower() in ("1", "true", "on", "yes") else 0
        if key == "relist_limit":
            value = max(1, min(100, int(value)))
        if key == "bargain_max_rounds":
            value = max(1, min(10, int(value)))
        if key == "risk_cooldown_minutes":
            value = max(1, min(180, int(value)))
        if key in ("polish_time", "daily_report_time"):
            value = str(value).strip()
            if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", value):
                raise HTTPException(400, "时间格式应为 HH:MM")
        if key == "llm_enabled" and str(value).lower() in ("1", "true", "on", "yes") and not runtime.llm.has_key():
            raise HTTPException(400, "未配置 LLM_API_KEY，无法开启 LLM 模式")
        await runtime.settings.set(key, value)
    if "polish_time" in payload.values:
        await runtime.patrol.update_job("polish", local_time=str(payload.values["polish_time"]))
    if "daily_report_time" in payload.values:
        await runtime.patrol.update_job("daily_report", local_time=str(payload.values["daily_report_time"]))
    await runtime.apply_settings()
    await runtime.knowledge.sync_all_items()
    return {"ok": True, "values": await runtime.settings.public(), "llm": runtime.llm.status()}
