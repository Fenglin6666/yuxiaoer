"""闲鱼订单同步（真实 mtop.taobao.idle.trade.merchant.sold.get）。

只同步订单到本地状态机；自动发货仍由本项目的 FulfillmentService 负责，
卡券、风控、幂等继续复用现有实现。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from yuxiaoer.core.util import dumps, iso, new_id

from .mtop import MtopClient

log = logging.getLogger("yuxiaoer.xianyu.orders")

_STATUS_MAP = {
    "待付款": "new",
    "待发货": "paid",
    "已发货": "shipped",
    "交易成功": "done",
    "交易关闭": "cancelled",
    "退款中": "refund_open",
    "退款成功": "refund_resolved",
    "已退款": "refund_resolved",
    "退款关闭": "cancelled",
}
_TERMINAL = {"done", "cancelled", "refund_resolved"}
_RANK = {
    "new": 0, "paid": 1, "shipped": 2, "delivered": 3, "done": 4,
    "refund_open": 5, "refund_resolved": 6, "cancelled": 6,
}


def _parse_time(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).astimezone().isoformat()
        except Exception:
            pass
    return iso()


def _order_status(common: dict[str, Any]) -> str:
    if str(common.get("inRefund") or "").lower() == "true":
        return "refund_open"
    return _STATUS_MAP.get(str(common.get("orderStatus") or ""), "new")


class OrderSyncService:
    def __init__(self, runtime):
        self.runtime = runtime

    async def sync_account(self, account: dict[str, Any], *, query_code: str = "ALL",
                           max_pages: int | None = None) -> dict[str, Any]:
        cookies = str(account.get("cookies") or "")
        if not cookies:
            return {"ok": False, "error": "账号没有 Cookie", "fetched": 0, "inserted": 0, "updated": 0}
        client = MtopClient(cookies, device_id=str(account.get("device_id") or ""))
        try:
            first = await client.call_sold_orders(1, query_code=query_code)
            module = (first or {}).get("module") or {}
            items = module.get("items") or []
            total = int(module.get("totalCount") or len(items) or 0)
            pages = max(1, (total + 29) // 30)
            if max_pages:
                pages = min(pages, max_pages)
            all_items = list(items)
            for page in range(2, pages + 1):
                page_data = await client.call_sold_orders(page, query_code=query_code)
                all_items.extend(((page_data or {}).get("module") or {}).get("items") or [])
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200], "fetched": 0, "inserted": 0, "updated": 0}

        inserted = updated = 0
        errors: list[str] = []
        for raw in all_items:
            try:
                parsed = self._parse(raw, account)
                if not parsed:
                    continue
                changed = await self._upsert(parsed, account)
                if changed == "inserted":
                    inserted += 1
                elif changed == "updated":
                    updated += 1
                await self._maybe_auto_deliver(parsed["local_order_id"], parsed["status"])
            except Exception as exc:
                errors.append(str(exc)[:120])
                log.warning("sync order failed: %s", exc)
        # Token / Cookie 可能被响应刷新
        await self.runtime.db.execute(
            "UPDATE accounts SET cookies=?,updated_at=? WHERE id=?",
            (client.cookies, iso(), account["id"]),
        )
        return {
            "ok": not errors, "fetched": len(all_items), "inserted": inserted,
            "updated": updated, "errors": errors[:10],
        }

    def _parse(self, item: dict[str, Any], account: dict[str, Any]) -> dict[str, Any] | None:
        common = item.get("commonData") or {}
        buyer = item.get("buyerInfoVO") or {}
        price = item.get("priceVO") or {}
        right = item.get("rightVO") or {}
        order_no = str(common.get("orderId") or "").strip()
        item_id = str(common.get("itemId") or "").strip()
        if not order_no or not item_id:
            return None
        status = _order_status(common)
        try:
            amount = int(round(float(price.get("totalPrice") or 0) * 100))
        except Exception:
            amount = 0
        try:
            quantity = int(price.get("buyNum") or 1)
        except Exception:
            quantity = 1
        is_bargain = any(
            str(btn.get("tradeAction") or "") == "SKIP_PIN"
            for btn in (right.get("btnList") or []) if isinstance(btn, dict)
        )
        placed_at = _parse_time(str(common.get("createTime") or "")) or iso()
        return {
            "order_no": order_no,
            "platform_status": str(common.get("orderStatus") or ""),
            "status": status,
            "item_platform_id": item_id,
            "buyer_id": str(buyer.get("buyerId") or "").strip(),
            "buyer_nick": str(buyer.get("userNick") or "闲鱼买家").strip(),
            "receiver_name": str(buyer.get("name") or ""),
            "receiver_phone": str(buyer.get("phone") or ""),
            "receiver_address": str(buyer.get("address") or ""),
            "amount_cents": amount,
            "quantity": max(1, quantity),
            "is_bargain": is_bargain,
            "placed_at": placed_at,
            "account_id": str(account.get("platform_user_id") or account["id"]),
            "local_order_id": "",
        }

    async def _ensure_item(self, parsed: dict[str, Any]) -> str:
        platform_id = parsed["item_platform_id"]
        row = await self.runtime.db.fetchone(
            "SELECT * FROM items WHERE platform_item_id=? LIMIT 1", (platform_id,)
        )
        if row:
            return row["id"]
        item_id = f"xyitem_{platform_id}"
        now = iso()
        await self.runtime.db.execute(
            """INSERT OR IGNORE INTO items(id,platform_item_id,title,description,price_cents,floor_price_cents,
               max_discount_pct,category,condition,delivery_mode,stock,status,card_content,link_url,image_hint,
               knowledge_version,relist_count,relist_limit,sold_count,created_at,updated_at,meta_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id, platform_id, f"平台商品 {platform_id}",
                "从闲鱼订单同步自动创建的商品占位；可在商品页补充标题、描述与卡券。",
                parsed["amount_cents"] or 1, max(1, int((parsed["amount_cents"] or 1) * 0.85)),
                15, "平台同步", "二手", "physical", 1, "live", None, None, "📦",
                0, 0, 3, 0, now, now, dumps({"source": "xianyu_order_sync"}),
            ),
        )
        return item_id

    async def _ensure_buyer(self, parsed: dict[str, Any]) -> str:
        buyer_id = parsed["buyer_id"] or f"xy_buyer_{parsed['order_no']}"
        row = await self.runtime.db.fetchone("SELECT id FROM buyers WHERE id=?", (buyer_id,))
        if row:
            await self.runtime.db.execute(
                "UPDATE buyers SET nick=COALESCE(NULLIF(?,''),nick), source='xianyu' WHERE id=?",
                (parsed["buyer_nick"], buyer_id),
            )
            return buyer_id
        await self.runtime.db.execute(
            "INSERT INTO buyers(id,nick,note,deal_count,blacklist,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (buyer_id, parsed["buyer_nick"], "", 0, 0, "xianyu", iso(), iso()),
        )
        return buyer_id

    async def _upsert(self, parsed: dict[str, Any], account: dict[str, Any]) -> str:
        item_id = await self._ensure_item(parsed)
        buyer_id = await self._ensure_buyer(parsed)
        existing = await self.runtime.db.fetchone(
            "SELECT * FROM orders WHERE platform_order_id=? LIMIT 1", (parsed["order_no"],)
        )
        now = iso()
        if not existing:
            order_id = new_id("ord")
            status = parsed["status"]
            await self.runtime.db.execute(
                """INSERT INTO orders(id,platform_order_id,item_id,buyer_id,quantity,amount_cents,status,
                   address,buyer_note,tracking_company,tracking_no,refund_reason,refund_note,idempotency_key,
                   created_at,paid_at,shipped_at,delivered_at,done_at,updated_at,platform_status,account_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    order_id, parsed["order_no"], item_id, buyer_id, parsed["quantity"],
                    parsed["amount_cents"], status, parsed["receiver_address"], "",
                    None, None, None, None, f"xy:{account['id']}:{parsed['order_no']}",
                    parsed["placed_at"], parsed["placed_at"] if status != "new" else None,
                    now if status in ("shipped", "done") else None,
                    now if status == "done" else None,
                    now if status == "done" else None,
                    now, parsed["platform_status"], parsed["account_id"],
                ),
            )
            parsed["local_order_id"] = order_id
            await self.runtime.bus.emit("order.synced", {
                "order_id": order_id, "order_no": parsed["order_no"],
                "status": status, "source": "xianyu_ws_sync",
            })
            if status == "refund_open":
                await self.runtime.alerts.create(
                    "P1", "refund_request", f"平台退款：{parsed['order_no']}",
                    f"买家「{parsed['buyer_nick']}」的订单进入退款中，请到订单页处理。\n"
                    f"金额：¥{parsed['amount_cents'] / 100:.2f}",
                    order_id=order_id, dedupe_minutes=30,
                )
            return "inserted"

        old = dict(existing)
        parsed["local_order_id"] = old["id"]
        new_status = parsed["status"]
        # 终态不回退；本地已进入发货/售后流程时也不被平台的滞后状态拉回
        no_regress = {"shipped", "delivered", "done", "refund_open", "refund_resolved", "cancelled"}
        if old["status"] in _TERMINAL and new_status not in _TERMINAL:
            new_status = old["status"]
        elif old["status"] in no_regress and _RANK.get(new_status, 0) < _RANK.get(old["status"], 0):
            new_status = old["status"]
        fields = {
            "status": new_status,
            "platform_status": parsed["platform_status"],
            "buyer_id": buyer_id,
            "quantity": parsed["quantity"],
            "amount_cents": parsed["amount_cents"],
            "address": parsed["receiver_address"] or old.get("address"),
            "updated_at": now,
        }
        if new_status in ("shipped", "done") and not old.get("shipped_at"):
            fields["shipped_at"] = now
        if new_status in ("paid", "shipped", "done") and not old.get("paid_at"):
            fields["paid_at"] = parsed["placed_at"]
        if new_status == "done" and not old.get("done_at"):
            fields["done_at"] = now
        assignments = ", ".join(f"{k}=?" for k in fields)
        await self.runtime.db.execute(
            f"UPDATE orders SET {assignments} WHERE id=?",
            tuple(fields.values()) + (old["id"],),
        )
        if new_status != old["status"]:
            await self.runtime.bus.emit("order.status_synced", {
                "order_id": old["id"], "from": old["status"], "to": new_status,
                "source": "xianyu_ws_sync",
            })
        if new_status == "refund_open" and old["status"] != "refund_open":
            await self.runtime.alerts.create(
                "P1", "refund_request", f"平台退款：{parsed['order_no']}",
                f"买家「{parsed['buyer_nick']}」的订单进入退款中，请到订单页处理。\n"
                f"金额：¥{parsed['amount_cents'] / 100:.2f}",
                order_id=old["id"], dedupe_minutes=30,
            )
        return "updated"

    async def _maybe_auto_deliver(self, order_id: str, status: str) -> None:
        if status != "paid":
            return
        order = await self.runtime.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
        if not order:
            return
        await self.runtime.fulfillment.handle_order_paid({"order_id": order_id}, {})
