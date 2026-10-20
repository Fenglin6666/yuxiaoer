"""会话与消息：会话创建、入口消息落库、回复频控/夜间延迟、outbox 投递。"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta
from typing import Any

from yuxiaoer.core import config
from yuxiaoer.core.db import Database
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.util import (
    dumps,
    human_time,
    iso,
    loads,
    local_now,
    new_id,
    now_utc,
    parse_iso,
)
from yuxiaoer.seller.notifications.alerts import AlertService
from yuxiaoer.seller.platform.channels import BaseChannel
from yuxiaoer.seller.write_queue import WriteQueue

log = logging.getLogger("yuxiaoer.messaging")


class MessagingService:
    def __init__(
        self,
        db: Database,
        channel: BaseChannel,
        queue: WriteQueue,
        alerts: AlertService,
        settings: SettingsService,
    ):
        self.db = db
        self.channel = channel
        self.queue = queue
        self.alerts = alerts
        self.settings = settings
        self.worker: asyncio.Task | None = None
        self.running = False

    # ---------------- 会话 ----------------

    async def ensure_buyer(self, buyer_id: str, nick: str = "闲鱼买家") -> dict[str, Any]:
        row = await self.db.fetchone("SELECT * FROM buyers WHERE id=?", (buyer_id,))
        if row:
            return dict(row)
        now = iso()
        await self.db.execute(
            "INSERT INTO buyers(id,nick,note,deal_count,blacklist,source,created_at,updated_at)"
            " VALUES(?,?,?,0,0,?,?,?)",
            (buyer_id, nick, "", "channel", now, now),
        )
        row = await self.db.fetchone("SELECT * FROM buyers WHERE id=?", (buyer_id,))
        return dict(row) if row else {"id": buyer_id, "nick": nick}

    async def ensure_conversation(
        self, buyer_id: str, item_id: str | None, *, nick: str = "闲鱼买家", create: bool = True
    ) -> dict[str, Any] | None:
        await self.ensure_buyer(buyer_id, nick)
        row = await self.db.fetchone(
            "SELECT * FROM conversations WHERE buyer_id=? AND COALESCE(item_id,'')=COALESCE(?,'') AND status='active' ORDER BY COALESCE(last_message_at,created_at) DESC LIMIT 1",
            (buyer_id, item_id),
        )
        if row:
            return dict(row)
        if not create:
            return None
        conv_id = new_id("conv")
        session_id = new_id("sess")
        now = iso()
        await self.db.execute(
            """INSERT INTO conversations(id,buyer_id,item_id,session_id,status,handoff,unread_for_owner,
               bargain_round,last_message_at,created_at,updated_at,meta_json)
               VALUES(?,?,?,?,?,0,0,0,?,?,?,?)""",
            (conv_id, buyer_id, item_id, session_id, "active", now, now, now, dumps({})),
        )
        row = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (conv_id,))
        return dict(row) if row else None

    async def seller_conversation(self) -> dict[str, Any]:
        row = await self.db.fetchone("SELECT * FROM conversations WHERE id='conv_seller'")
        if row:
            return dict(row)
        now = iso()
        await self.db.execute(
            """INSERT OR IGNORE INTO conversations(id,buyer_id,item_id,session_id,status,handoff,unread_for_owner,
               bargain_round,last_message_at,created_at,updated_at,meta_json)
               VALUES('conv_seller','owner',NULL,'sess_seller','active',0,0,0,?,?,?,?)""",
            (now, now, now, dumps({"kind": "seller"})),
        )
        row = await self.db.fetchone("SELECT * FROM conversations WHERE id='conv_seller'")
        return dict(row) if row else {}

    # ---------------- 入口消息 ----------------

    async def add_inbound(
        self,
        conversation_id: str,
        text: str,
        *,
        external_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if external_id:
            existing = await self.db.fetchone(
                "SELECT * FROM messages WHERE external_id=?", (external_id,)
            )
            if existing:
                data = dict(existing)
                # 已处理才是重复；未处理说明上一轮进程在排队时退出，必须重新调度。
                data["duplicate"] = bool(int(existing["processed"] or 0))
                return data
        conv = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        msg_id = new_id("msg")
        now = iso()
        await self.db.execute(
            """INSERT INTO messages(id,conversation_id,direction,role,text,external_id,session_id,turn_id,status,meta_json,created_at,processed)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,0)""",
            (msg_id, conversation_id, "in", "buyer", text, external_id,
             conv["session_id"] if conv else None, None, "received", dumps(meta or {}), now),
        )
        await self.db.execute(
            "UPDATE conversations SET last_message_at=?,updated_at=?,unread_for_owner=unread_for_owner+1 WHERE id=?",
            (now, now, conversation_id),
        )
        row = await self.db.fetchone("SELECT * FROM messages WHERE id=?", (msg_id,))
        return dict(row) if row else {}

    async def pending_inbound(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT * FROM messages WHERE conversation_id=? AND direction='in' AND processed=0 ORDER BY created_at,id",
            (conversation_id,),
        )
        return [dict(r) for r in rows]

    async def mark_processed(self, message_ids: list[str]) -> None:
        for msg_id in message_ids:
            await self.db.execute("UPDATE messages SET processed=1 WHERE id=?", (msg_id,))

    async def add_local_message(
        self,
        conversation_id: str,
        text: str,
        *,
        role: str = "system",
        meta: dict[str, Any] | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        """只落库、不过平台通道的消息（小二 Agent 对话、系统卡片）。"""
        conv = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        msg_id = new_id("msg")
        now = iso()
        dir_ = direction or ("out" if role != "buyer" else "in")
        await self.db.execute(
            """INSERT INTO messages(id,conversation_id,direction,role,text,external_id,session_id,turn_id,status,meta_json,created_at,processed)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
            (msg_id, conversation_id, dir_, role, text, None,
             conv["session_id"] if conv else None, None, "sent", dumps(meta or {}), now),
        )
        await self.db.execute(
            "UPDATE conversations SET last_message_at=?,updated_at=? WHERE id=?",
            (now, now, conversation_id),
        )
        row = await self.db.fetchone("SELECT * FROM messages WHERE id=?", (msg_id,))
        return dict(row) if row else {}

    # ---------------- 回复 ----------------

    async def _throttle(self, conversation_id: str) -> tuple[str | None, str | None]:
        night_enabled = await self.settings.get_bool("night_mode", True)
        now_local = local_now()
        if night_enabled and config.NIGHT_START_HOUR <= now_local.hour < config.NIGHT_END_HOUR:
            h, m = [int(x) for x in config.NIGHT_DELAY_TO.split(":")]
            target = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
            return "夜间免打扰（01:00-07:00）", iso(target)

        row = await self.db.fetchone(
            "SELECT COUNT(*) AS n,MIN(created_at) AS first_at FROM messages "
            "WHERE conversation_id=? AND direction='out' AND role='agent' AND created_at>=?",
            (conversation_id, iso(now_utc() - timedelta(minutes=1))),
        )
        if row and int(row["n"] or 0) >= config.RATE_LIMIT_PER_MINUTE:
            first = parse_iso(row["first_at"])
            target = first + timedelta(minutes=1, seconds=1)
            return f"回复频控（1 分钟 ≤ {config.RATE_LIMIT_PER_MINUTE} 条）", iso(target)
        return None, None

    async def send_reply(
        self,
        conversation: dict[str, Any],
        text: str,
        *,
        role: str = "agent",
        turn_id: str | None = None,
        immediate: bool = False,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "空回复"}
        if not immediate and role == "agent":
            reason, send_after = await self._throttle(conversation["id"])
            if send_after:
                outbox_id = new_id("out")
                await self.db.execute(
                    """INSERT INTO outbox(id,conversation_id,buyer_id,item_id,text,session_id,send_after,status,attempts,created_at,meta_json)
                       VALUES(?,?,?,?,?,?,?,'pending',0,?,?)""",
                    (
                        outbox_id, conversation["id"], conversation.get("buyer_id"),
                        conversation.get("item_id"), text, conversation.get("session_id"),
                        send_after, iso(), dumps({"role": role, "turn_id": turn_id, "reason": reason, **(meta or {})}),
                    ),
                )
                return {
                    "ok": True, "scheduled": True, "outbox_id": outbox_id,
                    "send_after": send_after, "reason": reason, "text": text,
                }
        return await self._deliver(
            conversation, text, role=role, turn_id=turn_id, meta=meta
        )

    async def _deliver(
        self,
        conversation: dict[str, Any],
        text: str,
        *,
        role: str = "agent",
        turn_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            if role == "agent" and await self.settings.get_bool("human_typing", False):
                await asyncio.sleep(random.uniform(0.35, 0.95))
            external_id = await self.queue.run(
                lambda: self.channel.send_message(
                    conversation.get("buyer_id") or "",
                    text,
                    conversation_id=conversation["id"],
                    item_id=conversation.get("item_id"),
                ),
                label=f"send:{conversation['id']}",
                min_interval=0.3,
                jitter=0.15,
            )
        except Exception as exc:  # noqa: BLE001
            await self.alerts.create(
                "P1", "send_failed", "消息发送失败",
                f"会话 {conversation['id']} 回复发送失败：{str(exc)[:200]}",
                conversation_id=conversation["id"], dedupe_minutes=10,
            )
            return {"ok": False, "error": str(exc)}
        msg_id = new_id("msg")
        now = iso()
        await self.db.execute(
            """INSERT INTO messages(id,conversation_id,direction,role,text,external_id,session_id,turn_id,status,meta_json,created_at,processed)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
            (msg_id, conversation["id"], "out", role, text, external_id,
             conversation.get("session_id"), turn_id, "sent", dumps(meta or {}), now),
        )
        await self.db.execute(
            "UPDATE conversations SET last_message_at=?,updated_at=? WHERE id=?",
            (now, now, conversation["id"]),
        )
        row = await self.db.fetchone("SELECT * FROM messages WHERE id=?", (msg_id,))
        return {"ok": True, "scheduled": False, "message": dict(row) if row else {}}

    # ---------------- outbox ----------------

    def start(self) -> None:
        if self.worker is None:
            self.running = True
            self.worker = asyncio.create_task(self._outbox_loop(), name="outbox")

    async def stop(self) -> None:
        self.running = False
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except (asyncio.CancelledError, Exception):
                pass
            self.worker = None

    async def _outbox_loop(self) -> None:
        while self.running:
            try:
                await self.process_due()
            except Exception:  # noqa: BLE001
                log.exception("outbox loop error")
            await asyncio.sleep(config.OUTBOX_TICK_SECONDS)

    async def process_due(self) -> int:
        rows = await self.db.fetchall(
            "SELECT * FROM outbox WHERE status='pending' AND send_after<=? ORDER BY send_after LIMIT 20",
            (iso(),),
        )
        for row in rows:
            await self._deliver_outbox(dict(row))
        return len(rows)

    async def flush_all(self) -> int:
        rows = await self.db.fetchall(
            "SELECT * FROM outbox WHERE status='pending' ORDER BY send_after LIMIT 200"
        )
        for row in rows:
            await self._deliver_outbox(dict(row))
        return len(rows)

    async def _deliver_outbox(self, row: dict[str, Any]) -> None:
        conv = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (row["conversation_id"],))
        if not conv:
            await self.db.execute("UPDATE outbox SET status='failed',error='conversation missing' WHERE id=?", (row["id"],))
            return
        meta = loads(row.get("meta_json"), {}) or {}
        result = await self._deliver(
            dict(conv), row["text"], role=meta.get("role", "agent"), turn_id=meta.get("turn_id"), meta=meta
        )
        if result.get("ok"):
            await self.db.execute(
                "UPDATE outbox SET status='sent',sent_at=?,attempts=attempts+1 WHERE id=?",
                (iso(), row["id"]),
            )
        else:
            attempts = int(row.get("attempts") or 0) + 1
            if attempts >= 3:
                await self.db.execute(
                    "UPDATE outbox SET status='failed',attempts=?,error=? WHERE id=?",
                    (attempts, str(result.get("error"))[:300], row["id"]),
                )
            else:
                retry_at = iso(now_utc() + timedelta(seconds=30 * attempts))
                await self.db.execute(
                    "UPDATE outbox SET attempts=?,error=?,send_after=? WHERE id=?",
                    (attempts, str(result.get("error"))[:300], retry_at, row["id"]),
                )

    async def outbox_stats(self) -> dict[str, Any]:
        pending = await self.db.count("outbox", "status='pending'")
        failed = await self.db.count("outbox", "status='failed'")
        next_row = await self.db.fetchone(
            "SELECT send_after FROM outbox WHERE status='pending' ORDER BY send_after LIMIT 1"
        )
        return {
            "pending": pending,
            "failed": failed,
            "next_send_at": next_row["send_after"] if next_row else None,
            "next_send_human": human_time(next_row["send_after"]) if next_row else None,
        }

    # ---------------- 接管 ----------------

    async def set_handoff(self, conversation_id: str, reason: str, minutes: int = 30) -> None:
        now = now_utc()
        await self.db.execute(
            "UPDATE conversations SET handoff=1,handoff_until=?,handoff_reason=?,updated_at=? WHERE id=?",
            (iso(now + timedelta(minutes=minutes)), reason, iso(now), conversation_id),
        )

    async def resume(self, conversation_id: str) -> None:
        await self.db.execute(
            "UPDATE conversations SET handoff=0,handoff_until=NULL,handoff_reason=NULL,updated_at=? WHERE id=?",
            (iso(), conversation_id),
        )

    async def mark_owner_read(self, conversation_id: str) -> None:
        await self.db.execute(
            "UPDATE conversations SET unread_for_owner=0 WHERE id=?", (conversation_id,)
        )

    async def mark_owner_unread(self, conversation_id: str) -> None:
        await self.db.execute(
            "UPDATE conversations SET unread_for_owner=unread_for_owner+1 WHERE id=?",
            (conversation_id,),
        )

    async def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        return dict(row) if row else None

    async def messages(self, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
            (conversation_id, limit),
        )
        return [dict(r) | {"meta": loads(r["meta_json"], {})} for r in reversed(rows)]
