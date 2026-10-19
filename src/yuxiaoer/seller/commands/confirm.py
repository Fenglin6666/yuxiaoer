"""确认门：预览 → 店主确认 → 条件执行 → 回写状态与审计。"""

from __future__ import annotations

from typing import Any

from yuxiaoer.core.state import transition_item
from yuxiaoer.core.util import dumps, iso, new_id, yuan
from yuxiaoer.shared.toolbox import ToolBox

class ConfirmMixin:
    async def resolve(self, confirmation_id: str, approve: bool) -> bool:
        cfm = await self.confirmations.get(confirmation_id)
        if not cfm:
            await self._reply("这个确认项不存在，可能已经处理过了。")
            return False
        if cfm["status"] != "pending":
            await self._reply(f"这个确认项已经{ {'confirmed': '确认过', 'cancelled': '取消', 'expired': '过期'}.get(cfm['status'], cfm['status']) }啦。")
            return False
        if not approve:
            await self.confirmations.mark(confirmation_id, "cancelled", "店主取消")
            await self._cancel_side_effect(cfm)
            await self._reply(f"已取消：{cfm['title']}")
            await self.db.execute(
                "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
                (iso(), "owner", "confirm.cancel", confirmation_id, dumps(cfm["preview"]), "ok"),
            )
            return True

        result = await self._execute(cfm)
        if not result.get("ok"):
            await self._reply(f"执行失败：{result.get('error')}。确认项已保留，可以稍后重试。")
            await self.alerts.create(
                "P1", "confirm_failed", f"确认动作执行失败：{cfm['title']}",
                str(result.get("error")), dedupe_minutes=5,
            )
            return False
        await self.confirmations.mark(confirmation_id, "confirmed", "店主确认")
        if cfm["kind"] == "bargain_price":
            await self.alerts.ack_related(kind="bargain", meta_like=confirmation_id)
        await self._reply(result.get("text") or "已执行完成")
        await self.db.execute(
            "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
            (iso(), "owner", "confirm.approve", confirmation_id, dumps(cfm["preview"]), "ok"),
        )
        return True

    async def _cancel_side_effect(self, cfm: dict[str, Any]) -> None:
        if cfm["kind"] == "publish_listing":
            item_id = (cfm.get("payload") or {}).get("item_id")
            if item_id:
                await self.db.execute(
                    "UPDATE items SET status='draft',updated_at=? WHERE id=? AND status='pending_confirm'",
                    (iso(), item_id),
                )
        if cfm["kind"] == "publish_batch":
            for entry in (cfm.get("payload") or {}).get("items") or []:
                item_id = entry.get("item_id") if isinstance(entry, dict) else entry
                if item_id:
                    await self.db.execute(
                        "UPDATE items SET status='draft',updated_at=? WHERE id=? AND status='pending_confirm'",
                        (iso(), item_id),
                    )

    async def _execute(self, cfm: dict[str, Any]) -> dict[str, Any]:
        kind = cfm["kind"]
        payload = cfm.get("payload") or {}
        if kind == "publish_listing":
            return await self._execute_publish(payload)
        if kind == "publish_batch":
            return await self._execute_batch(payload)
        if kind == "offline_item":
            return await self._execute_offline(payload)
        if kind == "relist_item":
            return await self._execute_relist(payload)
        if kind == "change_price":
            return await self._execute_price(payload, source="seller")
        if kind == "bargain_price":
            return await self._execute_price(payload, source="bargain")
        return {"ok": False, "error": f"未知确认类型 {kind}"}

    async def _execute_publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_id = payload.get("item_id")
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        if not item:
            return {"ok": False, "error": "商品不存在"}
        if item["status"] != "pending_confirm":
            return {"ok": False, "error": f"商品状态为 {item['status']}，不能发布"}
        try:
            published = await self.queue.run(
                lambda: self.channel.publish_item(dict(item)), label=f"publish:{item_id}"
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"平台发布失败：{exc}"}
        ok = await transition_item(
            self.db, self.bus, item_id, ["pending_confirm"], "live",
            fields={"platform_item_id": published.get("platform_item_id")},
            actor="seller_agent", reason="店主确认发布",
        )
        if not ok:
            return {"ok": False, "error": "商品状态已变化，发布未落库"}
        sync = await self.knowledge.sync_item(item_id)
        if self.delivery:
            await self.delivery.ensure_item_cards(item_id)
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        return {
            "ok": True,
            "text": (
                f"已上架：{item['title']}\n价格 ¥{yuan(item['price_cents'])} · {item['delivery_mode'] == 'virtual' and '虚拟自动发货' or '实物待发货'}\n"
                f"链接：{published.get('url')}\n知识库已同步（v{(sync or {}).get('version', 1)}）"
            ),
            "url": published.get("url"),
        }

    async def _execute_relist(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_id = payload.get("item_id")
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        if not item:
            return {"ok": False, "error": "商品不存在"}
        if item["status"] not in ("offline", "sold_out"):
            return {"ok": False, "error": f"商品状态为 {item['status']}，不需要重新上架"}
        try:
            published = await self.queue.run(
                lambda: self.channel.publish_item(dict(item)), label=f"relist:{item_id}"
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"平台重新上架失败：{str(exc)[:240]}"}
        ok = await transition_item(
            self.db, self.bus, item_id, ["offline", "sold_out"], "live",
            fields={
                "platform_item_id": published.get("platform_item_id"),
                "relist_count": int(item["relist_count"]) + 1,
                "listed_at": iso(),
            },
            actor="seller_agent", reason="店主确认重新上架",
        )
        if not ok:
            return {"ok": False, "error": "商品状态已变化，重新上架未落库"}
        sync = await self.knowledge.sync_item(item_id)
        if self.delivery:
            await self.delivery.ensure_item_cards(item_id)
        return {
            "ok": True,
            "text": (
                f"已重新上架：{item['title']}\n价格 ¥{yuan(item['price_cents'])} · 新平台 ID {published.get('platform_item_id')}\n"
                f"链接：{published.get('url')}\n知识库已同步（v{(sync or {}).get('version', 1)}）"
            ),
            "url": published.get("url"),
        }

    async def _execute_offline(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_id = payload.get("item_id")
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        if not item:
            return {"ok": False, "error": "商品不存在"}
        try:
            await self.queue.run(lambda: self.channel.offline_item(dict(item)), label=f"offline:{item_id}")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"平台下架失败：{exc}"}
        ok = await transition_item(
            self.db, self.bus, item_id, ["live", "sold_out"], "offline",
            actor="seller_agent", reason="店主确认下架",
        )
        if not ok:
            return {"ok": False, "error": "商品状态已变化，下架未落库"}
        await self.knowledge.tombstone(f"item:{item_id}")
        return {"ok": True, "text": f"已下架：{item['title']}\n商品知识已打墓碑，买家检索会立即失效。"}

    async def _execute_price(self, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
        item_id = payload.get("item_id")
        new_price = int(payload.get("price_cents") or 0)
        if new_price <= 0:
            return {"ok": False, "error": "价格不合法"}
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        if not item:
            return {"ok": False, "error": "商品不存在"}
        try:
            await self.queue.run(
                lambda: self.channel.change_price(dict(item), new_price), label=f"price:{item_id}"
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"平台改价失败：{exc}"}
        floor = min(int(item["floor_price_cents"]), new_price)
        await self.db.execute(
            "UPDATE items SET price_cents=?,floor_price_cents=?,updated_at=? WHERE id=?",
            (new_price, floor, iso(), item_id),
        )
        sync = await self.knowledge.sync_item(item_id)
        if source == "bargain":
            conv_id = payload.get("conversation_id")
            if conv_id:
                conv = await self.messaging.conversation(conv_id)
                if conv:
                    await self.messaging.send_reply(
                        conv,
                        f"店主同意啦～ 已经帮你改到 ¥{yuan(new_price)}，现在可以直接拍下，马上给你发。",
                        immediate=True, role="agent", meta={"kind": "bargain_price_changed"},
                    )
            return {
                "ok": True,
                "text": f"已改价应价：{item['title']} → ¥{yuan(new_price)}，并已通知买家。知识库 v{(sync or {}).get('version', 1)}",
            }
        return {
            "ok": True,
            "text": f"已改价：{item['title']} → ¥{yuan(new_price)}\n知识库已同步（v{(sync or {}).get('version', 1)}）。",
        }

    async def batch_preview(self, text: str) -> dict[str, Any]:
        seller = await self.messaging.seller_conversation()
        toolbox = ToolBox(
            self.db, turn_id=new_id("sturn"), session_id=seller["session_id"], agent="seller", limit=8
        )
        result = await self._batch_listing(text, toolbox)
        await self._reply(result.get("text") or "", card=result.get("card"))
        return result

    async def _execute_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items") or []
        published: list[str] = []
        failed: list[str] = []
        for entry in items:
            item_id = entry.get("item_id") if isinstance(entry, dict) else entry
            item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
            if not item:
                failed.append(f"{item_id} 不存在")
                continue
            if item["status"] != "pending_confirm":
                failed.append(f"{item['title']} 状态 {item['status']}")
                continue
            try:
                result = await self.queue.run(
                    lambda it=dict(item): self.channel.publish_item(it), label=f"batch_publish:{item_id}"
                )
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{item['title']} 平台失败：{exc}")
                continue
            ok = await transition_item(
                self.db, self.bus, item_id, ["pending_confirm"], "live",
                fields={"platform_item_id": result.get("platform_item_id")},
                actor="seller_agent", reason="店主确认批量发布",
            )
            if not ok:
                failed.append(f"{item['title']} 状态已变化")
                continue
            await self.knowledge.sync_item(item_id)
            if self.delivery:
                await self.delivery.ensure_item_cards(item_id)
            published.append(item["title"])
        if failed:
            await self.alerts.create(
                "P1", "batch_publish_partial", "批量发布部分失败",
                "失败：" + "；".join(failed[:5]), dedupe_minutes=5,
            )
        text = f"批量发布完成：成功 {len(published)} 件"
        if published:
            text += "\n" + "\n".join(f"· {t}" for t in published)
        if failed:
            text += f"\n失败 {len(failed)} 件：" + "；".join(failed[:5])
        return {"ok": not failed, "text": text, "published": published, "failed": failed, "error": "部分失败" if failed else None}
