"""通知抽象层：一个 Alert → 多渠道投递 + 失败重试 + 投递日志。

参考 Usagi monitor 的通知矩阵思路，按自己的数据模型实现：
- 渠道：站内日志 / 企业微信 / Bark / Server酱 / ntfy / Telegram / PushPlus / Gotify / 通用 Webhook；
- 级别过滤：渠道设置 min_level（P1 表示 P0+P1，P2 只发 P2）；
- 每渠道最多 3 次退避重试；结果落 notification_logs，UI 可查。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from yuxiaoer.core.db import Database
from yuxiaoer.core.util import dumps, human_time, iso, loads, new_id, now_utc

from .channels import SENDERS, Message

log = logging.getLogger("yuxiaoer.notify")

LEVEL_RANK = {"P0": 0, "P1": 1, "P2": 2}
KINDS = {
    "log": "站内日志", "wecom": "企业微信机器人", "bark": "Bark（iOS）",
    "serverchan": "Server酱", "ntfy": "ntfy", "telegram": "Telegram",
    "pushplus": "PushPlus", "gotify": "Gotify", "generic": "通用 Webhook",
    "email": "邮箱（SMTP/IMAP）",
}


def _allowed(min_level: str, level: str) -> bool:
    return LEVEL_RANK.get(level, 9) <= LEVEL_RANK.get(min_level, 1)


class NotificationService:
    def __init__(self, db: Database):
        self.db = db
        self._tasks: set[asyncio.Task] = set()

    async def list_channels(self) -> list[dict[str, Any]]:
        rows = await self.db.fetchall("SELECT * FROM notify_channels ORDER BY created_at")
        return [self._row(r) for r in rows]

    async def get(self, channel_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchone("SELECT * FROM notify_channels WHERE id=?", (channel_id,))
        return self._row(row) if row else None

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        data = dict(row)
        data["config"] = loads(data.get("config_json"), {}) or {}
        data["kind_label"] = KINDS.get(data.get("kind"), data.get("kind"))
        data["enabled"] = bool(data.get("enabled"))
        data["config_summary"] = _config_summary(data["config"])
        return data

    async def upsert(self, payload: dict[str, Any], channel_id: str | None = None) -> dict[str, Any]:
        kind = str(payload.get("kind") or "generic")
        if kind not in KINDS:
            raise ValueError("不支持的通知渠道")
        name = str(payload.get("name") or KINDS[kind])[:60]
        config = payload.get("config") or {}
        enabled = 1 if payload.get("enabled", True) else 0
        min_level = str(payload.get("min_level") or "P1").upper()
        if min_level not in LEVEL_RANK:
            min_level = "P1"
        cid = channel_id or new_id("ch")
        now = iso()
        if channel_id:
            exists = await self.db.fetchone("SELECT id FROM notify_channels WHERE id=?", (channel_id,))
            if not exists:
                raise KeyError("渠道不存在")
            await self.db.execute(
                "UPDATE notify_channels SET kind=?,name=?,config_json=?,enabled=?,min_level=?,updated_at=? WHERE id=?",
                (kind, name, dumps(config), enabled, min_level, now, cid),
            )
        else:
            await self.db.execute(
                "INSERT INTO notify_channels(id,kind,name,config_json,enabled,min_level,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (cid, kind, name, dumps(config), enabled, min_level, now, now),
            )
        return await self.get(cid) or {}

    async def delete(self, channel_id: str) -> bool:
        rowcount, _ = await self.db.execute("DELETE FROM notify_channels WHERE id=?", (channel_id,))
        return rowcount > 0

    async def dispatch_alert(self, alert: dict[str, Any]) -> list[str]:
        channels = [c for c in await self.list_channels() if c["enabled"] and _allowed(c["min_level"], alert.get("level", "P1"))]
        log_ids = []
        for channel in channels:
            log_id = await self._new_log(channel["id"], alert.get("id"), alert.get("level"))
            log_ids.append(str(log_id))
            task = asyncio.create_task(self._deliver(log_id, channel, alert), name=f"notify:{channel['id']}")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return log_ids

    async def _new_log(self, channel_id: str, alert_id: str | None, level: str) -> int:
        _, rowid = await self.db.execute(
            "INSERT INTO notification_logs(channel_id,alert_id,level,status,attempts,created_at)"
            " VALUES(?,?,?,?,0,?)",
            (channel_id, alert_id, level, "pending", iso()),
        )
        return int(rowid or 0)

    async def _deliver(self, log_id: int, channel: dict[str, Any], alert: dict[str, Any]) -> None:
        attempts = 0
        last_error = ""
        response = ""
        for attempt in range(1, 4):
            attempts = attempt
            try:
                response = await self._send(channel, alert)
                await self.db.execute(
                    "UPDATE notification_logs SET status='sent',attempts=?,response=?,sent_at=? WHERE id=?",
                    (attempts, response[:500], iso(), log_id),
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)[:500]
                if attempt < 3:
                    await asyncio.sleep(0.6 * attempt)
        await self.db.execute(
            "UPDATE notification_logs SET status='failed',attempts=?,error=? WHERE id=?",
            (attempts, last_error, log_id),
        )

    async def _send(self, channel: dict[str, Any], alert: dict[str, Any]) -> str:
        kind = channel["kind"]
        sender = SENDERS.get(kind)
        if sender is None:
            raise ValueError(f"未知渠道 {kind}")
        level = alert.get("level", "P1")
        message = Message(
            title=f"【鱼小二 · {level}】{alert.get('title', '')}",
            body=alert.get("body") or "",
            level=level,
            alert=alert,
        )
        return await sender(channel.get("config") or {}, message)

    async def send_test(self, channel_id: str) -> dict[str, Any]:
        channel = await self.get(channel_id)
        if not channel:
            raise KeyError("渠道不存在")
        alert = {
            "id": "test", "level": "P1", "title": "测试通知",
            "body": f"这是一条来自鱼小二的通知测试。{human_time(now_utc())}",
        }
        log_id = await self._new_log(channel_id, "test", "P1")
        await self._deliver(log_id, channel, alert)
        row = await self.db.fetchone("SELECT * FROM notification_logs WHERE id=?", (log_id,))
        return dict(row) if row else {}

    async def logs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT l.*,c.name AS channel_name,c.kind AS channel_kind FROM notification_logs l "
            "LEFT JOIN notify_channels c ON c.id=l.channel_id ORDER BY l.id DESC LIMIT ?",
            (limit,),
        )
        out = []
        for row in rows:
            data = dict(row)
            data["created_human"] = human_time(data.get("created_at"))
            data["sent_human"] = human_time(data.get("sent_at")) if data.get("sent_at") else "—"
            out.append(data)
        return out

    async def flush(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def stats(self) -> dict[str, Any]:
        total = await self.db.count("notify_channels")
        enabled = await self.db.count("notify_channels", "enabled=1")
        sent = await self.db.count("notification_logs", "status='sent'")
        failed = await self.db.count("notification_logs", "status='failed'")
        return {"channels": total, "enabled": enabled, "sent": sent, "failed": failed, "kinds": KINDS}


def _config_summary(config: dict[str, Any]) -> str:
    if not config:
        return "无需配置"
    parts = []
    for key in ("smtp_host", "imap_host", "from_addr", "to_addr", "url", "topic", "chat_id"):
        if config.get(key):
            parts.append(f"{key}={config[key]}")
    if config.get("token"):
        parts.append("token=****")
    if config.get("smtp_password") or config.get("imap_password"):
        parts.append("password=****")
    return " · ".join(parts) or "已配置"
