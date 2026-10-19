"""确认门：钱路动作执行前先产预览，店主确认后才执行。

- 30 分钟过期，过期自动作废；
- 支持对话里说"确认"（取最近一条 pending）或点击卡片按钮；
- 所有确认/驳回写审计。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from yuxiaoer.core import config
from yuxiaoer.core.db import Database
from yuxiaoer.core.util import dumps, iso, loads, new_id, now_utc


class ConfirmationService:
    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        kind: str,
        title: str,
        preview: dict[str, Any],
        payload: dict[str, Any],
        *,
        source: str = "agent",
        ttl_minutes: int | None = None,
    ) -> dict[str, Any]:
        await self.expire()
        cid = new_id("cfm")
        now = now_utc()
        expires = now + timedelta(minutes=ttl_minutes or config.CONFIRM_TTL_MINUTES)
        await self.db.execute(
            """INSERT INTO confirmations(id,kind,title,preview_json,payload_json,status,expires_at,created_at,source)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (cid, kind, title, dumps(preview), dumps(payload), "pending", iso(expires), iso(now), source),
        )
        row = await self.db.fetchone("SELECT * FROM confirmations WHERE id=?", (cid,))
        return self._row(row) if row else {}

    async def latest_pending(self) -> dict[str, Any] | None:
        await self.expire()
        row = await self.db.fetchone(
            "SELECT * FROM confirmations WHERE status='pending' ORDER BY created_at DESC LIMIT 1"
        )
        return self._row(row) if row else None

    async def get(self, confirmation_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchone("SELECT * FROM confirmations WHERE id=?", (confirmation_id,))
        return self._row(row) if row else None

    async def list(self, status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
        await self.expire()
        if status == "all":
            rows = await self.db.fetchall(
                "SELECT * FROM confirmations ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        else:
            rows = await self.db.fetchall(
                "SELECT * FROM confirmations WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        return [self._row(r) for r in rows]

    async def mark(self, confirmation_id: str, status: str, note: str | None = None) -> bool:
        rowcount, _ = await self.db.execute(
            "UPDATE confirmations SET status=?,resolved_at=?,note=? WHERE id=? AND status='pending'",
            (status, iso(), note, confirmation_id),
        )
        return rowcount > 0

    async def update_pending(
        self,
        confirmation_id: str,
        *,
        title: str,
        preview: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        rowcount, _ = await self.db.execute(
            """UPDATE confirmations SET title=?,preview_json=?,payload_json=?
               WHERE id=? AND status='pending'""",
            (title, dumps(preview), dumps(payload), confirmation_id),
        )
        return await self.get(confirmation_id) if rowcount else None

    async def expire(self) -> int:
        rowcount, _ = await self.db.execute(
            "UPDATE confirmations SET status='expired',resolved_at=? WHERE status='pending' AND expires_at<?",
            (iso(), iso()),
        )
        return rowcount

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        data = dict(row)
        data["preview"] = loads(data.get("preview_json"), {})
        data["payload"] = loads(data.get("payload_json"), {})
        return data
