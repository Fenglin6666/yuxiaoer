"""卖家 Agent（单例）：店主对话指令 → 意图解析 → 预览/确认 → 原生执行。

资金/上架类动作全部两段式：先返回预览卡，店主回"确认"或点按钮后才执行。
"""

from __future__ import annotations

import json
import re
from typing import Any

from yuxiaoer.seller.notifications.alerts import AlertService
from yuxiaoer.buyer.conversation.agent import ToolBox
from yuxiaoer.seller.platform.channels import BaseChannel
from yuxiaoer.seller.confirmations import ConfirmationService
from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.buyer.knowledge.service import KnowledgeService
from yuxiaoer.core.llm import LLMClient
from yuxiaoer.seller.conversation.messaging import MessagingService
from yuxiaoer.seller.commerce.orders import OrderService
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.state import transition_item
from yuxiaoer.core.util import (
    dumps, human_time, iso, loads, local_now, new_id, now_utc, parse_iso,
    percentile, snippet, start_of_local_day, yuan,
)
from yuxiaoer.seller.write_queue import WriteQueue

YES_WORDS = {"确认", "确定", "是", "好", "可以", "同意", "执行", "发布", "上架", "ok", "yes"}
CANCEL_WORDS = {"取消", "算了", "不要了", "否", "no", "cancel"}
TRACKING_COMPANIES = ["顺丰", "京东", "中通", "圆通", "韵达", "申通", "极兔", "邮政", "EMS", "德邦"]

VIRTUAL_HINTS = [
    "资料", "电子", "pdf", "PDF", "课程", "模板", "软件", "教程", "素材", "源码",
    "卡券", "链接", "会员", "笔记", "真题", "网课", "题库", "电子书", "虚拟",
]
PHYSICAL_HINTS = ["实物", "包邮", "成色", "二手", "全新", "挂件", "手机", "相机", "耳机", "书", "衣服", "鞋"]


