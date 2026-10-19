"""客服工作台：会话、消息、人工接管、媒体上传。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from ..core import config
from ..core.util import dumps, iso, loads, snippet
from ..runtime import runtime
from ._models import ManualReplyIn
from ._views import _conv_out, _full_item, _message_out, _scheduled_reply

router = APIRouter()

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
