"""值守循环：心跳/掉线重连、链接巡检、每日擦亮、日报。

调度器在进程内每 5s 检查一次 patrol_jobs.next_run_at。
所有平台写动作都走 write queue，失败退避并产生告警。
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

from yuxiaoer.seller.notifications.alerts import AlertService
from yuxiaoer.seller.platform.channels import BaseChannel
from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.buyer.knowledge.service import KnowledgeService
from yuxiaoer.seller.conversation.messaging import MessagingService
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.util import (
    dumps, human_time, iso, loads, local_now, new_id, next_local_time, now_utc,
    parse_iso, snippet, start_of_local_day, yuan,
)
from yuxiaoer.seller.write_queue import WriteQueue

log = logging.getLogger("yuxiaoer.patrol")


class PatrolService:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        channel: BaseChannel,
        queue: WriteQueue,
        alerts: AlertService,
        knowledge: KnowledgeService,
        messaging: MessagingService,
        settings: SettingsService,
    ):
        self.db = db
        self.bus = bus
        self.channel = channel
        self.queue = queue
        self.alerts = alerts
        self.knowledge = knowledge
        self.messaging = messaging
        self.settings = settings
        self.worker: asyncio.Task | None = None
        self.running = False
        self._locks: dict[str, asyncio.Lock] = {}
        self.last_tick_at: str | None = None

    # ---------------- 调度 ----------------

    async def start(self) -> None:
        await self.ensure_jobs()
        if self.worker is None:
            self.running = True
            self.worker = asyncio.create_task(self._loop(), name="patrol")

    async def stop(self) -> None:
        self.running = False
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except (asyncio.CancelledError, Exception):
                pass
            self.worker = None

    async def _loop(self) -> None:
        while self.running:
            try:
                self.last_tick_at = iso()
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("patrol tick failed")
            await asyncio.sleep(5)

    async def ensure_jobs(self) -> None:
        defaults = [
            ("heartbeat", "账号心跳 / 掉线重连", 1800, None),
            ("link_check", "网盘链接巡检", 21600, None),
            ("polish", "每日擦亮", None, {"local_time": "10:05"}),
            ("daily_report", "每日 21:00 日报", None, {"local_time": "21:00"}),
        ]
        for name, title, interval, schedule in defaults:
            exists = await self.db.fetchone("SELECT 1 FROM patrol_jobs WHERE name=?", (name,))
            if not exists:
                next_run = iso(now_utc() + timedelta(seconds=interval or 300))
                await self.db.execute(
                    "INSERT INTO patrol_jobs(name,title,interval_seconds,schedule_json,next_run_at,enabled)"
                    " VALUES(?,?,?,?,?,1)",
                    (name, title, interval, dumps(schedule) if schedule else None, next_run),
                )

    async def tick(self) -> None:
        rows = await self.db.fetchall(
            "SELECT * FROM patrol_jobs WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=?",
            (iso(),),
        )
        for row in rows:
            await self.run_job(row["name"], manual=False)

    async def update_job(
        self,
        name: str,
        *,
        enabled: bool | None = None,
        local_time: str | None = None,
        interval_seconds: int | None = None,
    ) -> dict[str, Any]:
        job = await self.db.fetchone("SELECT * FROM patrol_jobs WHERE name=?", (name,))
        if not job:
            raise KeyError("任务不存在")
        job = dict(job)
        fields: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            fields.append("enabled=?")
            params.append(1 if enabled else 0)
        schedule = loads(job.get("schedule_json"), {}) or {}
        if local_time:
            if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", local_time):
                raise ValueError("时间格式应为 HH:MM")
            schedule = {"local_time": local_time}
            fields.extend(["schedule_json=?", "interval_seconds=NULL"])
            params.append(dumps(schedule))
            job["interval_seconds"] = None
        if interval_seconds is not None:
            if interval_seconds < 30:
                raise ValueError("间隔不能小于 30 秒")
            fields.extend(["interval_seconds=?", "schedule_json=NULL"])
            params.append(int(interval_seconds))
            job["interval_seconds"] = interval_seconds
            schedule = {}
        job["schedule_json"] = dumps(schedule) if schedule else None
        next_run = await self._schedule_next(job, manual=False)
        fields.append("next_run_at=?")
        params.append(next_run)
        params.append(name)
        await self.db.execute(f"UPDATE patrol_jobs SET {', '.join(fields)} WHERE name=?", params)
        await self.bus.emit("patrol.schedule_updated", {"name": name, "next_run_at": next_run})
        return await self.job_info(name) or {}

    async def _schedule_next(self, job: dict[str, Any], *, manual: bool) -> str:
        if job.get("interval_seconds"):
            return iso(now_utc() + timedelta(seconds=int(job["interval_seconds"])))
        schedule = loads(job.get("schedule_json"), {}) or {}
        local_time = schedule.get("local_time")
        if local_time:
            return iso(next_local_time(local_time, after=now_utc()))
        return iso(now_utc() + timedelta(hours=1))

    # ---------------- 执行 ----------------

    async def run_job(self, name: str, *, manual: bool = False) -> dict[str, Any]:
        lock = self._locks.setdefault(name, asyncio.Lock())
        if lock.locked():
            return {"ok": False, "text": "该任务正在执行中，请稍后。"}
        async with lock:
            job = await self.db.fetchone("SELECT * FROM patrol_jobs WHERE name=?", (name,))
            if not job:
                return {"ok": False, "text": "任务不存在"}
            job = dict(job)
            started = iso()
            try:
                if name == "heartbeat":
                    result = await self._heartbeat()
                elif name == "link_check":
                    result = await self._link_check()
                elif name == "polish":
                    result = await self._polish()
                elif name == "daily_report":
                    result = await self._daily_report()
                else:
                    result = {"ok": False, "text": f"未知任务 {name}"}
            except Exception as exc:  # noqa: BLE001
                log.exception("job %s failed", name)
                result = {"ok": False, "text": f"任务失败：{str(exc)[:160]}"}
                await self.alerts.create(
                    "P1", "patrol_failed", f"值守任务失败：{job['title']}",
                    str(exc)[:300], dedupe_minutes=10,
                )
            next_run = await self._schedule_next(job, manual=manual)
            await self.db.execute(
                "UPDATE patrol_jobs SET last_run_at=?,last_status=?,last_detail=?,next_run_at=? WHERE name=?",
                (started, "ok" if result.get("ok") else "failed",
                 snippet(result.get("text", ""), 500), next_run, name),
            )
            await self.bus.emit(
                "patrol.run",
                {"name": name, "ok": result.get("ok"), "text": result.get("text"),
                 "manual": manual, "next_run_at": next_run},
            )
            result["job"] = await self.job_info(name)
            return result

    async def _heartbeat(self) -> dict[str, Any]:
        account = await self.db.fetchone("SELECT * FROM accounts ORDER BY updated_at DESC LIMIT 1")
        if not account:
            return {"ok": True, "text": "还没有登录账号，跳过心跳"}
        health = await self.channel.health()
        online = bool(health.get("online"))
        if not online and hasattr(self.channel, "restart"):
            try:
                await self.channel.restart()
                await asyncio.sleep(2)
                health = await self.channel.health()
                online = bool(health.get("online"))
                if online:
                    await self.alerts.create(
                        "P2", "reconnected", "账号掉线已自动重连",
                        "检测到 WebSocket 掉线，已自动重连成功。", dedupe_minutes=10,
                    )
                    await self.alerts.ack_related(kind="account_offline")
            except Exception:
                pass
        if online:
            now_iso = iso()
            if account:
                await self.db.execute(
                    "UPDATE accounts SET status='online',last_heartbeat_at=?,detail=?,updated_at=? WHERE id=?",
                    (now_iso, health.get("detail") or "心跳正常", now_iso, account["id"]),
                )
            return {"ok": True, "text": f"账号在线 · {health.get('detail') or '心跳正常'} · {human_time(now_iso)}"}
        await self.alerts.create(
            "P0", "account_offline", "账号掉线，需要重新扫码",
            f"心跳失败：{health.get('detail')}。请检查账号 Cookie 并重新扫码。", dedupe_minutes=10,
        )
        if account:
            await self.db.execute(
                "UPDATE accounts SET status='offline',detail=?,updated_at=? WHERE id=?",
                (health.get("detail") or "掉线", iso(), account["id"]),
            )
        return {"ok": False, "text": f"账号掉线：{health.get('detail')}，已发 P0 告警。"}

    async def _link_check(self) -> dict[str, Any]:
        items = await self.db.fetchall(
            "SELECT * FROM items WHERE status='live' AND delivery_mode='virtual' AND link_url IS NOT NULL"
        )
        checked = 0
        broken: list[dict[str, Any]] = []
        for item in items:
            checked += 1
            alive = await self.channel.check_link(item["link_url"])
            if alive:
                continue
            broken.append({"item_id": item["id"], "title": item["title"], "url": item["link_url"]})
            await self.alerts.create(
                "P1", "link_dead", "链接失效",
                f"「{item['title']}」的链接已失效，请到商品详情手动更新卡券链接。",
                meta={"item_id": item["id"]}, dedupe_minutes=30,
            )
        text = f"链接巡检完成：检查 {checked} 个虚拟商品，失效 {len(broken)} 个。"
        if broken:
            text += "\n" + "\n".join(f"· {r['title']}" for r in broken)
        return {"ok": True, "text": text, "detail": {"checked": checked, "broken": broken}}

    async def _polish(self) -> dict[str, Any]:
        items = await self.db.fetchall("SELECT * FROM items WHERE status='live'")
        count = await self.queue.run(
            lambda: self.channel.polish_items([dict(i) for i in items]), label="polish"
        )
        await self.bus.emit("patrol.polished", {"count": count})
        return {"ok": True, "text": f"擦亮完成：{count} 件在售商品已擦亮 · {local_now().strftime('%H:%M')}"}

    async def _daily_report(self) -> dict[str, Any]:
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
        handoff = await self.db.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE handoff=1 AND updated_at>=?", (since,), 0
        )
        paid_row = await self.db.fetchone(
            "SELECT COUNT(*) AS n,COALESCE(SUM(amount_cents),0) AS gmv FROM orders WHERE paid_at>=?", (since,)
        )
        pending_ship = await self.db.count("orders", "status='paid'")
        refunds = await self.db.count("orders", "status='refund_open'")
        text = (
            f"📊 鱼小二日报（{local_now().strftime('%Y-%m-%d')}）\n"
            f"咨询会话 {conversations} · 买家消息 {inbound} · 自动回复 {outbound} · 转人工 {handoff}\n"
            f"成交 {paid_row['n'] if paid_row else 0} 单 · GMV ¥{yuan(paid_row['gmv'] if paid_row else 0)} · "
            f"待发货 {pending_ship} · 退款中 {refunds}"
        )
        alert_id = await self.alerts.create("P2", "daily_report", "今日经营日报", text, dedupe_minutes=60)
        seller = await self.messaging.seller_conversation()
        await self.messaging.add_local_message(seller["id"], text, role="system", meta={"alert_id": alert_id})
        return {"ok": True, "text": text}

    # ---------------- 查询 ----------------

    async def job_info(self, name: str) -> dict[str, Any] | None:
        row = await self.db.fetchone("SELECT * FROM patrol_jobs WHERE name=?", (name,))
        if not row:
            return None
        data = dict(row)
        data["next_run_human"] = human_time(data.get("next_run_at"))
        data["last_run_human"] = human_time(data.get("last_run_at"))
        data["schedule"] = loads(data.get("schedule_json"), {})
        return data

    async def jobs(self) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT name FROM patrol_jobs ORDER BY CASE name "
            "WHEN 'heartbeat' THEN 0 WHEN 'link_check' THEN 1 WHEN 'polish' THEN 2 "
            "WHEN 'daily_report' THEN 3 ELSE 4 END"
        )
        out = []
        for row in rows:
            info = await self.job_info(row["name"])
            if info:
                out.append(info)
        return out
