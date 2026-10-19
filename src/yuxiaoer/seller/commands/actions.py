"""店主指令：下架/改价/发货/订单/日报/接管/帮助。"""

from __future__ import annotations

import re
from typing import Any

from yuxiaoer.core.util import (
    dumps,
    human_time,
    iso,
    loads,
    local_now,
    start_of_local_day,
    yuan,
)
from yuxiaoer.shared.toolbox import ToolBox

from ..constants import TRACKING_COMPANIES
from ._shared import clean_query, propose


class CommandActionsMixin:
    async def _takeover_command(self, text: str) -> dict[str, Any]:
        target = re.sub(r"^(人工|接管|转人工)[:：]?\s*", "", text).strip()
        conv = await self._find_conversation(target, require_handoff=False)
        if not conv:
            return {"ok": False, "text": f"没找到「{target or '最近'}」对应的会话，请说「人工 买家昵称」。"}
        await self.messaging.set_handoff(conv["id"], "店主指令接管", minutes=120)
        await self.alerts.ack_related(kind="handoff", conversation_id=conv["id"])
        return {"ok": True, "text": f"已接管「{conv.get('buyer_nick') or conv['buyer_id']}」的会话，自动回复暂停 2 小时。"}

    async def _resume_command(self, text: str) -> dict[str, Any]:
        target = re.sub(r"^(恢复托管|恢复|自动回复|释放)[:：]?\s*", "", text).strip()
        conv = await self._find_conversation(target, require_handoff=True)
        if not conv:
            return {"ok": False, "text": "当前没有待恢复的接管会话。"}
        await self.messaging.resume(conv["id"])
        await self.alerts.ack_related(kind="handoff", conversation_id=conv["id"])
        return {"ok": True, "text": f"已恢复「{conv.get('buyer_nick') or conv['buyer_id']}」的自动托管。"}

    async def _find_conversation(self, query: str, *, require_handoff: bool) -> dict[str, Any] | None:
        sql = (
            "SELECT c.*,b.nick AS buyer_nick,i.title AS item_title FROM conversations c "
            "LEFT JOIN buyers b ON b.id=c.buyer_id LEFT JOIN items i ON i.id=c.item_id "
            "WHERE c.id!='conv_seller' AND c.status='active'"
        )
        params: list[Any] = []
        if require_handoff:
            sql += " AND c.handoff=1"
        if query:
            sql += " AND (b.nick LIKE ? OR i.title LIKE ? OR c.buyer_id LIKE ?)"
            params.extend([f"%{query}%"] * 3)
        sql += " ORDER BY COALESCE(c.last_message_at,c.created_at) DESC LIMIT 1"
        row = await self.db.fetchone(sql, params)
        return dict(row) if row else None

    async def _offline(self, text: str, toolbox: ToolBox) -> dict[str, Any]:
        query = clean_query(text, r"(下架|撤下|删除)")
        matches = await self._find_items(query)
        if not matches:
            return {"ok": False, "text": f"没找到「{query}」对应的在售商品，可以说得更具体一点，或先发「订单？」看看。"}
        if len(matches) > 1:
            titles = "、".join(f"「{m['title']}」" for m in matches[:5])
            return {"ok": False, "text": f"匹配到多件商品：{titles}。请把商品名再说具体一点。"}
        item = matches[0]
        if item["status"] == "offline":
            return {"ok": False, "text": f"「{item['title']}」已经是下架状态啦。"}
        if item["status"] not in ("live", "sold_out"):
            return {"ok": False, "text": f"「{item['title']}」当前是 {item['status']}，还没有上架，不能下架。"}
        preview = {
            "kind": "offline_item", "item_id": item["id"], "title": item["title"],
            "price_cents": item["price_cents"], "status": item["status"],
        }
        return await propose(
            self.confirmations,
            toolbox,
            kind="offline_item",
            title=f"下架商品：{item['title']}",
            preview=preview,
            payload={"item_id": item["id"]},
            text=f"要下架「{item['title']}」（¥{yuan(item['price_cents'])}）吗？确认后我会下架并同步知识库墓碑。",
        )

    async def _relist(self, text: str, toolbox: ToolBox) -> dict[str, Any]:
        query = clean_query(text, r"(重新上架|重新发布|再上架|续售|恢复上架|重新挂)")
        matches = [m for m in await self._find_items(query) if m["status"] in ("offline", "sold_out")]
        if not matches:
            return {"ok": False, "text": f"没找到「{query}」对应的已下架/已售出商品。"}
        if len(matches) > 1:
            titles = "、".join(f"「{m['title']}」" for m in matches[:5])
            return {"ok": False, "text": f"匹配到多件商品：{titles}。请指定要重新上架哪一件。"}
        item = matches[0]
        meta = loads(item["meta_json"], {}) or {}
        options = meta.get("publish") if isinstance(meta.get("publish"), dict) else {}
        if not options:
            image_url = str(meta.get("image_url") or "").strip()
            options, missing = await self._auto_publish_options(
                item["title"], item["description"] or item["title"], text,
                [image_url] if image_url else [], item["delivery_mode"] == "virtual",
            )
            if not options:
                return {"ok": False, "text": "缺少发布参数（图片/分类/所在地）。" + missing}
            meta["publish"] = options
            await self.db.execute(
                "UPDATE items SET meta_json=?,updated_at=? WHERE id=?", (dumps(meta), iso(), item["id"])
            )
        preview = {
            "kind": "relist_item", "item_id": item["id"], "title": item["title"],
            "price_cents": item["price_cents"], "status": item["status"],
            "images": options.get("images") or [],
            "publish_category": (options.get("category") or {}).get("cat_name"),
            "publish_address": options.get("address"),
        }
        return await propose(
            self.confirmations,
            toolbox,
            kind="relist_item",
            title=f"重新上架：{item['title']}",
            preview=preview,
            payload={"item_id": item["id"]},
            text=(
                f"要重新上架「{item['title']}」（¥{yuan(item['price_cents'])}）吗？\n"
                "确认后会按保存的发布参数重新发布一条新商品；旧的已下架商品仍保留在闲鱼后台。"
            ),
        )

    async def _change_price(self, text: str, toolbox: ToolBox) -> dict[str, Any]:
        price, _ = self._extract_price(text)
        if not price:
            return {"ok": False, "text": "改价要带新价格，例如：改价 Kindle 到 199 元。"}
        query = clean_query(
            text,
            r"(改价|改价格|调价|价格改)",
            extra=(
                r"(到|改成|改为|至)\s*\d+(?:\.\d{1,2})?\s*(?:元|块)?"
                r"|\d+(?:\.\d{1,2})?\s*(?:元|块)?|(到|改成|改为)"
            ),
        )
        matches = await self._find_items(query)
        if not matches:
            return {"ok": False, "text": f"没找到「{query}」对应的商品，请把商品名说具体一点。"}
        if len(matches) > 1:
            titles = "、".join(f"「{m['title']}」" for m in matches[:5])
            return {"ok": False, "text": f"匹配到多件商品：{titles}。请指定要改哪一件。"}
        item = matches[0]
        if item["status"] != "live" or not item["platform_item_id"]:
            return {"ok": False, "text": f"「{item['title']}」还没有真正上架（或没有平台 ID），不能改价。"}
        preview = {
            "kind": "change_price", "item_id": item["id"], "title": item["title"],
            "old_price_cents": item["price_cents"], "new_price_cents": price,
            "old_price_text": f"¥{yuan(item['price_cents'])}", "new_price_text": f"¥{yuan(price)}",
        }
        return await propose(
            self.confirmations,
            toolbox,
            kind="change_price",
            title=f"改价：{item['title']}",
            preview=preview,
            payload={"item_id": item["id"], "price_cents": price},
            tool_args={"item_id": item["id"], "price": price},
            text=f"把「{item['title']}」从 ¥{yuan(item['price_cents'])} 改到 ¥{yuan(price)}？确认后执行。",
        )

    async def _ship(self, text: str, toolbox: ToolBox) -> dict[str, Any]:
        order_id_match = re.search(r"(ord_[a-z0-9]+)", text)
        order = None
        if order_id_match:
            row = await self.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id_match.group(1),))
            order = dict(row) if row else None
        if not order:
            rows = await self.db.fetchall(
                "SELECT o.*,i.title FROM orders o JOIN items i ON i.id=o.item_id "
                "WHERE o.status='paid' ORDER BY o.created_at DESC"
            )
            if len(rows) == 1:
                order = dict(rows[0])
            elif len(rows) > 1:
                lines = [
                    f"· {r['id']}｜{r['title']}｜¥{yuan(r['amount_cents'])}｜{r['buyer_id']}"
                    for r in rows[:6]
                ]
                return {
                    "ok": False,
                    "text": "有多个待发货订单，请指定订单号：\n" + "\n".join(lines)
                            + "\n\n格式：发货 ord_xxx 顺丰 SF123456789",
                }
            else:
                return {"ok": False, "text": "现在没有待发货订单。"}
        if order["status"] != "paid":
            return {"ok": False, "text": f"订单 {order['id']} 状态为 {order['status']}，不能发货。"}

        company = next((c for c in TRACKING_COMPANIES if c.lower() in text.lower()), "快递")
        no_match = re.search(r"(?<![A-Za-z0-9])([A-Za-z]{2,4}\d{8,20})(?![A-Za-z0-9])", text) or re.search(
            r"(?<!\d)(\d{10,20})(?!\d)", text
        )
        if not no_match:
            return {"ok": False, "text": "没有识别到快递单号。请按「发货 <订单号> 顺丰 <单号>」格式再发一次。"}
        tracking_no = no_match.group(1)
        filled = await toolbox.call(
            "fill_tracking_no", {"order_id": order["id"], "company": company, "tracking_no": tracking_no},
            lambda: self.orders.fill_tracking(order["id"], company, tracking_no),
        )
        result = filled.get("data") or {}
        if not result.get("ok"):
            return {"ok": False, "text": f"回填失败：{result.get('error') or filled.get('error')}"}
        item = await self.db.fetchone("SELECT title FROM items WHERE id=?", (order["item_id"],))
        return {
            "ok": True,
            "text": f"已回填单号：{company} {tracking_no}\n订单：{order['id']}｜{item['title'] if item else ''}\n已自动通知买家。",
            "card": {"type": "shipped", "order_id": order["id"], "company": company, "tracking_no": tracking_no},
        }

    async def _orders_summary(self, toolbox: ToolBox) -> tuple[str, dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT o.*,i.title FROM orders o JOIN items i ON i.id=o.item_id "
            "ORDER BY CASE o.status WHEN 'refund_open' THEN 0 WHEN 'paid' THEN 1 ELSE 2 END,o.created_at DESC LIMIT 12"
        )
        counts = {r["status"]: 0 for r in rows}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        labels = {"paid": "待发货", "refund_open": "退款中", "shipped": "已发货", "done": "已完成",
                  "delivered": "已送达", "refund_resolved": "退款已处理", "new": "新订单", "cancelled": "已取消"}
        head = f"订单概览：待发货 {counts.get('paid', 0)} · 退款中 {counts.get('refund_open', 0)} · 已发货 {counts.get('shipped', 0)}"
        lines = [head]
        for r in rows[:6]:
            lines.append(
                f"· {r['id']}｜{r['title']}｜¥{yuan(r['amount_cents'])}｜{labels.get(r['status'], r['status'])}｜{r['buyer_id']}"
            )
        lines.append("\n发货：发货 <订单号> 顺丰 <单号>；退款处理请到「订单履约」页。")
        await toolbox.call("get_orders", {"limit": 12}, lambda: {"count": len(rows)})
        card = {"type": "order_list", "orders": [
            {"id": r["id"], "title": r["title"], "amount_cents": r["amount_cents"],
             "status": r["status"], "status_text": labels.get(r["status"], r["status"]),
             "buyer_id": r["buyer_id"], "created_at": r["created_at"]} for r in rows[:8]
        ]}
        return "\n".join(lines), card

    async def _daily_report(self) -> str:
        since = iso(start_of_local_day(0))
        conversations = await self.db.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE created_at>=? AND id!='conv_seller'", (since,), 0
        )
        inbound = await self.db.fetchval(
            "SELECT COUNT(*) FROM messages WHERE direction='in' AND role='buyer' AND created_at>=?", (since,), 0
        )
        outbound = await self.db.fetchval(
            "SELECT COUNT(*) FROM messages WHERE direction='out' AND role='agent' AND created_at>=?", (since,), 0
        )
        paid = await self.db.fetchval(
            "SELECT COUNT(*),COALESCE(SUM(amount_cents),0) FROM orders WHERE paid_at>=?", (since,)
        )
        handoff = await self.db.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE handoff=1 AND updated_at>=?", (since,), 0
        )
        pending_ship = await self.db.count("orders", "status='paid'")
        refunds = await self.db.count("orders", "status='refund_open'")
        paid_count = paid[0] if paid else 0
        gmv = paid[1] if paid else 0
        return (
            f"📊 今日经营日报（{local_now().strftime('%m-%d')}）\n"
            f"· 新咨询 {conversations} 个会话 / {inbound} 条买家消息\n"
            f"· 自动回复 {outbound} 条，转人工 {handoff} 个\n"
            f"· 成交 {paid_count} 单，GMV ¥{yuan(gmv)}\n"
            f"· 待发货 {pending_ship} 单，退款处理中 {refunds} 单\n"
            "需要我处理哪一项，直接说就行。"
        )

    async def _pending_text(self) -> str:
        rows = await self.confirmations.list("pending", 10)
        if not rows:
            return "现在没有待确认的操作。"
        lines = ["待确认："]
        for r in rows:
            lines.append(f"· {r['title']}（{human_time(r['created_at'])}，{r['id']}）")
        lines.append("回复「确认」执行最近一条，或到卡片上点按钮。")
        return "\n".join(lines)

    async def _help_text(self) -> str:
        return (
            "我可以直接替你操作：\n"
            "· 发图片 + 描述，我自动补标题/价格/分类/所在地，再给你发布预览\n"
            "· 上架：<标题> <价格> <描述> —— 也可以手写价格和标题\n"
            "· 下架 <商品名> / 改价 <商品名> 到 199 / 重新上架 <商品名>\n"
            "· 发布设置 图片=... 分类ID=... 分类名=... 地址=...（可选覆盖）\n"
            "· 订单？ / 发货 <订单号> <快递公司> <单号>\n"
            "· 人工 <买家昵称> / 恢复 <买家昵称> —— 接管或恢复自动托管\n"
            "· 日报 / 擦亮 / 待确认\n"
            "上架/改价/下架都会先给你确认卡，确认后才动平台。"
        )
