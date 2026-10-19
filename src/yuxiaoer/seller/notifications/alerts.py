"""分级告警 + 通知渠道投递。"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.core.util import dumps, iso, loads, new_id, now_utc

log = logging.getLogger("yuxiaoer.alerts")

LEVELS = {"P0": "强提醒", "P1": "普通提醒", "P2": "日报/信息"}


class AlertService:
    def __init__(self, db: Database, bus: EventBus, notifications: Any = None):
        self.db = db
        self.bus = bus
        self.notifications = notifications

    async def create(
        self,
        level: str,
        kind: str,
        title: str,
        body: str = "",
        *,
        conversation_id: str | None = None,
        order_id: str | None = None,
        meta: dict[str, Any] | None = None,
        dedupe_minutes: int = 0,
    ) -> str:
        level = level.upper()
        if level not in LEVELS:
            level = "P1"
        if dedupe_minutes > 0:
            since = iso(now_utc() - timedelta(minutes=dedupe_minutes))
            existing = await self.db.fetchone(
                """SELECT id FROM alerts WHERE status='open' AND kind=? AND
                   COALESCE(conversation_id,'')=COALESCE(?,'') AND
                   COALESCE(order_id,'')=COALESCE(?,'') AND created_at>=?
                   ORDER BY created_at DESC LIMIT 1""",
                (kind, conversation_id, order_id, since),
            )
            if existing:
                return existing["id"]

        alert_id = new_id("alert")
        await self.db.execute(
            """INSERT INTO alerts(id,level,kind,title,body,status,conversation_id,order_id,meta_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (alert_id, level, kind, title, body, "open", conversation_id, order_id, dumps(meta or {}), iso()),
        )
        await self.bus.emit(
            "alert.created",
            {"alert_id": alert_id, "level": level, "kind": kind, "title": title, "body": body},
            session_id=None,
        )
        if self.notifications is not None:
            try:
                await self.notifications.dispatch_alert({
                    "id": alert_id, "level": level, "kind": kind, "title": title,
                    "body": body, "conversation_id": conversation_id, "order_id": order_id,
                })
            except Exception as exc:  # noqa: BLE001
                log.warning("通知分发失败: %s", exc)
        return alert_id

    async def list(self, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
        where = "status=?" if status != "all" else "1=1"
        params: list[Any] = [] if status == "all" else [status]
        rows = await self.db.fetchall(
            f"SELECT * FROM alerts WHERE {where} ORDER BY CASE level WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END, created_at DESC LIMIT ?",
            (*params, limit),
        )
        return [dict(r) | {"meta": loads(r["meta_json"], {})} for r in rows]

    async def ack(self, alert_id: str) -> bool:
        rowcount, _ = await self.db.execute(
            "UPDATE alerts SET status='ack',ack_at=? WHERE id=? AND status='open'", (iso(), alert_id)
        )
        return rowcount > 0

    async def ack_related(
        self,
        *,
        kind: str | None = None,
        order_id: str | None = None,
        conversation_id: str | None = None,
        meta_like: str | None = None,
    ) -> int:
        """动作解决后，把关联的未处理告警一并标掉，避免告警越积越多。"""
        sql = "UPDATE alerts SET status='ack',ack_at=? WHERE status='open'"
        params: list[Any] = [iso()]
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        if order_id:
            sql += " AND order_id=?"
            params.append(order_id)
        if conversation_id:
            sql += " AND conversation_id=?"
            params.append(conversation_id)
        if meta_like:
            sql += " AND meta_json LIKE ?"
            params.append(f"%{meta_like}%")
        rowcount, _ = await self.db.execute(sql, params)
        return rowcount

    async def open_counts(self) -> dict[str, int]:
        rows = await self.db.fetchall(
            "SELECT level,COUNT(*) AS n FROM alerts WHERE status='open' GROUP BY level"
        )
        out = {"P0": 0, "P1": 0, "P2": 0}
        for row in rows:
            out[row["level"]] = int(row["n"])
        out["total"] = sum(out.values())
        return out
