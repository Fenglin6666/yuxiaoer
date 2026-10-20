"""入口直投网关：每条买家消息立即进入 Agent，不做合并、不做 debounce。

之前的 IngestService 会把同一会话的消息攒 1.5 秒再处理；现在改成：
- 消息按会话进入独立 FIFO 队列；
- 每个会话一个 worker，严格“一条消息一个 turn、一条回复”；
- 入队前不做数据库查询，商品/会话/去重都在 worker 里、进入 Agent 边界时处理。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from yuxiaoer.buyer.conversation.agent import BuyerAgent
from yuxiaoer.core.db import Database
from yuxiaoer.core.util import dumps, iso, loads
from yuxiaoer.shared.ports import MessagingPort

log = logging.getLogger("yuxiaoer.ingest")


class IngestService:
    def __init__(self, db: Database, messaging: MessagingPort, buyer: BuyerAgent):
        self.db = db
        self.messaging = messaging
        self.buyer = buyer
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._recovery: set[asyncio.Task] = set()
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
        platform_item_id: str | None = None,
    ) -> dict[str, Any]:
        """只入队，不做数据库 IO——这是 Agent 前唯一的动作。"""
        if self._stopped:
            return {"queued": False, "error": "ingest stopped"}
        key = f"{buyer_id}|{item_id or platform_item_id or ''}"
        queue = self._queues.get(key)
        if queue is None:
            queue = asyncio.Queue()
            self._queues[key] = queue
            self._workers[key] = asyncio.create_task(
                self._worker(key, queue), name=f"ingest:{key}"
            )
        await queue.put({
            "buyer_id": buyer_id,
            "nick": nick,
            "text": text,
            "item_id": item_id,
            "platform_item_id": platform_item_id,
            "external_id": external_id,
            "platform_chat_id": platform_chat_id,
        })
        return {"queued": True, "queue": key}

    async def _worker(self, key: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        while True:
            job = await queue.get()
            try:
                await self._handle_job(job)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("ingest job failed: %s", key)
            finally:
                queue.task_done()

    async def _handle_job(self, job: dict[str, Any]) -> None:
        item_id = job.get("item_id")
        if not item_id and job.get("platform_item_id"):
            item_id = await self._resolve_item(str(job["platform_item_id"]))

        conv = await self.messaging.ensure_conversation(
            job["buyer_id"], item_id, nick=job["nick"]
        )
        if not conv:
            raise RuntimeError("无法创建会话")

        chat_id = job.get("platform_chat_id")
        if chat_id:
            meta = loads(conv.get("meta_json"), {}) or {}
            meta.update({
                "platform_chat_id": str(chat_id).replace("@goofish", ""),
                "platform_buyer_id": str(job["buyer_id"]).replace("@goofish", ""),
                "source": "xianyu_ws",
            })
            await self.db.execute(
                "UPDATE conversations SET meta_json=?,updated_at=? WHERE id=?",
                (dumps(meta), iso(), conv["id"]),
            )

        msg = await self.messaging.add_inbound(
            conv["id"], job["text"], external_id=job.get("external_id"),
            meta={"source": "buyer_channel"},
        )
        if msg.get("duplicate"):
            return
        await self.buyer.handle_message(conv["id"], msg["id"])
        self.processed_turns += 1

    async def _resolve_item(self, platform_id: str) -> str:
        row = await self.db.fetchone(
            "SELECT id FROM items WHERE platform_item_id=? LIMIT 1", (platform_id,)
        )
        if row:
            return row["id"]
        item_id = f"xyitem_{platform_id}"
        now = iso()
        await self.db.execute(
            """INSERT OR IGNORE INTO items(id,platform_item_id,title,description,price_cents,floor_price_cents,
               max_discount_pct,category,condition,delivery_mode,stock,status,card_content,link_url,image_hint,
               knowledge_version,relist_count,relist_limit,sold_count,created_at,updated_at,meta_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id, platform_id, f"平台商品 {platform_id}",
                "来自 WebSocket 消息的自动占位商品；请补充标题、描述和卡券。",
                1, 1, 15, "平台同步", "二手", "physical", 1, "live", None, None, "📦",
                0, 0, 3, 0, now, now, dumps({"source": "xianyu_ws"}),
            ),
        )
        return item_id

    async def recover_pending(self) -> int:
        """重启后把未处理消息逐条投回 Agent，不做合并。"""
        rows = await self.db.fetchall(
            "SELECT DISTINCT conversation_id FROM messages WHERE direction='in' AND processed=0"
        )
        for row in rows:
            task = asyncio.create_task(
                self._recover_conversation(row["conversation_id"]),
                name=f"ingest-recover:{row['conversation_id']}",
            )
            self._recovery.add(task)
            task.add_done_callback(self._recovery.discard)
        return len(rows)

    async def _recover_conversation(self, conversation_id: str) -> None:
        rows = await self.db.fetchall(
            "SELECT id FROM messages WHERE conversation_id=? AND direction='in' AND processed=0 "
            "ORDER BY created_at,id",
            (conversation_id,),
        )
        for row in rows:
            try:
                await self.buyer.handle_message(conversation_id, row["id"])
            except Exception:  # noqa: BLE001
                log.exception("ingest recover failed: %s", conversation_id)

    async def flush(self) -> int:
        """测试/运维用：等当前所有队列处理完。"""
        await asyncio.gather(*(q.join() for q in self._queues.values()))
        return self.processed_turns

    def stop(self) -> None:
        self._stopped = True
        for task in self._workers.values():
            task.cancel()
        self._workers.clear()
        self._queues.clear()
        for task in self._recovery:
            task.cancel()
        self._recovery.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "queues": len(self._queues),
            "workers": len(self._workers),
            "processed_turns": self.processed_turns,
        }