class SellerAgent:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        messaging: MessagingService,
        alerts: AlertService,
        knowledge: KnowledgeService,
        confirmations: ConfirmationService,
        orders: OrderService,
        channel: BaseChannel,
        queue: WriteQueue,
        settings: SettingsService,
        llm: LLMClient,
    ):
        self.db = db
        self.bus = bus
        self.messaging = messaging
        self.alerts = alerts
        self.knowledge = knowledge
        self.confirmations = confirmations
        self.orders = orders
        self.channel = channel
        self.queue = queue
        self.settings = settings
        self.llm = llm
        self.patrol: Any = None
        self.delivery: Any = None

    def set_patrol(self, patrol: Any) -> None:
        self.patrol = patrol

    # ---------------- 入口 ----------------

    async def ensure_welcome(self) -> None:
        seller = await self.messaging.seller_conversation()
        count = await self.db.count("messages", "conversation_id=?", (seller["id"],))
        if count > 0:
            return
        await self._reply(
            "店主你好，我是鱼小二 👋\n"
            "买家消息我会 24h 托管，遇到退款/纠纷/风险消息会在这里提醒你。\n\n"
            "你可以直接对我说：\n"
            "· 发图片 + 描述，我自动补标题、价格、分类、所在地\n"
            "· 上架：标题 价格 描述 / 改价 商品名 到 199 / 下架 商品名\n"
            "· 发布设置 图片=… 分类ID=… 地址=…（可选，覆盖自动参数）\n"
            "· 订单？ / 发货 ord_xxx 顺丰 SF123456789\n"
            "· 人工 <买家昵称> / 恢复 <买家昵称>\n"
            "· 日报 / 擦亮 / 帮助\n"
            "上架、改价、下架都会先给你确认卡。",
        )

    async def handle(self, text: str, images: list[str] | None = None) -> dict[str, Any]:
        text = (text or "").strip()
        seller = await self.messaging.seller_conversation()
        if not text:
            return {"ok": False, "error": "空消息"}
        await self.messaging.add_local_message(
            seller["id"], text, role="owner", direction="in",
            meta={"source": "owner", "images": images or []},
        )
        toolbox = ToolBox(
            self.db, turn_id=new_id("sturn"), session_id=seller["session_id"], agent="seller", limit=8
        )
        normalized = re.sub(r"[\s，。！!？?]+", "", text)

        pending = await self.confirmations.latest_pending()
        specific = re.match(r"^(确认|同意|执行|取消)(cfm_[A-Za-z0-9]+)$", normalized, re.I)
        if specific:
            action, confirmation_id = specific.group(1), specific.group(2)
            approve = action != "取消"
            ok = await self.resolve(confirmation_id, approve)
            return {"ok": ok, "action": "confirm" if approve else "cancel", "confirmation_id": confirmation_id}
        if pending and (normalized.lower() in YES_WORDS or normalized.startswith("确认") and len(normalized) <= 10):
            ok = await self.resolve(pending["id"], True)
            return {"ok": ok, "action": "confirm", "confirmation_id": pending["id"]}
        if pending and normalized.lower() in CANCEL_WORDS:
            await self.resolve(pending["id"], False)
            return {"ok": True, "action": "cancel", "confirmation_id": pending["id"]}

        if re.match(r"^(帮助|help|怎么用|使用说明)$", normalized, re.I):
            await self._reply(await self._help_text())
            return {"ok": True, "action": "help"}
        if re.match(r"^(待确认|确认项|待办|pending)$", normalized, re.I):
            await self._reply(await self._pending_text())
            return {"ok": True, "action": "pending"}
        if re.match(r"^(日报|报告|今日报告|经营日报)$", normalized, re.I):
            report = await self._daily_report()
            await self._reply(report)
            return {"ok": True, "action": "report"}
        if re.match(r"^(擦亮|擦亮全部|一键擦亮)$", normalized, re.I):
            if not self.patrol:
                await self._reply("值守服务还没启动，稍后再试～")
                return {"ok": False, "error": "patrol unavailable"}
            result = await self.patrol.run_job("polish", manual=True)
            await self._reply(result.get("text") or "擦亮完成")
            return {"ok": True, "action": "polish", "result": result}
        if re.match(r"^(发布设置|上架配置|发布参数|设置发布|发布配置)", normalized, re.I):
            result = await self._publish_settings(text)
            await self._reply(result["text"])
            return {"ok": result["ok"], "action": "publish_settings"}
        if re.search(r"(重新上架|重新发布|再上架|续售|恢复上架|重新挂)", normalized, re.I):
            result = await self._relist(text, toolbox)
            await self._reply(result["text"], card=result.get("card"))
            return {"ok": result["ok"], "action": "relist"}
        if re.search(r"(改价|改价格|调价|价格改|改到|改成)", normalized, re.I) and re.search(r"\d", normalized):
            result = await self._change_price(text, toolbox)
            await self._reply(result["text"], card=result.get("card"))
            return {"ok": result["ok"], "action": "change_price"}
        if re.search(r"(下架|撤下|删除)", normalized, re.I):
            result = await self._offline(text, toolbox)
            await self._reply(result["text"], card=result.get("card"))
            return {"ok": result["ok"], "action": "offline"}
        if re.search(r"(上架|发布|发品|新品|新增商品)", normalized, re.I):
            result = await self._listing(text, toolbox, images=images)
            await self._reply(result["text"], card=result.get("card"))
            return {"ok": result["ok"], "action": "listing", "item_id": result.get("item_id")}
        if re.match(r"^(订单|订单\?|订单？|查订单|我的订单|待发货)$", normalized, re.I):
            text_out, card = await self._orders_summary(toolbox)
            await self._reply(text_out, card=card)
            return {"ok": True, "action": "orders"}
        if re.match(r"^(发货|填单号|快递单号|回填快递)", normalized, re.I) or (
            re.search(r"[A-Za-z]{2,4}\d{8,}", text) and "订单" not in text
        ):
            result = await self._ship(text, toolbox)
            await self._reply(result["text"], card=result.get("card"))
            return {"ok": result["ok"], "action": "ship", "error": result.get("error")}
        if re.match(r"^(人工|接管|转人工)", normalized, re.I):
            result = await self._takeover_command(text)
            await self._reply(result["text"])
            return {"ok": result["ok"], "action": "takeover", "error": result.get("error")}
        if re.match(r"^(恢复|恢复托管|自动回复|释放)", normalized, re.I):
            result = await self._resume_command(text)
            await self._reply(result["text"])
            return {"ok": result["ok"], "action": "resume", "error": result.get("error")}
        if images:
            # 图片 + 描述即视为上架意图，不需要额外写“上架”前缀
            result = await self._listing(text, toolbox, images=images)
            await self._reply(result["text"], card=result.get("card"))
            return {"ok": result["ok"], "action": "listing", "item_id": result.get("item_id")}

        await self._reply(await self._help_text())
        return {"ok": True, "action": "help"}

    # ---------------- 确认门 ----------------

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

    # ---------------- 指令实现 ----------------

    async def _publish_options(self) -> tuple[dict[str, Any] | None, str]:
        """读取店主通过「发布设置」配置的默认发布参数。"""
        raw_images = (await self.settings.get("publish_images")).strip()
        images: list[str] = []
        if raw_images:
            if raw_images.startswith("["):
                try:
                    images = [str(x).strip() for x in json.loads(raw_images) if str(x).strip()]
                except Exception:
                    images = []
            else:
                images = [x.strip() for x in re.split(r"[\n,，]", raw_images) if x.strip()]
        category = {
            "cat_id": (await self.settings.get("publish_cat_id")).strip(),
            "cat_name": (await self.settings.get("publish_cat_name")).strip(),
            "channel_cat_id": (await self.settings.get("publish_channel_cat_id")).strip(),
            "tb_cat_id": (await self.settings.get("publish_tb_cat_id")).strip(),
        }
        address = (await self.settings.get("publish_address")).strip()
        geo_raw = (await self.settings.get("publish_address_geo")).strip()
        geo = None
        if geo_raw:
            try:
                geo = json.loads(geo_raw)
            except Exception:
                geo = None
        options = {
            "images": images,
            "category": category,
            "address": address,
            "shipping_method": (await self.settings.get("publish_shipping_method")).strip() or "free",
            "mode": (await self.settings.get("publish_mode")).strip() or "personal",
            "quantity": 1,
        }
        if isinstance(geo, dict):
            options["address_geo"] = geo
        missing = []
        if not images:
            missing.append("图片")
        if not (category["cat_id"] or category["channel_cat_id"]) or not category["cat_name"]:
            missing.append("分类ID/分类名")
        if not address and not geo:
            missing.append("所在地")
        if missing:
            return None, (
                "发布参数还不全：缺 " + "、".join(missing) + "。\n"
                "先发一条配置，例如：\n"
                "发布设置 图片=https://xx/1.jpg,https://xx/2.jpg 分类ID=123 分类名=虚拟资料 地址=杭州市西湖区\n"
                "可选：频道分类ID=... 淘宝分类ID=... 模式=personal|shop 运费=free|none|fixed"
            )
        return options, ""

    async def _auto_publish_options(
        self, title: str, description: str, raw: str, images: list[str] | None, virtual: bool,
    ) -> tuple[dict[str, Any] | None, str]:
        """根据图片 + 描述自动补全发布参数；分类优先调平台推荐。"""
        image_list = [str(x).strip() for x in (images or []) if str(x).strip()]
        if not image_list:
            raw_images = (await self.settings.get("publish_images")).strip()
            image_list = [x.strip() for x in re.split(r"[\n,，]", raw_images) if x.strip()]
        if not image_list:
            return None, "把商品图片一起发给我（点输入框左侧的图片按钮），我就能按描述自动补参数。"
        category = {
            "cat_id": (await self.settings.get("publish_cat_id")).strip(),
            "cat_name": (await self.settings.get("publish_cat_name")).strip(),
            "channel_cat_id": (await self.settings.get("publish_channel_cat_id")).strip(),
            "tb_cat_id": (await self.settings.get("publish_tb_cat_id")).strip(),
        }
        if not (category["cat_id"] or category["channel_cat_id"]) or not category["cat_name"]:
            recommend = getattr(self.channel, "recommend_category", None)
            if recommend is None:
                return None, "当前通道不支持分类推荐，请先发「发布设置 分类ID=… 分类名=…」。"
            try:
                rows = await recommend(title, description)
            except Exception as exc:
                return None, f"分类自动推荐失败：{str(exc)[:180]}。可以发「发布设置 分类ID=… 分类名=…」手动指定。"
            if not rows:
                return None, "平台没有返回可用分类；请发「发布设置 分类ID=… 分类名=…」。"
            best = rows[0]
            category = {
                "cat_id": str(best.get("cat_id") or ""),
                "cat_name": str(best.get("cat_name") or best.get("channel_cat_name") or ""),
                "channel_cat_id": str(best.get("channel_cat_id") or ""),
                "channel_cat_name": str(best.get("channel_cat_name") or ""),
                "tb_cat_id": str(best.get("tb_cat_id") or ""),
                "leaf_id": str(best.get("leaf_id") or ""),
            }
        address = (await self.settings.get("publish_address")).strip()
        if not address:
            city = re.search(
                r"(北京|上海|广州|深圳|杭州|南京|苏州|成都|重庆|武汉|西安|天津|长沙|郑州|青岛|宁波|厦门|福州|合肥|济南|昆明|大连|沈阳|无锡|佛山|东莞)(?:市)?",
                raw,
            )
            address = city.group(1) + "市" if city else (await self.settings.get("publish_default_address")).strip()
        options = {
            "images": image_list,
            "category": category,
            "address": address or "杭州市",
            "shipping_method": (await self.settings.get("publish_shipping_method")).strip()
            or ("none" if virtual else "free"),
            "mode": (await self.settings.get("publish_mode")).strip() or "personal",
            "quantity": 1,
        }
        geo_raw = (await self.settings.get("publish_address_geo")).strip()
        if geo_raw:
            try:
                geo = json.loads(geo_raw)
                if isinstance(geo, dict):
                    options["address_geo"] = geo
            except Exception:
                pass
        return options, ""

    async def _publish_settings(self, text: str) -> dict[str, Any]:
        raw = re.sub(r"^(发布设置|上架配置|发布参数|设置发布|发布配置)[:：]?\s*", "", text).strip()
        pairs = re.findall(
            r"(频道分类ID|淘宝分类ID|分类ID|分类名|图片|地址|模式|运费)\s*[=:：]\s*(\S+)",
            raw, re.I,
        )
        mapping = {
            "图片": "publish_images",
            "分类ID": "publish_cat_id",
            "分类名": "publish_cat_name",
            "频道分类ID": "publish_channel_cat_id",
            "淘宝分类ID": "publish_tb_cat_id",
            "地址": "publish_address",
            "模式": "publish_mode",
            "运费": "publish_shipping_method",
        }
        if pairs:
            for key, value in pairs:
                await self.settings.set(mapping[key], value.strip())
        options, missing = await self._publish_options()
        if not options:
            if pairs:
                return {"ok": True, "text": "已保存这次设置。\n" + missing + "\n其余参数可以在上架时用图片+描述自动补。"}
            return {"ok": False, "text": missing}
        return {
            "ok": True,
            "text": (
                "发布参数已保存。\n"
                f"图片：{len(options['images'])} 张\n"
                f"分类：{options['category'].get('cat_name') or '—'}（{options['category'].get('cat_id') or options['category'].get('channel_cat_id') or '—'}）\n"
                f"所在地：{options.get('address') or '使用坐标'}\n"
                f"模式：{options.get('mode')} · 运费：{options.get('shipping_method')}\n"
                "现在可以直接说：上架：标题 价格 描述"
            ),
        }

    async def _listing(self, text: str, toolbox: ToolBox, images: list[str] | None = None) -> dict[str, Any]:
        raw = re.sub(r"^(上架|发布|发品|新品|新增商品)[:：]?\s*", "", text).strip()
        if not raw:
            return {"ok": False, "text": "把商品描述一起发我，例如：上架：小学奥数全套资料 9.9元 电子资料，拍下自动发。"}
        card_content = None
        card_match = re.search(r"(?:卡券|卡密|发货内容)[:：]\s*(.+)$", raw, re.S | re.I)
        if card_match:
            card_content = card_match.group(1).strip()[:4000]
            raw = raw[: card_match.start()].strip()
        price, raw_no_price = self._extract_price(raw)
        virtual = any(h in raw for h in VIRTUAL_HINTS) and not any(h in raw for h in ["实物", "包邮"])
        if not price:
            price = await self.settings.get_int("publish_default_price", 990)
        floor_pct = await self.settings.get_int("floor_discount_pct", 85)
        floor = max(1, int(round(price * max(0, min(100, floor_pct)) / 100)))
        lines = [line.strip() for line in raw_no_price.splitlines() if line.strip()]
        first_line = lines[0] if lines else raw_no_price
        title = re.sub(r"^(商品|标题)[:：]", "", first_line).strip(" -—:：")
        rest = ""
        if len(lines) > 1:
            rest = "\n".join(lines[1:]).strip()
        else:
            parts = re.split(r"[，,。；;]", title, maxsplit=1)
            if len(parts) > 1:
                title, rest = parts[0], parts[1].strip()
        # 标题里去掉明显的发货/类型修饰，保留成色等卖点；被去掉的词仍留在描述里
        removed = ""
        match = re.search(
            r"\s*(电子资料|虚拟商品|虚拟资料|实物商品|拍下自动发\w*|拍下后自动发\w*|包邮|48小时内发\w*)\s*$",
            title,
        )
        if match:
            removed = match.group(1)
            title = title[: match.start()]
        title = re.sub(r"\s+", " ", title).strip()
        title = title[:30]
        if len(title) < 2:
            title = self._fallback_title(raw_no_price, virtual)
        # 用"原句去掉标题"得到描述，避免只剩半句
        remainder = first_line.replace(title, "", 1).strip(" ，,。")
        if len(lines) > 1:
            desc_parts = [p for p in (remainder, rest) if p]
            desc = "，".join(dict.fromkeys(desc_parts)).strip()
        else:
            desc = remainder
        if not desc:
            desc = raw_no_price
        policy = (
            "虚拟资料，拍下后自动发网盘链接，链接失效免费补发。"
            if virtual else
            "实物拍摄，包邮，48 小时内发出；二手物品非质量问题不退换。"
        )
        if policy not in desc:
            desc = f"{desc}\n{policy}"
        desc = re.sub(r"([，,。；;])\1+", r"\1", desc).strip()[:1000]
        condition = "电子资料" if virtual else self._extract_condition(raw)
        category = self._category(raw, virtual)
        delivery_mode = "virtual" if virtual else "physical"
        if self.llm.available():
            polished = await self._llm_listing(title, desc, price, delivery_mode)
            if polished:
                title = polished.get("title") or title
                desc = polished.get("description") or desc
        publish_options, missing = await self._auto_publish_options(
            title, desc, raw, images, virtual,
        )
        if not publish_options:
            return {"ok": False, "text": missing}
        item_id = await self._create_pending_item(
            title=title, description=desc, price=price, floor=floor, virtual=virtual,
            condition=condition, category=category, floor_pct=floor_pct, card_content=card_content,
            publish_options=publish_options,
        )
        preview = {
            "kind": "publish_listing", "item_id": item_id, "title": title,
            "description": desc, "price_cents": price, "floor_price_cents": floor,
            "delivery_mode": delivery_mode, "condition": condition, "category": category,
            "price_text": f"¥{yuan(price)}", "has_card": bool(card_content),
            "images": publish_options.get("images") or [],
            "publish_category": (publish_options.get("category") or {}).get("cat_name"),
            "publish_category_id": (publish_options.get("category") or {}).get("cat_id"),
            "publish_channel_cat_id": (publish_options.get("category") or {}).get("channel_cat_id"),
            "publish_tb_cat_id": (publish_options.get("category") or {}).get("tb_cat_id"),
            "publish_leaf_id": (publish_options.get("category") or {}).get("leaf_id"),
            "publish_address": publish_options.get("address"),
            "publish_shipping_method": publish_options.get("shipping_method"),
            "publish_mode": publish_options.get("mode"),
            "stock": publish_options.get("quantity"),
        }
        cfm = await self.confirmations.create(
            "publish_listing", f"发布商品：{title}", preview, {"item_id": item_id}, source="seller_agent"
        )
        card = {"type": "confirmation", "confirmation_id": cfm["id"], "preview": preview}
        await toolbox.call(
            "draft_listing", {"item_id": item_id, "title": title, "price_cents": price},
            lambda: {"item_id": item_id, "status": "pending_confirm"},
        )
        text_out = (
            f"拟好了一版，确认后我再发布 👇\n"
            f"标题：{title}\n价格：¥{yuan(price)}（底价 ¥{yuan(floor)}）\n"
            f"类型：{'虚拟自动发货' if virtual else '实物待发货'}\n"
            "回复「确认」或点卡片按钮发布；回复「取消」放弃。"
        )
        return {"ok": True, "text": text_out, "card": card, "item_id": item_id}

    async def _create_pending_item(
        self, *, title: str, description: str, price: int, floor: int, virtual: bool,
        condition: str, category: str, floor_pct: int, card_content: str | None = None,
        publish_options: dict[str, Any] | None = None,
    ) -> str:
        item_id = new_id("item")
        now = iso()
        await self.db.execute(
            """INSERT INTO items(id,title,description,price_cents,floor_price_cents,max_discount_pct,category,
               condition,delivery_mode,stock,status,card_content,link_url,image_hint,knowledge_version,
               relist_count,relist_limit,sold_count,created_at,updated_at,meta_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id, title, description, price, floor, max(0, 100 - floor_pct), category,
                condition, "virtual" if virtual else "physical", 1 if not virtual else 999,
                "pending_confirm", card_content, None, "📦", 0, 0, 3, 0, now, now,
                dumps({"created_by": "seller_agent", "publish": publish_options or {}}),
            ),
        )
        return item_id

    async def _batch_listing(self, text: str, toolbox: ToolBox) -> dict[str, Any]:
        raw = re.sub(r"^(批量上架|批量发布|批量发品)[:：]?\s*", "", text).strip()
        if not raw:
            return {"ok": False, "text": "批量格式：每行「标题 | 价格 | 虚拟/实物 | 描述」，例如：\n小学奥数资料 | 9.9 | 虚拟 | 拍下自动发"}
        floor_pct = await self.settings.get_int("floor_discount_pct", 85)
        lines = [line.strip() for line in raw.splitlines() if line.strip() and line.strip() != "---"]
        prepared: list[dict[str, Any]] = []
        for line in lines:
            parts = [p.strip() for p in re.split(r"\s*[|｜]\s*", line)]
            if len(parts) < 2:
                continue
            title = parts[0]
            price = self._parse_price_token(parts[1])
            type_token = parts[2].lower() if len(parts) >= 3 else ""
            virtual = "虚" in type_token or any(h in line for h in VIRTUAL_HINTS)
            if "实物" in type_token:
                virtual = False
            desc = " | ".join(parts[3:]).strip() if len(parts) >= 4 else ""
            if not desc:
                desc = "，".join(parts[2:]).strip() if len(parts) >= 3 else ""
            if not price:
                price = 990 if virtual else 4900
            if not title:
                continue
            title = re.sub(r"\s+", " ", title).strip()[:30]
            policy = (
                "虚拟资料，拍下后自动发网盘链接，链接失效免费补发。"
                if virtual else "实物拍摄，包邮，48 小时内发出；二手物品非质量问题不退换。"
            )
            if policy not in desc:
                desc = f"{desc}\n{policy}" if desc else policy
            prepared.append({
                "title": title, "description": desc[:1000], "price_cents": price,
                "floor_price_cents": max(1, int(round(price * floor_pct / 100))),
                "delivery_mode": "virtual" if virtual else "physical",
                "condition": "电子资料" if virtual else self._extract_condition(line),
                "category": self._category(line, virtual),
            })
        if not prepared:
            return {"ok": False, "text": "没有解析到商品。每行请用 | 分隔：标题 | 价格 | 虚拟/实物 | 描述"}
        if len(prepared) == 1:
            # 只有一条时退回单条上架流程
            return await self._listing("上架：" + raw, toolbox)
        items_payload = []
        preview_items = []
        for data in prepared:
            item_id = await self._create_pending_item(
                title=data["title"], description=data["description"],
                price=data["price_cents"], floor=data["floor_price_cents"],
                virtual=data["delivery_mode"] == "virtual",
                condition=data["condition"], category=data["category"], floor_pct=floor_pct,
            )
            preview = {
                "kind": "publish_batch_item", "item_id": item_id, "title": data["title"],
                "price_cents": data["price_cents"], "price_text": f"¥{yuan(data['price_cents'])}",
                "floor_price_cents": data["floor_price_cents"],
                "delivery_mode": data["delivery_mode"], "condition": data["condition"],
                "category": data["category"], "description": data["description"],
            }
            preview_items.append(preview)
            items_payload.append({"item_id": item_id})
        preview = {"kind": "publish_batch", "items": preview_items, "count": len(preview_items)}
        cfm = await self.confirmations.create(
            "publish_batch", f"批量发布 {len(preview_items)} 件商品", preview,
            {"items": items_payload}, source="seller_agent",
        )
        card = {"type": "confirmation", "confirmation_id": cfm["id"], "preview": preview}
        await toolbox.call(
            "draft_batch_listing", {"count": len(preview_items)},
            lambda: {"count": len(preview_items)},
        )
        text_out = (
            f"批量预览好了：{len(preview_items)} 件商品。\n"
            + "\n".join(f"· {p['title']} {p['price_text']}（{'虚拟' if p['delivery_mode'] == 'virtual' else '实物'}）" for p in preview_items)
            + "\n确认后我会按顺序发布（仍走单写队列），确认前不动平台。"
        )
        return {"ok": True, "text": text_out, "card": card, "count": len(preview_items)}

    @staticmethod
    def _parse_price_token(token: str) -> int | None:
        token = (token or "").replace("¥", "").replace("￥", "").replace("元", "").replace("块", "").strip()
        m = re.search(r"(\d+(?:\.\d{1,2})?)", token)
        if not m:
            return None
        try:
            return int(round(float(m.group(1)) * 100))
        except ValueError:
            return None

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
        query = re.sub(r"(下架|撤下|删除)", " ", text)
        query = re.sub(r"^(把|请|帮我|麻烦|给|将)\s*", "", query.strip())
        query = re.sub(r"(那个|这件|商品|一下|的)", " ", query).strip(" ，,。")
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
        cfm = await self.confirmations.create(
            "offline_item", f"下架商品：{item['title']}", preview, {"item_id": item["id"]},
            source="seller_agent",
        )
        await toolbox.call("offline_item", {"item_id": item["id"]}, lambda: {"preview": True})
        card = {"type": "confirmation", "confirmation_id": cfm["id"], "preview": preview}
        return {
            "ok": True,
            "text": f"要下架「{item['title']}」（¥{yuan(item['price_cents'])}）吗？确认后我会下架并同步知识库墓碑。",
            "card": card,
        }

    async def _relist(self, text: str, toolbox: ToolBox) -> dict[str, Any]:
        query = re.sub(r"(重新上架|重新发布|再上架|续售|恢复上架|重新挂)", " ", text)
        query = re.sub(r"^(把|请|帮我|麻烦|给|将)\s*", "", query.strip())
        query = re.sub(r"(那个|这件|商品|一下|的)", " ", query).strip(" ，,。")
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
        cfm = await self.confirmations.create(
            "relist_item", f"重新上架：{item['title']}", preview, {"item_id": item["id"]},
            source="seller_agent",
        )
        await toolbox.call("relist_item", {"item_id": item["id"]}, lambda: {"preview": True})
        card = {"type": "confirmation", "confirmation_id": cfm["id"], "preview": preview}
        return {
            "ok": True,
            "text": (
                f"要重新上架「{item['title']}」（¥{yuan(item['price_cents'])}）吗？\n"
                "确认后会按保存的发布参数重新发布一条新商品；旧的已下架商品仍保留在闲鱼后台。"
            ),
            "card": card,
        }

    async def _change_price(self, text: str, toolbox: ToolBox) -> dict[str, Any]:
        price, _ = self._extract_price(text)
        if not price:
            return {"ok": False, "text": "改价要带新价格，例如：改价 Kindle 到 199 元。"}
        query = re.sub(r"(改价|改价格|调价|价格改)", " ", text)
        query = re.sub(r"(到|改成|改为|至)\s*\d+(?:\.\d{1,2})?\s*(?:元|块)?", " ", query)
        query = re.sub(r"\d+(?:\.\d{1,2})?\s*(?:元|块)?", " ", query)
        query = re.sub(r"^(把|请|帮我|麻烦|给|将)\s*", "", query.strip())
        query = re.sub(r"(那个|这件|商品|一下|的|到|改成|改为)", " ", query).strip(" ，,。")
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
        cfm = await self.confirmations.create(
            "change_price", f"改价：{item['title']}", preview,
            {"item_id": item["id"], "price_cents": price}, source="seller_agent",
        )
        await toolbox.call("change_price", {"item_id": item["id"], "price": price}, lambda: {"preview": True})
        card = {"type": "confirmation", "confirmation_id": cfm["id"], "preview": preview}
        return {
            "ok": True,
            "text": f"把「{item['title']}」从 ¥{yuan(item['price_cents'])} 改到 ¥{yuan(price)}？确认后执行。",
            "card": card,
        }

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

    # ---------------- 工具 ----------------

    async def _find_items(self, query: str) -> list[dict[str, Any]]:
        query = re.sub(r"(那个|这件|商品|一下|麻烦|帮我|请|的)", "", query or "").strip()
        rows = await self.db.fetchall(
            "SELECT * FROM items WHERE status IN ('live','sold_out','pending_confirm','offline') ORDER BY updated_at DESC"
        )
        if not query:
            return []
        q = query.lower()
        tokens = [t for t in re.split(r"[\s，,。]+", q) if len(t) >= 2]
        scored: list[tuple[int, dict]] = []
        for row in rows:
            title = row["title"].lower()
            score = 0
            if q == title:
                score = 100
            elif q in title:
                score = 70 + len(q)
            elif title in q:
                score = 60 + len(title)
            else:
                for token in tokens:
                    if token in title:
                        score += 20 + len(token)
            if score:
                scored.append((score, dict(row)))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return []
        top = scored[0][0]
        return [row for score, row in scored if top - score < 15][:5]

    @staticmethod
    def _extract_price(text: str) -> tuple[int | None, str]:
        patterns = [
            r"(?:改价|改价格|调价|价格改)\s*(?:到|为|成|至)?\s*(\d+(?:\.\d{1,2})?)\s*(?:元|块)?",
            r"(?:价格|卖|售价|¥|￥)\s*(\d+(?:\.\d{1,2})?)\s*(?:元|块)?",
            r"(\d+(?:\.\d{1,2})?)\s*(?:元|块)",
            r"(?:到|改成|改为)\s*(\d+(?:\.\d{1,2})?)\s*(?:元|块)?",
        ]
        match = None
        for pat in patterns:
            matches = list(re.finditer(pat, text))
            if matches:
                match = matches[-1]
                break
        if not match:
            return None, text
        try:
            cents = int(round(float(match.group(1)) * 100))
        except ValueError:
            return None, text
        cleaned = text[: match.start()] + " " + text[match.end():]
        cleaned = re.sub(r"(价格|卖|售价)[:：]?\s*$", "", cleaned).strip()
        return cents, cleaned

    @staticmethod
    def _extract_condition(text: str) -> str:
        m = re.search(r"(全新|99新|98新|95新|9成新|8成新|7成新)", text)
        return m.group(1) if m else "自用闲置"

    @staticmethod
    def _fallback_title(text: str, virtual: bool) -> str:
        """描述里只有类型/价格时，从后半句提取一个可用的短标题。"""
        cleaned = re.sub(r"\d+(?:\.\d{1,2})?\s*(?:元|块)?", " ", text or "")
        parts = [p.strip(" -—:：，,。；;") for p in re.split(r"[，,。；;\n]", cleaned)]
        blocked = {"虚拟资料", "虚拟商品", "电子资料", "实物商品", "拍下自动发", "拍下后自动发", "包邮", "全新", "二手"}
        for part in parts:
            part = re.sub(r"^(虚拟资料|虚拟商品|电子资料|实物商品|商品|标题)[:：]?\s*", "", part).strip()
            if len(part) >= 4 and part not in blocked and not re.fullmatch(r"[虚拟实物资料商品自动发货包邮全新二手\s]+", part):
                return part[:30]
        return "闲置好物" if not virtual else "虚拟资料"

    @staticmethod
    def _category(text: str, virtual: bool) -> str:
        if virtual:
            if re.search(r"考研|英语|数学|小学|初中|高中|学习|真题|题库|课程", text):
                return "教育培训 > 学习资料"
            return "虚拟资源 > 数字素材"
        if re.search(r"手机|iPad|ipad|相机|耳机|Kindle|kindle|数码|电脑", text):
            return "数码 > 闲置数码"
        if re.search(r"挂件|玩偶|手办|潮玩", text):
            return "潮玩 > 毛绒挂件"
        return "闲置 > 其他"

    async def _llm_listing(self, title: str, desc: str, price: int, delivery: str) -> dict[str, str] | None:
        prompt = (
            "把下面的闲置商品信息润色成闲鱼文案。只输出 JSON："
            '{"title":"30字内标题","description":"80-220字描述"}。'
            "标题禁止感叹号堆砌，描述要真实、具体、亲切，不能出现微信/QQ/外链/网盘链接，不能编造参数。\n"
            f"原标题：{title}\n原描述：{desc}\n价格：{yuan(price)} 元\n类型：{'虚拟' if delivery == 'virtual' else '实物'}"
        )
        raw = await self.llm.chat(
            [{"role": "user", "content": prompt}], purpose="seller_listing", temperature=0.7,
            max_tokens=500, json_mode=True,
        )
        if not raw:
            return None
        try:
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            t = str(data.get("title") or "")[:30].strip()
            d = str(data.get("description") or "").strip()
            if not t or len(d) < 20 or re.search(r"微信|qq|http|https|转账", d, re.I):
                return None
            return {"title": t, "description": d[:800]}
        except Exception:
            return None

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

    async def _reply(self, text: str, *, card: dict[str, Any] | None = None) -> dict[str, Any]:
        seller = await self.messaging.seller_conversation()
        meta = {"card": card} if card else {}
        return await self.messaging.add_local_message(
            seller["id"], text, role="agent", meta=meta
        )
