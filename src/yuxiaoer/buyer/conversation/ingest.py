"""入口消息合并器：同一买家 5 秒内的多条消息合并为一轮。

- 每个会话一个 debounce timer；
- Agent 处理期间到达的新消息，处理完后再起一轮；
- 生产默认 5s，可通过设置调小。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from yuxiaoer.buyer.conversation.agent import BuyerAgent
from yuxiaoer.core.db import Database
from yuxiaoer.seller.conversation.messaging import MessagingService
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.util import dumps, iso, loads

log = logging.getLogger("yuxiaoer.ingest")


class IngestService:
    def __init__(
        self,
        db: Database,
        messaging: MessagingService,
        buyer: BuyerAgent,
        settings: SettingsService,
    ):
        self.db = db
        self.messaging = messaging
        self.buyer = buyer
        self.settings = settings
        self._timers: dict[str, asyncio.Task] = {}
        self._processing: set[str] = set()
        self._stopped = False
        self.processed_turns = 0

    async def submit_buyer_message(
        self,
        *,
        buyer_id: str,
        text: str,
        item_id: str | None,
        nick: str = "闲鱼买家",
        external_id: str | None = None,
        platform_chat_id: str | None = None,
    ) -> dict[str, Any]:
        conv = await self.messaging.ensure_conversation(buyer_id, item_id, nick=nick)
        if not conv:
            raise RuntimeError("无法创建会话")
        if platform_chat_id:
            meta = loads(conv.get("meta_json"), {}) or {}
            meta.update({
                "platform_chat_id": str(platform_chat_id).replace("@goofish", ""),
                "platform_buyer_id": str(buyer_id).replace("@goofish", ""),
                "source": "xianyu_ws",
            })
            await self.db.execute(
                "UPDATE conversations SET meta_json=?,updated_at=? WHERE id=?",
                (dumps(meta), iso(), conv["id"]),
            )
        msg = await self.messaging.add_inbound(
            conv["id"], text, external_id=external_id, meta={"source": "buyer_channel"}
        )
        if msg.get("duplicate"):
            return {"conversation_id": conv["id"], "message_id": msg.get("id"), "duplicate": True}
        self._schedule(conv["id"])
        return {"conversation_id": conv["id"], "message_id": msg.get("id"), "session_id": conv["session_id"]}

    def _schedule(self, conversation_id: str) -> None:
        if self._stopped:
            return
        existing = self._timers.get(conversation_id)
        if existing and not existing.done():
            existing.cancel()
        task = asyncio.create_task(self._run_later(conversation_id), name=f"ingest:{conversation_id}")
        self._timers[conversation_id] = task

    async def _run_later(self, conversation_id: str) -> None:
        try:
            window = await self.settings.get_float("merge_window_seconds", 1.5)
            await asyncio.sleep(max(0.0, window))
        except asyncio.CancelledError:
            return
        if conversation_id in self._processing:
            return
        self._timers.pop(conversation_id, None)
        self._processing.add(conversation_id)
        try:
            await self.buyer.handle_pending(conversation_id)
            self.processed_turns += 1
        except Exception:  # noqa: BLE001
            log.exception("ingest processing failed")
        finally:
            self._processing.discard(conversation_id)
        pending = await self.messaging.pending_inbound(conversation_id)
        if pending:
            self._schedule(conversation_id)

    async def recover_pending(self) -> int:
        """服务重启后，把已入库但没处理完的入站消息重新排期。"""
        rows = await self.db.fetchall(
            "SELECT DISTINCT conversation_id FROM messages WHERE direction='in' AND processed=0"
        )
        for row in rows:
            self._schedule(row["conversation_id"])
        return len(rows)

    async def flush(self) -> int:
        """测试/运维用：取消等待窗口，立即处理所有 pending。"""
        for task in list(self._timers.values()):
            task.cancel()
        self._timers.clear()
        # 如果某个会话已经在处理，等它结束，避免调用方读到半成品
        for _ in range(200):
            if not self._processing:
                break
            await asyncio.sleep(0.01)
        rows = await self.db.fetchall(
            "SELECT DISTINCT conversation_id FROM messages WHERE direction='in' AND processed=0"
        )
        count = 0
        for row in rows:
            conv_id = row["conversation_id"]
            if conv_id in self._processing:
                continue
            self._processing.add(conv_id)
            try:
                await self.buyer.handle_pending(conv_id)
                count += 1
            finally:
                self._processing.discard(conv_id)
        return count

    def stop(self) -> None:
        self._stopped = True
        for task in self._timers.values():
            task.cancel()
        self._timers.clear()

    def cancel_pending(self) -> None:
        for task in self._timers.values():
            task.cancel()
        self._timers.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "timers": len(self._timers),
            "processing": len(self._processing),
            "processed_turns": self.processed_turns,
        }
