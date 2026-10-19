"""订单：下单、自动发货、回填单号、退款处理。

退款 vs 发货的竞态由状态机乐观锁拦截：
- 退款受理：paid/shipped/delivered → refund_open
- 自动发货：paid → shipped
两者只有一个条件 UPDATE 能成功，另一个影响 0 行即被拒绝。
"""

from __future__ import annotations

import logging
from typing import Any

from yuxiaoer.core import config
from yuxiaoer.seller.notifications.alerts import AlertService
from yuxiaoer.seller.platform.channels import BaseChannel
from yuxiaoer.core.db import Database
from yuxiaoer.seller.commerce.delivery import DeliveryService
from yuxiaoer.core.events import EventBus
from yuxiaoer.shared.knowledge import KnowledgeService
from yuxiaoer.seller.conversation.messaging import MessagingService
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.state import transition_item, transition_order
from yuxiaoer.core.util import dumps, iso, new_id, snippet, yuan
from yuxiaoer.seller.write_queue import WriteQueue

log = logging.getLogger("yuxiaoer.orders")


class OrderService:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        messaging: MessagingService,
        alerts: AlertService,
        knowledge: KnowledgeService,
        channel: BaseChannel,
        queue: WriteQueue,
        settings: SettingsService,
    ):
        self.db = db
        self.bus = bus
        self.messaging = messaging
        self.alerts = alerts
        self.knowledge = knowledge
        self.channel = channel
        self.queue = queue
        self.settings = settings

    async def purchase(
        self, buyer_id: str, item_id: str, *, nick: str = "闲鱼买家", idempotency_key: str | None = None
    ) -> dict[str, Any]:
        await self.messaging.ensure_buyer(buyer_id, nick)
        if idempotency_key:
            existing = await self.db.fetchone("SELECT * FROM orders WHERE idempotency_key=?", (idempotency_key,))
            if existing:
                return {"ok": True, "order": dict(existing), "reused": True}
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        if not item:
            return {"ok": False, "error": "商品不存在"}
        if item["status"] != "live":
            return {"ok": False, "error": f"商品当前状态为 {item['status']}，无法下单"}
        active = await self.db.fetchone(
            "SELECT * FROM orders WHERE buyer_id=? AND item_id=? AND status IN ('paid','shipped','delivered','refund_open')"
            " ORDER BY created_at DESC LIMIT 1",
            (buyer_id, item_id),
        )
        if active:
            return {"ok": True, "order": dict(active), "reused": True, "notice": "已有进行中的订单"}

        # 先用状态机把商品锁成 sold_out，防止超卖
        locked = await transition_item(
            self.db, self.bus, item_id, ["live"], "sold_out",
            actor="buyer_checkout", reason="买家下单",
        )
        if not locked:
            return {"ok": False, "error": "手慢了，商品刚刚被拍下"}
        if item["delivery_mode"] == "physical":
            await self.db.execute(
                "UPDATE items SET stock=MAX(stock-1,0),sold_count=sold_count+1 WHERE id=?", (item_id,)
            )
        else:
            await self.db.execute("UPDATE items SET sold_count=sold_count+1 WHERE id=?", (item_id,))
        order_id = new_id("ord")
        now = iso()
        await self.db.execute(
            """INSERT INTO orders(id,platform_order_id,item_id,buyer_id,quantity,amount_cents,status,idempotency_key,
               created_at,paid_at,updated_at)
               VALUES(?,?,?,?,1,?,'new',?,?,?,?)""",
            (order_id, "XY" + new_id("", 12).upper(), item_id, buyer_id,
             item["price_cents"], idempotency_key or new_id("idem"), now, None, now),
        )
        paid = await transition_order(
            self.db, self.bus, order_id, ["new"], "paid", actor="buyer_checkout", reason="买家付款",
        )
        if not paid:
            await self.db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
            return {"ok": False, "error": "订单状态异常，已取消"}
        order = await self.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
        return {"ok": True, "order": dict(order) if order else None}

    async def fill_tracking(
        self, order_id: str, company: str, tracking_no: str, *, actor: str = "seller_agent"
    ) -> dict[str, Any]:
        order = await self.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
        if not order:
            return {"ok": False, "error": "订单不存在"}
        if order["status"] != "paid":
            return {"ok": False, "error": f"订单状态为 {order['status']}，不能发货"}
        ok = await transition_order(
            self.db, self.bus, order_id, ["paid"], "shipped",
            fields={"tracking_company": company, "tracking_no": tracking_no},
            actor=actor, reason="回填快递单号",
        )
        if not ok:
            return {"ok": False, "error": "状态已变化，发货被状态机拦截"}
        conv = await self.messaging.ensure_conversation(order["buyer_id"], order["item_id"], create=True)
        if conv:
            await self.messaging.send_reply(
                conv,
                f"已经发货啦～ {company} 单号 {tracking_no}，预计 2-3 天到，收到有问题随时找我。",
                immediate=True, role="agent", meta={"order_id": order_id, "kind": "shipping_notice"},
            )
        await self.alerts.ack_related(kind="order_pending", order_id=order_id)
        await self.alerts.ack_related(kind="ship_reminder", order_id=order_id)
        return {"ok": True}

    async def resolve_refund(
        self, order_id: str, *, approve: bool, note: str = "", actor: str = "owner"
    ) -> dict[str, Any]:
        order = await self.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
        if not order:
            return {"ok": False, "error": "订单不存在"}
        if order["status"] != "refund_open":
            return {"ok": False, "error": f"订单状态为 {order['status']}，不在退款中"}
        result_note = ("同意退款：" if approve else "拒绝退款：") + (note or "店主已处理")
        ok = await transition_order(
            self.db, self.bus, order_id, ["refund_open"], "refund_resolved",
            fields={"refund_note": result_note}, actor=actor, reason=result_note,
        )
        if not ok:
            return {"ok": False, "error": "状态已变化"}
        conv = await self.messaging.ensure_conversation(order["buyer_id"], order["item_id"], create=True)
        if conv:
            text = "退款已经处理好啦，款项会按平台流程退回～" if approve else "店主已处理你的售后申请，具体方案已在平台内沟通～"
            await self.messaging.send_reply(
                conv, text, immediate=True, role="agent",
                meta={"order_id": order_id, "kind": "refund_result"},
            )
        await self.alerts.ack_related(kind="refund_request", order_id=order_id)
        if conv:
            await self.alerts.ack_related(kind="handoff", conversation_id=conv["id"])
        # 退款后重新上架：虚拟商品换新链接，实物恢复库存
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (order["item_id"],))
        if approve and item and item["status"] == "sold_out":
            if item["delivery_mode"] == "physical":
                await self.db.execute("UPDATE items SET stock=stock+1 WHERE id=?", (item["id"],))
            ok2 = await transition_item(
                self.db, self.bus, item["id"], ["sold_out"], "live",
                fields={"relist_count": int(item["relist_count"]) + 1},
                actor=actor, reason="退款后重新上架",
            )
            if ok2:
                await self.knowledge.sync_item(item["id"])
        return {"ok": True}

    async def confirm_receipt(self, order_id: str, *, actor: str = "buyer") -> dict[str, Any]:
        order = await self.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
        if not order:
            return {"ok": False, "error": "订单不存在"}
        if order["status"] not in ("shipped", "delivered"):
            return {"ok": False, "error": f"订单状态为 {order['status']}，不能确认收货"}
        ok = await transition_order(
            self.db, self.bus, order_id, ["shipped", "delivered"], "done",
            actor=actor, reason="买家确认收货",
        )
        if ok and await self.settings.get_bool("auto_review", False):
            await self.review(order_id, text="交易愉快，感谢信任～", actor="auto_review")
        return {"ok": True} if ok else {"ok": False, "error": "状态已变化"}

    async def review(self, order_id: str, *, text: str = "交易愉快，感谢信任～", actor: str = "owner") -> dict[str, Any]:
        order = await self.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
        if not order:
            return {"ok": False, "error": "订单不存在"}
        if order["status"] != "done":
            return {"ok": False, "error": "订单完成后才能评价"}
        await self.db.execute(
            "UPDATE orders SET reviewed_at=?,reviewed_text=?,updated_at=? WHERE id=?",
            (iso(), text[:500], iso(), order_id),
        )
        await self.db.execute(
            "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
            (iso(), actor, "order.review", order_id, dumps({"text": text[:200]}), "ok"),
        )
        await self.bus.emit("order.reviewed", {"order_id": order_id, "text": text[:200]}, actor=actor)
        return {"ok": True}


