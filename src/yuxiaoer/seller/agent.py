"""卖家 Agent（单例）：店主对话指令 → 意图解析 → 预览/确认 → 原生执行。

资金/上架类动作全部两段式：先返回预览卡，店主回"确认"或点按钮后才执行。
本类只保留装配、入口路由与回复；具体指令/上架/确认逻辑在 commands/ 的 mixin 中。
"""

from __future__ import annotations

import re
from typing import Any

from yuxiaoer.shared.toolbox import ToolBox
from yuxiaoer.shared.knowledge import KnowledgeService
from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.core.llm import LLMClient
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.util import new_id
from yuxiaoer.seller.commerce.orders import OrderService
from yuxiaoer.seller.confirmations import ConfirmationService
from yuxiaoer.seller.conversation.messaging import MessagingService
from yuxiaoer.seller.notifications.alerts import AlertService
from yuxiaoer.seller.platform.channels import BaseChannel
from yuxiaoer.seller.write_queue import WriteQueue

from .commands.actions import CommandActionsMixin
from .commands.confirm import ConfirmMixin
from .commands.listing import ListingMixin
from .commands.parsing import ParsingMixin
from .constants import CANCEL_WORDS, YES_WORDS


class SellerAgent(ConfirmMixin, ListingMixin, CommandActionsMixin, ParsingMixin):
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

    async def _reply(self, text: str, *, card: dict[str, Any] | None = None) -> dict[str, Any]:
        seller = await self.messaging.seller_conversation()
        meta = {"card": card} if card else {}
        return await self.messaging.add_local_message(
            seller["id"], text, role="agent", meta=meta
        )
