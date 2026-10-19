"""持久化事件总线（进程内同步投递 + 启动重放）。

事件先落 events 表，再调用处理器；处理器失败会留痕并产生 P1 告警。
单进程、低吞吐场景下这比引入 MQ 更可靠：崩溃后启动时重放未完成事件。
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from yuxiaoer.core.db import Database
from yuxiaoer.core.util import dumps, iso, new_id, now_utc

log = logging.getLogger("yuxiaoer.events")

Handler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self, db: Database):
        self.db = db
        self._handlers: dict[str, list[Handler]] = {}
        self.delivered = 0
        self.failed = 0
        self.last_error: str | None = None

    def on(self, topic: str, handler: Handler) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    async def emit(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        actor: str = "system",
    ) -> str:
        event_id = new_id("evt")
        await self.db.execute(
            """INSERT INTO events(event_id,topic,payload_json,status,attempts,session_id,created_at)
               VALUES(?,?,?,?,0,?,?)""",
            (event_id, topic, dumps(payload), "pending", session_id, iso()),
        )
        await self._dispatch(event_id, topic, payload, session_id)
        return event_id

    async def _dispatch(
        self,
        event_id: str,
        topic: str,
        payload: dict[str, Any],
        session_id: str | None,
        attempts: int = 0,
    ) -> None:
        handlers = self._handlers.get(topic, [])
        meta = {"event_id": event_id, "topic": topic, "session_id": session_id}
        try:
            for handler in handlers:
                await handler(payload, meta)
            await self.db.execute(
                "UPDATE events SET status='done',attempts=?,consumed_at=?,error=NULL WHERE event_id=?",
                (attempts + 1, iso(), event_id),
            )
            self.delivered += 1
        except Exception as exc:  # noqa: BLE001
            self.failed += 1
            self.last_error = f"{topic}: {exc}"
            log.exception("event handler failed: %s", topic)
            await self.db.execute(
                "UPDATE events SET status='failed',attempts=?,error=? WHERE event_id=?",
                (attempts + 1, str(exc)[:500], event_id),
            )
            await self._alert_failure(topic, event_id, exc)

    async def _alert_failure(self, topic: str, event_id: str, exc: Exception) -> None:
        try:
            await self.db.execute(
                "INSERT INTO alerts(id,level,kind,title,body,status,meta_json,created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    new_id("alert"), "P1", "event_failed", f"事件处理失败：{topic}",
                    f"事件 {event_id} 处理异常：{str(exc)[:200]}。请查看事件流并重试。",
                    "open", dumps({"event_id": event_id}), iso(),
                ),
            )
        except Exception:
            pass

    async def replay_pending(self, limit: int = 200) -> int:
        rows = await self.db.fetchall(
            "SELECT * FROM events WHERE status IN ('pending','processing') ORDER BY id LIMIT ?",
            (limit,),
        )
        count = 0
        for row in rows:
            payload = {}
            try:
                import json

                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            await self._dispatch(
                row["event_id"], row["topic"], payload, row["session_id"], int(row["attempts"] or 0)
            )
            count += 1
        return count

    async def backlog(self) -> int:
        return await self.db.count("events", "status IN ('pending','processing')")

    def stats(self) -> dict[str, Any]:
        return {"delivered": self.delivered, "failed": self.failed, "last_error": self.last_error}
