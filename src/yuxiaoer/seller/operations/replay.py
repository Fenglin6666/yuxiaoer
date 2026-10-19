"""会话回放：按 session/conversation 拉出消息、网关判定、工具调用、事件与告警。"""

from __future__ import annotations

from typing import Any

from yuxiaoer.core.db import Database
from yuxiaoer.core.util import human_time, loads


class ReplayService:
    def __init__(self, db: Database):
        self.db = db

    async def sessions(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            """SELECT c.*,b.nick AS buyer_nick,i.title AS item_title,
               (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count,
               (SELECT COUNT(*) FROM turns t WHERE t.conversation_id=c.id) AS turn_count,
               (SELECT text FROM messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC LIMIT 1) AS last_text,
               (SELECT created_at FROM messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC LIMIT 1) AS last_at
               FROM conversations c LEFT JOIN buyers b ON b.id=c.buyer_id LEFT JOIN items i ON i.id=c.item_id
               WHERE c.id!='conv_seller' ORDER BY COALESCE(last_at,c.updated_at) DESC LIMIT ?""",
            (limit,),
        )
        out = []
        for r in rows:
            data = dict(r)
            data["last_at_human"] = human_time(data.get("last_at"))
            out.append(data)
        return out

    async def trace(self, conversation_id: str) -> dict[str, Any] | None:
        conv = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        if not conv:
            return None
        conv = dict(conv)
        buyer = await self.db.fetchone("SELECT * FROM buyers WHERE id=?", (conv["buyer_id"],))
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (conv["item_id"],)) if conv.get("item_id") else None
        messages = await self.db.fetchall(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at,id", (conversation_id,)
        )
        turns = await self.db.fetchall(
            "SELECT * FROM turns WHERE conversation_id=? ORDER BY started_at", (conversation_id,)
        )
        tool_calls = await self.db.fetchall(
            "SELECT * FROM tool_calls WHERE session_id=? ORDER BY created_at", (conv["session_id"],)
        )
        events = await self.db.fetchall(
            "SELECT * FROM events WHERE session_id=? ORDER BY created_at", (conv["session_id"],)
        )
        alerts = await self.db.fetchall(
            "SELECT * FROM alerts WHERE conversation_id=? ORDER BY created_at", (conversation_id,)
        )
        orders = await self.db.fetchall(
            "SELECT * FROM orders WHERE buyer_id=? AND COALESCE(item_id,'')=COALESCE(?,'') ORDER BY created_at",
            (conv["buyer_id"], conv.get("item_id")),
        )
        timeline: list[dict[str, Any]] = []
        for m in messages:
            meta = loads(m["meta_json"], {}) or {}
            timeline.append({
                "ts": m["created_at"], "type": "message", "direction": m["direction"],
                "role": m["role"], "title": "买家消息" if m["direction"] == "in" else "客服回复",
                "text": m["text"], "meta": meta,
            })
        for t in turns:
            gw = loads(t["gateway_json"], {}) or {}
            timeline.append({
                "ts": t["started_at"], "type": "turn", "title": "Agent 一轮处理",
                "text": f"网关：{gw.get('category')} / {gw.get('action')}（{gw.get('reason', '')}）",
                "meta": {"turn": dict(t), "gateway": gw},
            })
        for tc in tool_calls:
            timeline.append({
                "ts": tc["created_at"], "type": "tool", "title": f"工具 · {tc['tool']}",
                "text": tc["result_json"] or "",
                "meta": {"ok": bool(tc["ok"]), "args": loads(tc["args_json"], {}), "latency_ms": tc["latency_ms"]},
            })
        for ev in events:
            timeline.append({
                "ts": ev["created_at"], "type": "event", "title": f"事件 · {ev['topic']}",
                "text": ev["payload_json"] or "", "meta": {"status": ev["status"]},
            })
        for a in alerts:
            timeline.append({
                "ts": a["created_at"], "type": "alert", "title": f"告警 · {a['level']} {a['kind']}",
                "text": a["title"] + "\n" + (a["body"] or ""), "meta": {"status": a["status"]},
            })
        for o in orders:
            timeline.append({
                "ts": o["created_at"], "type": "order", "title": f"订单 · {o['status']}",
                "text": f"{o['id']} · ¥{o['amount_cents']/100:.2f}",
                "meta": dict(o),
            })
        timeline.sort(key=lambda x: x["ts"])
        return {
            "conversation": conv,
            "buyer": dict(buyer) if buyer else None,
            "item": dict(item) if item else None,
            "turns": [dict(t) | {"gateway": loads(t["gateway_json"], {})} for t in turns],
            "tool_calls": [dict(tc) | {"args": loads(tc["args_json"], {}), "result": loads(tc["result_json"], {})} for tc in tool_calls],
            "events": [dict(e) | {"payload": loads(e["payload_json"], {})} for e in events],
            "alerts": [dict(a) | {"meta": loads(a["meta_json"], {})} for a in alerts],
            "orders": [dict(o) for o in orders],
            "timeline": timeline,
        }