class FulfillmentService:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        messaging: MessagingService,
        alerts: AlertService,
        knowledge: KnowledgeService,
        channel: BaseChannel,
        queue: WriteQueue,
        settings: SettingsService,
        delivery: DeliveryService,
    ):
        self.db = db
        self.bus = bus
        self.messaging = messaging
        self.alerts = alerts
        self.knowledge = knowledge
        self.channel = channel
        self.queue = queue
        self.settings = settings
        self.delivery = delivery

    async def handle_order_paid(self, payload: dict[str, Any], meta: dict[str, Any]) -> None:
        order_id = payload.get("order_id")
        if not order_id:
            return
        order = await self.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
        if not order:
            return
        order = dict(order)
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (order["item_id"],))
        if not item:
            await self.alerts.create("P1", "order_item_missing", "订单商品缺失",
                                     f"订单 {order_id} 找不到商品 {order['item_id']}", order_id=order_id)
            return
        item = dict(item)
        conv = await self.messaging.ensure_conversation(order["buyer_id"], order["item_id"], create=True)
        if not conv:
            return

        if order["status"] == "refund_open":
            await self.alerts.create(
                "P1", "fulfill_conflict", "自动发货被状态机拦截",
                f"订单 {order_id} 已进入退款流程，自动发货动作被拒绝（乐观锁 0 行）。",
                conversation_id=conv["id"], order_id=order_id, dedupe_minutes=5,
            )
            return
        if order["status"] != "paid":
            return

        if item["delivery_mode"] == "virtual":
            shipped = await transition_order(
                self.db, self.bus, order_id, ["paid"], "shipped",
                fields={"tracking_company": "自动发货", "tracking_no": "AUTO-" + order_id[-6:].upper()},
                actor="fulfillment", reason="虚拟商品自动发货",
            )
            if not shipped:
                await self.alerts.create(
                    "P1", "fulfillment_conflict", "自动发货被状态机拦截",
                    f"订单 {order_id} 当前已非 paid 状态，自动发货未执行。",
                    conversation_id=conv["id"], order_id=order_id, dedupe_minutes=5,
                )
                return
            delivery = await self.delivery.deliver(order, item, content=None, reason="auto")
            if delivery.get("ok"):
                await self.bus.emit(
                    "fulfillment.auto_delivered",
                    {"order_id": order_id, "item_id": item["id"], "buyer_id": order["buyer_id"],
                     "card_id": delivery.get("card_id")},
                    session_id=conv.get("session_id"),
                )
        else:
            await self.alerts.create(
                "P1", "order_pending", f"待发货：{item['title']}",
                f"买家 {order['buyer_id']} 已付款 ¥{yuan(order['amount_cents'])}，地址：{order.get('address') or '未填写'}。"
                "请填写快递单号。",
                conversation_id=conv["id"], order_id=order_id, dedupe_minutes=30,
            )
            seller = await self.messaging.seller_conversation()
            await self.messaging.add_local_message(
                seller["id"],
                f"新订单已付款：{item['title']} ¥{yuan(order['amount_cents'])}\n"
                f"地址：{order.get('address') or '未填写'}\n请发货后回填快递单号。",
                role="system",
                meta={"card": {"type": "order", "order_id": order_id, "item_id": item["id"],
                               "title": item["title"], "amount_cents": order["amount_cents"]}},
            )
