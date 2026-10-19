"""卡券库存 + 自动发货 + 补发。

- 虚拟商品可有多张卡券（一单一卡）；
- 发货前从 available 池中原子占用（条件 UPDATE），避免并发重复发同一张；
- 每次发送都落 delivery_attempts，失败产生 P1；
- 买家补发/店主补发复用同一卡券内容，支持多卡库存。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.core.util import dumps, iso, new_id, now_utc, snippet
from yuxiaoer.seller.conversation.messaging import MessagingService
from yuxiaoer.seller.notifications.alerts import AlertService

log = logging.getLogger("yuxiaoer.delivery")


class DeliveryService:
    def __init__(self, db: Database, bus: EventBus, messaging: MessagingService, alerts: AlertService):
        self.db = db
        self.bus = bus
        self.messaging = messaging
        self.alerts = alerts

    async def ensure_item_cards(self, item_id: str) -> int:
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        if not item or item["delivery_mode"] != "virtual":
            return 0
        count = await self.db.count("delivery_cards", "item_id=?", (item_id,))
        if count or not item["card_content"]:
            return count
        await self.add_card(item_id, item["card_content"], note="从商品卡券内容自动初始化")
        return 1

    async def ensure_all(self) -> None:
        rows = await self.db.fetchall(
            "SELECT id FROM items WHERE delivery_mode='virtual' AND status IN ('live','sold_out')"
        )
        for row in rows:
            await self.ensure_item_cards(row["id"])

    async def list_cards(self, item_id: str) -> list[dict[str, Any]]:
        await self.ensure_item_cards(item_id)
        rows = await self.db.fetchall(
            "SELECT * FROM delivery_cards WHERE item_id=? ORDER BY created_at DESC", (item_id,)
        )
        return [dict(r) for r in rows]

    async def add_card(self, item_id: str, content: str, note: str = "") -> dict[str, Any]:
        content = (content or "").strip()
        if not content:
            raise ValueError("卡券内容不能为空")
        card_id = new_id("card")
        now = iso()
        await self.db.execute(
            """INSERT INTO delivery_cards(id,item_id,content,status,use_count,max_use,order_id,note,expires_at,created_at,updated_at)
               VALUES(?,?,?,?,0,1,NULL,?,?,?,?)""",
            (card_id, item_id, content[:4000], "available", note[:200],
             iso(now_utc() + timedelta(days=365)), now, now),
        )
        row = await self.db.fetchone("SELECT * FROM delivery_cards WHERE id=?", (card_id,))
        return dict(row) if row else {}

    async def disable_card(self, card_id: str) -> bool:
        rowcount, _ = await self.db.execute(
            "UPDATE delivery_cards SET status='disabled',updated_at=? WHERE id=? AND status='available'",
            (iso(), card_id),
        )
        return rowcount > 0

    async def card_counts(self, item_id: str) -> dict[str, int]:
        rows = await self.db.fetchall(
            "SELECT status,COUNT(*) AS n FROM delivery_cards WHERE item_id=? GROUP BY status", (item_id,)
        )
        out = {"available": 0, "used": 0, "disabled": 0}
        for row in rows:
            out[row["status"]] = int(row["n"])
        out["total"] = sum(out.values())
        return out

    async def _allocate(self, item_id: str, order_id: str) -> dict[str, Any] | None:
        rows = await self.db.fetchall(
            "SELECT * FROM delivery_cards WHERE item_id=? AND status='available' "
            "AND (expires_at IS NULL OR expires_at>?) ORDER BY created_at LIMIT 5",
            (item_id, iso()),
        )
        for row in rows:
            rowcount, _ = await self.db.execute(
                "UPDATE delivery_cards SET status='used',use_count=use_count+1,order_id=?,updated_at=? "
                "WHERE id=? AND status='available'",
                (order_id, iso(), row["id"]),
            )
            if rowcount:
                return dict(row)
        return None

    async def deliver(
        self,
        order: dict[str, Any],
        item: dict[str, Any],
        *,
        content: str | None = None,
        reason: str = "auto",
        card_id: str | None = None,
    ) -> dict[str, Any]:
        if content is None:
            card = await self._allocate(item["id"], order["id"])
            if card:
                content = card["content"]
                card_id = card["id"]
            else:
                content = item.get("card_content")
        if not content:
            await self.alerts.create(
                "P1", "card_empty", f"无卡券可发：{item['title']}",
                f"订单 {order['id']} 需要虚拟发货，但卡券池为空且商品没有兜底卡券内容。请到商品详情补充卡券。",
                order_id=order["id"], meta={"item_id": item["id"]}, dedupe_minutes=10,
            )
            await self._log_attempt(order["id"], card_id, "failed", "no card content", "")
            return {"ok": False, "error": "无卡券可发"}
        conv = await self.messaging.ensure_conversation(order["buyer_id"], item["id"], create=True)
        if not conv:
            await self._log_attempt(order["id"], card_id, "failed", "conversation missing", content)
            return {"ok": False, "error": "无法创建买家会话"}
        sent = await self.messaging.send_reply(
            conv, content, immediate=True, role="agent",
            meta={"order_id": order["id"], "kind": "virtual_delivery", "reason": reason, "card_id": card_id},
        )
        ok = bool(sent.get("ok"))
        await self._log_attempt(
            order["id"], card_id, "sent" if ok else "failed",
            sent.get("error"), content,
        )
        if card_id:
            await self.db.execute(
                "UPDATE orders SET delivery_card_id=?,updated_at=? WHERE id=?",
                (card_id, iso(), order["id"]),
            )
        if ok:
            await self.bus.emit(
                "delivery.sent",
                {"order_id": order["id"], "item_id": item["id"], "card_id": card_id, "reason": reason},
            )
        else:
            await self.alerts.create(
                "P1", "delivery_failed", f"自动发货失败：{item['title']}",
                f"订单 {order['id']} 发送卡券失败：{sent.get('error') or '未知错误'}",
                order_id=order["id"], dedupe_minutes=5,
            )
        return {"ok": ok, "card_id": card_id, "content": content, "error": sent.get("error")}

    async def resend(self, order_id: str, *, actor: str = "owner") -> dict[str, Any]:
        order = await self.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
        if not order:
            return {"ok": False, "error": "订单不存在"}
        order = dict(order)
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (order["item_id"],))
        if not item or item["delivery_mode"] != "virtual":
            return {"ok": False, "error": "不是虚拟商品订单"}
        item = dict(item)
        if order["status"] not in ("shipped", "delivered", "done"):
            return {"ok": False, "error": f"订单状态 {order['status']} 不能补发"}
        # 优先复用订单原卡券，其次从库存取新卡
        content = None
        card_id = order.get("delivery_card_id")
        if card_id:
            card = await self.db.fetchone("SELECT * FROM delivery_cards WHERE id=?", (card_id,))
            if card:
                content = card["content"]
        if not content:
            card = await self._allocate(item["id"], order_id)
            if card:
                content = card["content"]
                card_id = card["id"]
        if not content:
            content = item.get("card_content")
        if not content:
            return {"ok": False, "error": "没有可用卡券，请先在商品详情补充"}
        conv = await self.messaging.ensure_conversation(order["buyer_id"], item["id"], create=True)
        sent = await self.messaging.send_reply(
            conv, f"补发一下～\n{content}", immediate=True, role="agent",
            meta={"order_id": order_id, "kind": "delivery_resend", "actor": actor},
        )
        await self._log_attempt(order_id, card_id, "resent" if sent.get("ok") else "failed", sent.get("error"), content)
        await self.db.execute(
            "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
            (iso(), actor, "delivery.resend", order_id, dumps({"card_id": card_id}), "ok" if sent.get("ok") else "failed"),
        )
        return {"ok": bool(sent.get("ok")), "error": sent.get("error")}

    async def _log_attempt(self, order_id: str, card_id: str | None, status: str, error: str | None, content: str) -> None:
        await self.db.execute(
            "INSERT INTO delivery_attempts(order_id,card_id,status,error,content_snippet,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (order_id, card_id, status, (error or "")[:300] if error else None, snippet(content, 160), iso()),
        )

    async def attempts(self, order_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT * FROM delivery_attempts WHERE order_id=? ORDER BY id DESC LIMIT 20", (order_id,)
        )
        return [dict(r) for r in rows]
