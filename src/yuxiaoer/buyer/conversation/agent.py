"""买家会话 Agent：上下文组装 → 意图分支 → 工具 → 回复/转人工。

每买家会话一个实例（由 IngestService 保证串行），工具白名单窄：
get_item_info / get_order_status / create_refund_request / escalate_human。
无发布、改价、发货权限。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from yuxiaoer.core import config
from yuxiaoer.buyer.conversation.bargain import decide as bargain_decide
from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.buyer.conversation.gateway import Decision, classify
from yuxiaoer.shared.knowledge import KnowledgeService
from yuxiaoer.shared.ports import AlertPort, MessagingPort
from yuxiaoer.shared.toolbox import ToolBox
from yuxiaoer.core.llm import LLMClient
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.state import transition_order
from yuxiaoer.core.util import dumps, human_time, iso, loads, new_id, now_utc, parse_iso, snippet, yuan

log = logging.getLogger("yuxiaoer.buyer")


@dataclass
class BuyerReply:
    text: str = ""
    action: str = "reply"
    handoff: bool = False
    handoff_reason: str = ""
    notes: list[str] = field(default_factory=list)
    steps: int = 0



class BuyerAgent:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        knowledge: KnowledgeService,
        messaging: MessagingPort,
        alerts: AlertPort,
        settings: SettingsService,
        llm: LLMClient,
        confirmations: Any,
    ):
        self.db = db
        self.bus = bus
        self.knowledge = knowledge
        self.messaging = messaging
        self.alerts = alerts
        self.settings = settings
        self.llm = llm
        self.confirmations = confirmations
        self._locks: dict[str, asyncio.Lock] = {}

    # ---------------- 入口 ----------------

    async def handle_pending(self, conversation_id: str) -> dict[str, Any] | None:
        lock = self._locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            return await self._handle_locked(conversation_id)

    async def _handle_locked(self, conversation_id: str) -> dict[str, Any] | None:
        conv = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        if not conv:
            return None
        conv = dict(conv)
        pending = await self.messaging.pending_inbound(conversation_id)
        if not pending:
            return None

        # 人工接管中：不自动回复，但仍标记已处理，避免积压
        if conv.get("handoff"):
            until = conv.get("handoff_until")
            if until and parse_iso(until) > now_utc():
                await self.messaging.mark_processed([m["id"] for m in pending])
                await self.messaging.mark_owner_unread(conversation_id)
                return {"skipped": "handoff"}
            await self.messaging.resume(conversation_id)

        text = "\n".join(m["text"] for m in pending).strip()[:2000]
        first_at = pending[0]["created_at"]
        turn_id = new_id("turn")
        session_id = conv["session_id"]
        started = iso()
        await self.db.execute(
            "INSERT INTO turns(id,conversation_id,session_id,status,started_at) VALUES(?,?,?,?,?)",
            (turn_id, conversation_id, session_id, "processing", started),
        )
        toolbox = ToolBox(
            self.db, turn_id=turn_id, session_id=session_id, agent="buyer",
            limit=config.BUYER_MAX_STEPS,
        )
        decision = classify(text, item_title=None)
        item = await self._item(conv.get("item_id"))
        buyer = await self.db.fetchone("SELECT * FROM buyers WHERE id=?", (conv["buyer_id"],))
        buyer = dict(buyer) if buyer else {"id": conv["buyer_id"], "nick": "买家"}

        # 规则不确定时，可选 LLM 兜底分类（不影响主链路）
        if decision.category == "unknown" and self.llm.available():
            decision = await self._llm_classify(text, decision)

        try:
            already_sent = False
            if decision.action == "silent":
                result = await self._handle_silent(conv, buyer, item, text, decision)
            elif decision.action == "template":
                reply = decision.template or "在的，有需要随时问我～"
                sent = await self.messaging.send_reply(conv, reply, turn_id=turn_id,
                                                       meta={"gateway": decision.category})
                already_sent = True
                result = BuyerReply(
                    text=reply, action="scheduled" if sent.get("scheduled") else "template",
                    steps=0, notes=[sent.get("reason")] if sent.get("reason") else [],
                )
            elif decision.cautious or decision.category == "unknown":
                result = await self._handle_cautious(conv, buyer, item, text, decision, toolbox)
            elif decision.category == "human":
                result = await self._handle_human_request(conv, buyer, item, text, decision, toolbox)
            elif decision.category == "after_sale":
                result = await self._after_sale(conv, buyer, item, text, decision, toolbox)
            elif decision.category == "bargain":
                result = await self._bargain(conv, buyer, item, text, decision, toolbox)
            elif decision.category == "order":
                result = await self._order(conv, buyer, item, text, decision, toolbox)
            else:
                result = await self._pre_sale(conv, buyer, item, text, decision, toolbox)

            if toolbox.repeat and not result.handoff:
                await self._escalate(conv, buyer, item, text, "同一工具重复调用，熔断转人工")
                result.handoff = True
                result.handoff_reason = "同一工具重复调用"
                result.text = result.text or "这个我让店主来看一下，稍等～"

            if toolbox.steps > config.BUYER_MAX_STEPS and not result.handoff:
                await self._escalate(conv, buyer, item, text, "工具步数超限")
                result.handoff = True
                result.handoff_reason = "工具步数超限"
                result.text = result.text or "这个我让店主来处理，稍等～"

            if result.text and not already_sent:
                sent = await self.messaging.send_reply(
                    conv, result.text, turn_id=turn_id,
                    meta={"gateway": decision.category, "handoff": result.handoff},
                )
                if sent.get("scheduled"):
                    result.action = "scheduled"
                    result.notes.append(sent.get("reason") or "已排期")

            await self.messaging.mark_processed([m["id"] for m in pending])
            latency_ms = int((now_utc() - parse_iso(first_at)).total_seconds() * 1000)
            await self._finish_turn(
                turn_id, decision, result, latency_ms, steps=toolbox.steps,
                status="done", reply=result.text, handoff=result.handoff,
            )
            return {
                "turn_id": turn_id, "decision": decision.to_dict(), "reply": result.text,
                "handoff": result.handoff, "steps": toolbox.steps,
                "scheduled": result.action == "scheduled", "notes": result.notes,
            }
        except Exception as exc:  # noqa: BLE001
            log.exception("buyer agent failed")
            await self.alerts.create(
                "P1", "agent_error", "买家 Agent 处理失败",
                f"会话 {conversation_id} 处理异常：{str(exc)[:200]}",
                conversation_id=conversation_id, dedupe_minutes=10,
            )
            fallback = "稍等，我让店主来看一下这条消息～"
            sent = await self.messaging.send_reply(conv, fallback, turn_id=turn_id)
            await self.messaging.mark_processed([m["id"] for m in pending])
            await self._finish_turn(
                turn_id, decision, BuyerReply(text=fallback, action="fallback", handoff=True),
                0, steps=toolbox.steps, status="failed", reply=fallback, handoff=True,
                error=str(exc),
            )
            return {"turn_id": turn_id, "decision": decision.to_dict(), "reply": fallback,
                    "handoff": True, "error": str(exc), "scheduled": sent.get("scheduled", False)}

    # ---------------- 分支 ----------------

    async def _pre_sale(
        self, conv: dict, buyer: dict, item: dict | None, text: str, decision: Decision, tools: ToolBox
    ) -> BuyerReply:
        if not item:
            await self._escalate(conv, buyer, None, text, "找不到商品上下文")
            return BuyerReply(text="这个商品的信息我这边没查到，我让店主来回复你～", handoff=True,
                              handoff_reason="商品缺失")
        await tools.call("get_item_info", {"item_id": item["id"]}, lambda: self._get_item_info(item["id"]))
        hits = await tools.call(
            "kb_search", {"query": text, "namespace": "buyer", "k": 3},
            lambda: self.knowledge.search(text, namespace="buyer", k=3, types=["faq"]),
        )
        faq_hits = (hits.get("data") or []) if hits.get("ok") else []
        faq_answer = self._faq_answer(faq_hits[0]) if faq_hits else None

        reply = None
        if self.llm.available():
            reply = await self._llm_compose(item, text, faq_hits)
        if not reply:
            if faq_answer:
                reply = faq_answer
                if len(reply) < 45 and item.get("delivery_mode") == "virtual":
                    reply += " 拍下后自动发网盘链接，不用等～"
            else:
                reply = self._fallback_pre_sale(item)
        return BuyerReply(text=reply, steps=tools.steps, notes=[f"FAQ命中{len(faq_hits)}条"])

    async def _bargain(
        self, conv: dict, buyer: dict, item: dict | None, text: str, decision: Decision, tools: ToolBox
    ) -> BuyerReply:
        if not item:
            return BuyerReply(text="这件商品我确认下再回你～", handoff=True, handoff_reason="商品缺失")
        await tools.call("get_item_info", {"item_id": item["id"]}, lambda: self._get_item_info(item["id"]))
        round_no = int(conv.get("bargain_round") or 0)
        max_rounds = await self.settings.get_int("bargain_max_rounds", 3)
        result = bargain_decide(item, text, round_no, max_rounds)
        await self.db.execute(
            "UPDATE conversations SET bargain_round=bargain_round+1,updated_at=? WHERE id=?",
            (iso(), conv["id"]),
        )
        notes = [f"议价 {result.kind}，目标 {yuan(result.target_cents)}"]
        # 原生协议尚未实现改价；只把买家出价转告店主，不生成假改价确认
        if result.kind == "accept" and result.target_cents < int(item["price_cents"]):
            await self.alerts.create(
                "P2", "bargain", "议价待店主处理",
                f"买家「{buyer.get('nick')}」对「{item['title']}」出价 ¥{yuan(result.target_cents)}，"
                f"标价 ¥{yuan(item['price_cents'])}。请到闲鱼手动改价。",
                conversation_id=conv["id"], dedupe_minutes=5,
            )
            reply = (
                f"{yuan(result.target_cents)} 元我记下了～ 需要店主到闲鱼改价，"
                "改好后再拍下就可以。"
            )
            notes.append("原生改价未实现，已转告店主")
        else:
            reply = result.message
        return BuyerReply(text=reply, steps=tools.steps, notes=notes)

    async def _after_sale(
        self, conv: dict, buyer: dict, item: dict | None, text: str, decision: Decision, tools: ToolBox
    ) -> BuyerReply:
        order_res = await tools.call(
            "get_order_status", {"buyer_id": conv["buyer_id"], "item_id": conv.get("item_id")},
            lambda: self._get_order_status(conv["buyer_id"], conv.get("item_id")),
        )
        order = (order_res.get("data") or {}).get("order") if order_res.get("ok") else None
        low = text.lower()

        # 退款/退货
        if re.search(r"退款|退货|退换|退钱|不想要", low):
            if not order:
                return BuyerReply(
                    text="可以退款～ 不过我先确认下订单，你把订单号发我一下，或者告诉我拍的是哪件？",
                    steps=tools.steps,
                )
            if order["status"] == "refund_open":
                return BuyerReply(text="这笔订单已经在退款处理中啦，店主会尽快处理，稍等～", steps=tools.steps)
            if order["status"] in ("done", "refund_resolved"):
                await self._escalate(conv, buyer, item, text, "已完成订单申请退款")
                return BuyerReply(text="这笔订单已经完成了，我让店主来跟你确认售后方案～", handoff=True,
                                  handoff_reason="已完成订单售后", steps=tools.steps)
            transitioned = await transition_order(
                self.db, self.bus, order["id"], ["paid", "shipped", "delivered"], "refund_open",
                fields={"refund_reason": snippet(text, 120)}, actor="buyer_agent", reason="买家申请退款",
            )
            await tools.call(
                "create_refund_request", {"order_id": order["id"], "reason": snippet(text, 120)},
                lambda: {"order_id": order["id"], "transitioned": transitioned},
            )
            if transitioned:
                await self.alerts.create(
                    "P1", "refund_request", f"退款申请：{item['title'] if item else order['item_id']}",
                    f"买家「{buyer.get('nick')}」申请退款：{snippet(text, 120)}。请到订单页处理。",
                    conversation_id=conv["id"], order_id=order["id"], dedupe_minutes=5,
                )
                return BuyerReply(
                    text="已经帮你登记退款申请啦，店主会尽快处理；有进度我第一时间告诉你。",
                    steps=tools.steps,
                )
            return BuyerReply(text="订单状态刚刚有变化，我确认一下再回你～", steps=tools.steps)

        # 链接失效
        if re.search(r"失效|打不开|提取码|链接没|链接错", low):
            await self._escalate(conv, buyer, item, text, "链接失效待补发")
            return BuyerReply(
                text="链接失效可以免费补发～ 我让店主马上给你换一条新链接，稍等一下。",
                handoff=True, handoff_reason="链接失效补发", steps=tools.steps,
            )

        # 损坏/少发/换货（放在物流之前，"少了一章"这类消息不能被"收到"误吞）
        if re.search(r"坏了|破损|瑕疵|少发|漏发|少了一|发错|不对|换货|怎么办", low):
            await self._escalate(conv, buyer, item, text, "售后问题转人工")
            return BuyerReply(
                text="抱歉给你添麻烦了，这个我让店主来处理，可以补发或退换，稍等一下～",
                handoff=True, handoff_reason="售后问题", steps=tools.steps,
            )

        # 改地址
        if re.search(r"地址|改收货", low):
            await self._escalate(conv, buyer, item, text, "修改地址")
            return BuyerReply(
                text="地址修改需要店主确认一下，我马上转给店主，稍等～",
                handoff=True, handoff_reason="修改地址", steps=tools.steps,
            )

        # 确认收货
        if re.search(r"确认收货", low):
            return BuyerReply(
                text="在闲鱼订单详情里点「确认收货」就可以啦；收到有问题随时找我～", steps=tools.steps
            )

        # 物流/发货
        if re.search(r"快递|物流|到哪|单号|签收|收货|收到|发货|还没发|催|多久到", low):
            if not order:
                return BuyerReply(
                    text="你是哪件商品的订单呀？把订单号发我，我马上帮你查发货和快递物流～",
                    steps=tools.steps,
                )
            if order["status"] == "paid":
                await self.alerts.create(
                    "P2", "ship_reminder", "买家催发货",
                    f"买家「{buyer.get('nick')}」在催发货：{snippet(text, 80)}",
                    conversation_id=conv["id"], order_id=order["id"], dedupe_minutes=30,
                )
                if order.get("tracking_no"):
                    return BuyerReply(
                        text=f"已经发货啦，{order.get('tracking_company') or '快递'}单号 {order['tracking_no']}，"
                             "预计 2-3 天到～", steps=tools.steps,
                    )
                return BuyerReply(
                    text="订单已经付款啦，还没发货，我帮你催一下店主，今天就安排～", steps=tools.steps
                )
            if order["status"] in ("shipped", "delivered", "done"):
                company = order.get("tracking_company") or "快递"
                no = order.get("tracking_no") or "（单号稍后发）"
                tail = "显示已签收" if order["status"] in ("delivered", "done") else "预计 2-3 天到"
                return BuyerReply(text=f"已经由{company}发出，单号 {no}，{tail}～", steps=tools.steps)
            if order["status"] == "refund_open":
                return BuyerReply(text="这笔订单正在退款处理中，物流会暂停，店主会尽快跟进～", steps=tools.steps)

        await self._escalate(conv, buyer, item, text, "售后意图不确定")
        return BuyerReply(
            text="这个我让店主来跟你确认一下，稍等～", handoff=True, handoff_reason="售后意图不确定",
            steps=tools.steps,
        )

    async def _order(
        self, conv: dict, buyer: dict, item: dict | None, text: str, decision: Decision, tools: ToolBox
    ) -> BuyerReply:
        order_res = await tools.call(
            "get_order_status", {"buyer_id": conv["buyer_id"], "item_id": conv.get("item_id")},
            lambda: self._get_order_status(conv["buyer_id"], conv.get("item_id")),
        )
        order = (order_res.get("data") or {}).get("order") if order_res.get("ok") else None
        if not order:
            return BuyerReply(
                text="我这边没查到这个商品的订单～ 把订单号发我，我帮你查一下。", steps=tools.steps
            )
        labels = {
            "paid": "已付款，等待发货", "shipped": "已发货", "delivered": "已送达",
            "done": "已完成", "refund_open": "退款处理中", "refund_resolved": "退款已处理",
            "cancelled": "已取消",
        }
        status_text = labels.get(order["status"], order["status"])
        detail = []
        if order.get("tracking_no"):
            detail.append(f"{order.get('tracking_company') or '快递'} {order['tracking_no']}")
        if order.get("amount_cents"):
            detail.append(f"金额 ¥{yuan(order['amount_cents'])}")
        tail = "；".join(detail)
        return BuyerReply(
            text=f"查到你的订单啦：{status_text}" + (f"（{tail}）" if tail else "") + "。还有什么需要我帮忙的吗？",
            steps=tools.steps,
        )

    async def _handle_cautious(
        self, conv: dict, buyer: dict, item: dict | None, text: str, decision: Decision, tools: ToolBox
    ) -> BuyerReply:
        hits_res = await tools.call(
            "kb_search", {"query": text, "namespace": "buyer", "k": 3},
            lambda: self.knowledge.search(text, namespace="buyer", k=3, types=["faq"]),
        )
        hits = (hits_res.get("data") or []) if hits_res.get("ok") else []
        if hits:
            return BuyerReply(text=self._faq_answer(hits[0]), steps=tools.steps)
        # 低置信问题只提醒店主，不进入 30 分钟人工接管：
        # 否则买家下一句“那你会干什么”也会被静默，表现为 AI 突然没反应。
        await self.alerts.create(
            "P2", "low_confidence", f"低置信问题：{buyer.get('nick') or '买家'}",
            f"买家消息：{snippet(text, 160)}\n建议店主补一条知识库，AI 已先回复兜底话术。",
            conversation_id=conv["id"], dedupe_minutes=10,
        )
        return BuyerReply(
            text="这个我不太确定，怕给你说错，我让店主来回复你～",
            handoff=False, handoff_reason="低置信问题", steps=tools.steps,
        )

    async def _handle_human_request(
        self, conv: dict, buyer: dict, item: dict | None, text: str, decision: Decision, tools: ToolBox
    ) -> BuyerReply:
        await self._escalate(conv, buyer, item, text, "买家主动要求人工")
        return BuyerReply(
            text="好的～ 我请店主来跟你聊，稍等一下。",
            handoff=True, handoff_reason="买家要求人工", steps=tools.steps,
        )

    async def _handle_silent(
        self, conv: dict, buyer: dict, item: dict | None, text: str, decision: Decision
    ) -> BuyerReply:
        kind = "risk_message" if decision.category == "risk" else "off_platform_attempt"
        title = "风险消息拦截" if decision.category == "risk" else "站外沟通拦截"
        await self.alerts.create(
            "P1", kind, f"{title}：{buyer.get('nick')}",
            f"买家消息：{snippet(text, 160)}\n命中规则：{decision.reason}\n已静默不回复。",
            conversation_id=conv["id"], dedupe_minutes=10,
        )
        await self.messaging.set_handoff(conv["id"], decision.reason, minutes=30)
        return BuyerReply(text="", action="silent", handoff=True, handoff_reason=decision.reason)

    # ---------------- 工具实现 ----------------

    async def _item(self, item_id: str | None) -> dict | None:
        if not item_id:
            return None
        row = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        return dict(row) if row else None

    async def _get_item_info(self, item_id: str) -> dict[str, Any]:
        item = await self._item(item_id)
        if not item:
            raise LookupError("item not found")
        return {
            "id": item["id"],
            "title": item["title"],
            "price_cents": item["price_cents"],
            "price_text": f"¥{yuan(item['price_cents'])}",
            "condition": item["condition"],
            "delivery_mode": item["delivery_mode"],
            "delivery_text": "虚拟商品，拍下自动发卡券/网盘链接" if item["delivery_mode"] == "virtual"
            else "实物，48 小时内发货，默认包邮",
            "stock": item["stock"],
            "status": item["status"],
            "description": snippet(item["description"], 300),
        }

    async def _get_order_status(self, buyer_id: str, item_id: str | None) -> dict[str, Any]:
        if item_id:
            row = await self.db.fetchone(
                "SELECT * FROM orders WHERE buyer_id=? AND item_id=? ORDER BY created_at DESC LIMIT 1",
                (buyer_id, item_id),
            )
        else:
            row = await self.db.fetchone(
                "SELECT * FROM orders WHERE buyer_id=? ORDER BY created_at DESC LIMIT 1",
                (buyer_id,),
            )
        if not row:
            return {"order": None}
        order = dict(row)
        return {
            "order": {
                "id": order["id"],
                "platform_order_id": order.get("platform_order_id"),
                "status": order["status"],
                "amount_cents": order["amount_cents"],
                "tracking_company": order.get("tracking_company"),
                "tracking_no": order.get("tracking_no"),
                "created_at": order["created_at"],
                "item_id": order["item_id"],
            }
        }

    # ---------------- 回复组装 ----------------

    @staticmethod
    def _faq_answer(hit: dict[str, Any]) -> str:
        text = hit.get("text") or ""
        if "答：" in text:
            answer = text.split("答：", 1)[1].strip()
            return re.sub(r"\s+", " ", answer)
        return snippet(text, 160)

    @staticmethod
    def _fallback_pre_sale(item: dict[str, Any]) -> str:
        condition = item.get("condition") or "成色不错"
        if item.get("delivery_mode") == "virtual" and "新" not in condition:
            condition = f"{condition}（非全新实体）"
        if item.get("delivery_mode") == "virtual":
            delivery = "拍下后自动发网盘链接，不用等"
        else:
            delivery = "实物包邮，48 小时内发出"
        return (
            f"在的，这件「{item['title']}」还有的～ 现在 ¥{yuan(item['price_cents'])}，"
            f"{condition}，{delivery}。还有想了解的可以直接问我。"
        )

    async def _llm_compose(self, item: dict, text: str, faq_hits: list[dict]) -> str | None:
        faq_text = "\n".join(self._faq_answer(h) for h in faq_hits[:2])
        facts = (
            f"商品：{item['title']}\n价格：{yuan(item['price_cents'])} 元\n"
            f"成色：{item['condition']}\n"
            f"发货：{'虚拟商品，拍下自动发网盘链接' if item['delivery_mode'] == 'virtual' else '实物，48 小时内发货，默认包邮'}\n"
            f"描述：{item['description']}\nFAQ：{faq_text or '无'}"
        )
        prompt = (
            "你是闲鱼店主小满的客服。只允许使用下面的<事实>回答，不得编造价格、库存、时效；"
            "不透露底价；不提微信/QQ/站外转账；不出现链接；60 字以内；亲切、自然；"
            "不要自称 AI 或机器人。直接输出回复文本。\n\n<事实>\n" + facts + "\n</事实>\n\n买家："
            + text + "\n客服："
        )
        reply = await self.llm.chat(
            [{"role": "user", "content": prompt}], purpose="buyer_reply", temperature=0.6, max_tokens=220
        )
        if not reply:
            return None
        return reply if self._validate_reply(reply, item) else None

    def _validate_reply(self, reply: str, item: dict) -> bool:
        reply = reply.strip()
        if not reply or len(reply) > 160:
            return False
        if re.search(r"微信|vx|qq|支付宝|私下|转账|二维码|链接：|https?://", reply, re.I):
            return False
        prices = re.findall(r"(\d+(?:\.\d{1,2})?)\s*元", reply)
        for p in prices:
            if abs(float(p) * 100 - int(item["price_cents"])) > 1:
                return False
        return True

    async def _llm_classify(self, text: str, fallback: Decision) -> Decision:
        prompt = (
            "把买家的闲鱼咨询分类为以下之一：pre_sale（售前咨询）、bargain（议价）、"
            "after_sale（售后/物流/退款）、order（订单查询）、chitchat（纯寒暄）、risk（辱骂/威胁/诈骗）、"
            "off_platform（要求加微信/站外交易）。只输出 JSON："
            '{"category":"pre_sale","confidence":0.8}'
        )
        raw = await self.llm.chat(
            [{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            purpose="gateway_classify", temperature=0.1, max_tokens=80, json_mode=True,
        )
        if not raw:
            return fallback
        try:
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            cat = data.get("category")
            conf = float(data.get("confidence", 0))
            if cat in {"pre_sale", "bargain", "after_sale", "order", "chitchat", "risk", "off_platform"} and conf >= 0.6:
                action = {"risk": "silent", "off_platform": "silent", "chitchat": "template"}.get(cat, "agent")
                return Decision(cat, action, conf, f"LLM 分类（{conf:.2f}）", cautious=cat == "unknown")
        except Exception:
            pass
        return fallback

    # ---------------- 转人工/确认卡 ----------------

    async def _escalate(
        self, conv: dict, buyer: dict, item: dict | None, text: str, reason: str
    ) -> None:
        await self.messaging.set_handoff(conv["id"], reason, minutes=30)
        await self.alerts.create(
            "P1", "handoff", f"转人工：{buyer.get('nick')}",
            f"原因：{reason}\n商品：{item['title'] if item else '-'}\n买家消息：{snippet(text, 160)}",
            conversation_id=conv["id"], dedupe_minutes=10,
        )

    async def _finish_turn(
        self, turn_id: str, decision: Decision, result: BuyerReply, latency_ms: int, *,
        steps: int, status: str, reply: str, handoff: bool, error: str | None = None,
    ) -> None:
        await self.db.execute(
            """UPDATE turns SET status=?,gateway_json=?,intent=?,action=?,reply_text=?,handoff=?,
               latency_ms=?,steps=?,finished_at=?,error=? WHERE id=?""",
            (
                status, dumps(decision.to_dict()), decision.category, result.action, reply,
                1 if handoff else 0, latency_ms, steps, iso(), error, turn_id,
            ),
        )

    # ---------------- 评测用干跑（无副作用） ----------------

    async def dry_reply(self, text: str, item_id: str | None) -> dict[str, Any]:
        item = await self._item(item_id)
        decision = classify(text, item_title=item["title"] if item else None)
        if decision.action == "silent":
            return {"category": decision.category, "action": "silent", "reply": "", "handoff": False}
        if decision.action == "template":
            return {"category": decision.category, "action": "template",
                    "reply": decision.template or "", "handoff": False}
        if not item:
            return {"category": decision.category, "action": decision.action,
                    "reply": "这个我让店主来回复你～", "handoff": True}
        if decision.category == "after_sale":
            reply = self._dry_after_sale(text)
        elif decision.category == "bargain":
            reply = bargain_decide(item, text, 0, 3).message
        elif decision.category == "order":
            reply = "我已经看到你的付款啦，我帮你查下订单状态～"
        elif decision.category == "pre_sale":
            hits = await self.knowledge.search(text, namespace="buyer", k=1, types=["faq"])
            reply = self._faq_answer(hits[0]) if hits else self._fallback_pre_sale(item)
        else:
            hits = await self.knowledge.search(text, namespace="buyer", k=1, types=["faq"])
            reply = self._faq_answer(hits[0]) if hits else "这个我帮您问下店主～"
        return {"category": decision.category, "action": decision.action,
                "reply": reply, "handoff": False}

    @staticmethod
    def _dry_after_sale(text: str) -> str:
        low = text.lower()
        if re.search(r"失效|打不开|提取码|链接", low):
            return "链接失效可以免费补发，我让店主马上发你一条新链接～"
        if re.search(r"退款|退货|退换|退钱", low):
            return "可以退的～ 我帮你登记退款申请，店主会尽快处理。"
        if re.search(r"坏了|破损|瑕疵|少发|漏发|少了一|发错|不对|换货", low):
            return "抱歉添麻烦了，我让店主来处理补发或退换～"
        if re.search(r"改地址|地址", low):
            return "地址修改需要店主确认，我马上转给店主～"
        if re.search(r"确认收货", low):
            return "在订单详情里点确认收货就可以啦～"
        if re.search(r"快递|物流|到哪|单号|签收|收货|收到|发货|还没发|没发|催|多久到", low):
            return "我帮你查一下这笔订单的快递物流，发货后会把单号发你～"
        return "这个我让店主来跟你确认一下～"
