"""指标金字塔：L0 健康 / L1 质量 / L2 成果（北极星=询单转化率）。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from yuxiaoer.core import config
from yuxiaoer.core.db import Database
from yuxiaoer.core.util import iso, local_date, now_utc, percentile, start_of_local_day


class MetricsService:
    def __init__(self, db: Database):
        self.db = db

    async def today(self) -> dict[str, Any]:
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
        answered = await self.db.fetchval(
            """SELECT COUNT(DISTINCT c.id) FROM conversations c
               WHERE c.created_at>=? AND c.id!='conv_seller' AND EXISTS(
                 SELECT 1 FROM messages m WHERE m.conversation_id=c.id AND m.direction='out' AND m.role='agent')""",
            (since,), 0,
        )
        handoff = await self.db.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE handoff=1 AND updated_at>=?", (since,), 0
        )
        unpaid = await self.db.fetchval(
            """SELECT COUNT(*) FROM conversations c WHERE c.created_at>=? AND c.id!='conv_seller'
               AND EXISTS(SELECT 1 FROM messages m WHERE m.conversation_id=c.id AND m.direction='in' AND m.role='buyer')
               AND NOT EXISTS(SELECT 1 FROM messages m WHERE m.conversation_id=c.id AND m.direction='out' AND m.role='agent')""",
            (since,), 0,
        )
        latencies = [
            float(r["latency_ms"])
            for r in await self.db.fetchall(
                "SELECT latency_ms FROM turns WHERE started_at>=? AND latency_ms IS NOT NULL AND status='done'",
                (since,),
            )
        ]
        turns = await self.db.fetchval("SELECT COUNT(*) FROM turns WHERE started_at>=?", (since,), 0)
        blocked = await self.db.fetchval(
            "SELECT COUNT(*) FROM turns WHERE started_at>=? AND intent IN ('risk','off_platform')", (since,), 0
        )
        paid_row = await self.db.fetchone(
            "SELECT COUNT(*) AS n,COALESCE(SUM(amount_cents),0) AS gmv FROM orders WHERE paid_at>=?", (since,)
        )
        refunds = await self.db.fetchval(
            "SELECT COUNT(*) FROM orders WHERE refund_reason IS NOT NULL AND created_at>=?", (since,), 0
        )
        pending_ship = await self.db.count("orders", "status='paid'")
        paid_n = int(paid_row["n"] or 0) if paid_row else 0
        gmv = int(paid_row["gmv"] or 0) if paid_row else 0
        return {
            "conversations": int(conversations or 0),
            "inbound": int(inbound or 0),
            "outbound": int(outbound or 0),
            "answer_rate": round(float(answered or 0) / conversations * 100, 1) if conversations else 0.0,
            "first_response_p50": round(percentile(latencies, 50) / 1000, 1),
            "first_response_p95": round(percentile(latencies, 95) / 1000, 1),
            "handoff": int(handoff or 0),
            "handoff_rate": round(float(handoff or 0) / conversations * 100, 1) if conversations else 0.0,
            "gateway_block_rate": round(float(blocked or 0) / turns * 100, 1) if turns else 0.0,
            "unanswered": int(unpaid or 0),
            "paid_orders": paid_n,
            "gmv": gmv,
            "conversion_rate": round(paid_n / conversations * 100, 1) if conversations else 0.0,
            "refund_rate": round(float(refunds or 0) / paid_n * 100, 1) if paid_n else 0.0,
            "pending_ship": int(pending_ship or 0),
            "turns": int(turns or 0),
        }

    async def series(self, days: int = 7) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for offset in range(days - 1, -1, -1):
            start = start_of_local_day(-offset)
            end = start_of_local_day(-offset + 1)
            conv = await self.db.fetchval(
                "SELECT COUNT(*) FROM conversations WHERE created_at>=? AND created_at<? AND id!='conv_seller'",
                (iso(start), iso(end)), 0,
            )
            paid = await self.db.fetchone(
                "SELECT COUNT(*) AS n,COALESCE(SUM(amount_cents),0) AS gmv FROM orders WHERE paid_at>=? AND paid_at<?",
                (iso(start), iso(end)),
            )
            msg = await self.db.fetchval(
                "SELECT COUNT(*) FROM messages WHERE direction='in' AND role='buyer' AND created_at>=? AND created_at<?",
                (iso(start), iso(end)), 0,
            )
            out.append({
                "date": local_date(start),
                "label": start.astimezone(config.TZ).strftime("%m-%d"),
                "conversations": int(conv or 0),
                "messages": int(msg or 0),
                "orders": int(paid["n"] or 0) if paid else 0,
                "gmv": int(paid["gmv"] or 0) if paid else 0,
            })
        return out

    async def health(self) -> dict[str, Any]:
        since = iso(now_utc() - timedelta(hours=24))
        tools = await self.db.fetchone(
            "SELECT COUNT(*) AS n,SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS bad FROM tool_calls WHERE created_at>=?",
            (since,),
        )
        llm = await self.db.fetchone(
            "SELECT COUNT(*) AS n,SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS bad FROM llm_calls WHERE created_at>=?",
            (since,),
        )
        tool_n = int(tools["n"] or 0) if tools else 0
        llm_n = int(llm["n"] or 0) if llm else 0
        return {
            "tool_calls": tool_n,
            "tool_error_rate": round(float(tools["bad"] or 0) / tool_n * 100, 1) if tool_n else 0.0,
            "llm_calls": llm_n,
            "llm_fail_rate": round(float(llm["bad"] or 0) / llm_n * 100, 1) if llm_n else 0.0,
        }

    async def overview(self) -> dict[str, Any]:
        return {
            "today": await self.today(),
            "series": await self.series(7),
            "health": await self.health(),
        }

    async def recent_orders(self, limit: int = 8) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT o.*,i.title,i.delivery_mode,b.nick AS buyer_nick FROM orders o "
            "JOIN items i ON i.id=o.item_id LEFT JOIN buyers b ON b.id=o.buyer_id "
            "ORDER BY o.created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    async def recent_conversations(self, limit: int = 8) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            """SELECT c.*,b.nick AS buyer_nick,i.title AS item_title,
               (SELECT text FROM messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC LIMIT 1) AS last_text,
               (SELECT created_at FROM messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC LIMIT 1) AS last_at
               FROM conversations c LEFT JOIN buyers b ON b.id=c.buyer_id LEFT JOIN items i ON i.id=c.item_id
               WHERE c.id!='conv_seller' ORDER BY COALESCE(last_at,c.updated_at) DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]
