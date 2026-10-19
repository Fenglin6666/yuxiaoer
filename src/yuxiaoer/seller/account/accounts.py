"""多账号登录 / 会话保活。

生命周期：
    logged_out → qr_pending → scanned → authenticated → expiring → expired
                                  ↑                    │
                                  └── refresh ─────────┘

刷新纪律参考社区实践（只实现事实与节奏，不复制源码）：
- Cookie / hasLogin 心跳约 30 分钟；
- _m_h5_tk 约 1.5–2.5h 随机刷新；
- websocket_token 约 10–14h 随机刷新；
- 多账号刷新之间随机错开 2–5s；
- 所有时间带抖动，绝不整点齐发。
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta
from typing import Any

from yuxiaoer.core import config
from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.util import dumps, human_time, iso, loads, new_id, now_utc, parse_iso
from yuxiaoer.seller.notifications.alerts import AlertService

log = logging.getLogger("yuxiaoer.accounts")

STATES = {"logged_out", "qr_pending", "scanned", "authenticated", "expiring", "expired"}


def _mask(value: str) -> str:
    return value


class AccountService:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        alerts: AlertService,
        settings: SettingsService,
    ):
        self.db = db
        self.bus = bus
        self.alerts = alerts
        self.settings = settings
        self.native = False
        self.qr_manager: Any = None
        self.on_session_refreshed: Any = None
        self._applied_qr: set[str] = set()

    async def list(self) -> list[dict[str, Any]]:
        rows = await self.db.fetchall("SELECT * FROM accounts ORDER BY is_active DESC, updated_at DESC")
        return [await self._decorate(dict(r)) for r in rows]

    async def get(self, account_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchone("SELECT * FROM accounts WHERE id=?", (account_id,))
        return await self._decorate(dict(row)) if row else None

    async def _decorate(self, account: dict[str, Any]) -> dict[str, Any]:
        policy = loads(account.get("refresh_policy_json"), {}) or {}
        account["policy"] = policy
        account["state_label"] = {
            "logged_out": "未登录", "qr_pending": "待扫码", "scanned": "已扫码待确认",
            "authenticated": "已登录", "expiring": "即将过期", "expired": "已过期",
        }.get(account.get("session_state"), account.get("session_state"))
        next_times = []
        for key in ("access_expires_at", "h5_token_expires_at", "ws_token_expires_at"):
            value = account.get(key)
            if value:
                next_times.append(value)
        account["next_refresh_at"] = min(next_times) if next_times else None
        account["next_refresh_human"] = human_time(account["next_refresh_at"]) if next_times else "—"
        account["access_expires_human"] = human_time(account.get("access_expires_at"))
        account["refresh_expires_human"] = human_time(account.get("refresh_expires_at"))
        account["ws_expires_human"] = human_time(account.get("ws_token_expires_at"))
        account["h5_expires_human"] = human_time(account.get("h5_token_expires_at"))
        account["last_refresh_human"] = human_time(account.get("last_refresh_at")) if account.get("last_refresh_at") else ""
        account["last_heartbeat_human"] = human_time(account.get("last_heartbeat_at")) if account.get("last_heartbeat_at") else ""
        account["cookie_updated_human"] = human_time(account.get("cookie_updated_at")) if account.get("cookie_updated_at") else ""
        account["has_cookie"] = bool(account.get("cookies"))
        account["ws_state"] = account.get("ws_state") or "disconnected"
        account["platform_user_id"] = account.get("platform_user_id") or account.get("id")
        account["is_active"] = bool(account.get("is_active"))
        return account

    async def _event(self, account_id: str, event: str, detail: dict[str, Any] | None = None) -> None:
        await self.db.execute(
            "INSERT INTO account_events(account_id,event,detail_json,created_at) VALUES(?,?,?,?)",
            (account_id, event, dumps(detail or {}), iso()),
        )
        await self.bus.emit("account.event", {"account_id": account_id, "event": event, **(detail or {})})

    async def create(self, nickname: str, platform: str = "xianyu") -> dict[str, Any]:
        account_id = new_id("acc")
        now = iso()
        policy = dumps({
            "h5_refresh_hours": list(config.SESSION_H5_REFRESH_HOURS),
            "ws_refresh_hours": list(config.SESSION_WS_REFRESH_HOURS),
            "cookie_check_minutes": config.SESSION_COOKIE_CHECK_MINUTES,
            "stagger_seconds": list(config.SESSION_ACCOUNT_STAGGER_SECONDS),
        })
        await self.db.execute(
            """INSERT INTO accounts(id,nickname,platform,status,updated_at,session_state,
               is_active,refresh_policy_json,detail)
               VALUES(?,?,?,?,?,?,0,?,?)""",
            (account_id, nickname.strip()[:40] or "新账号", platform, "offline", now,
             "logged_out", policy, "未登录"),
        )
        await self._event(account_id, "created", {"nickname": nickname})
        return await self.get(account_id) or {}

    async def start_login(self, account_id: str) -> dict[str, Any]:
        account = await self.get(account_id)
        if not account:
            raise KeyError("账号不存在")
        if not self.qr_manager:
            raise ValueError("真实扫码模块未初始化")
        result = await self.qr_manager.start()
        now = now_utc()
        await self.db.execute(
            """UPDATE accounts SET session_state='qr_pending',qr_session_id=?,qr_expires_at=?,
               updated_at=?,detail='等待扫码（真实 passport 流程）' WHERE id=?""",
            (result["session_id"], iso(now + timedelta(seconds=config.SESSION_QR_TTL_SECONDS)),
             iso(now), account_id),
        )
        await self._event(account_id, "login_start", {"channel": "passport", "qr_ttl_seconds": 300})
        return {
            "account_id": account_id,
            "qr_session_id": result["session_id"],
            "qr_code_url": result.get("qr_code_url"),
            "mode": "native",
            "expires_at": iso(now + timedelta(seconds=300)),
            "expires_in": 300,
        }

    async def login_status(self, account_id: str) -> dict[str, Any]:
        account = await self.get(account_id)
        if not account:
            raise KeyError("账号不存在")
        if not self.qr_manager or not account.get("qr_session_id"):
            return {
                "account_id": account_id, "session_id": account.get("qr_session_id"),
                "status": account.get("session_state"), "mode": "native",
            }
        data = await self.qr_manager.status(account["qr_session_id"])
        if data.get("status") == "success" and account["qr_session_id"] not in self._applied_qr:
            cookies = str(data.get("cookies") or "")
            unb = str(data.get("unb") or "")
            try:
                from yuxiaoer.seller.platform.xianyu.session import fetch_im_token
                token = await fetch_im_token(cookies, device_id=str(account.get("device_id") or ""))
                cookies = token["cookies"]
                now = now_utc()
                await self.db.execute(
                    """UPDATE accounts SET session_state='authenticated',status='online',is_active=1,
                       cookies=?,cookie_updated_at=?,platform_user_id=?,access_token=?,access_token_masked=?,
                       device_id=?,access_expires_at=?,refresh_expires_at=?,ws_token_expires_at=?,
                       h5_token_expires_at=?,last_refresh_at=?,last_heartbeat_at=?,qr_session_id=NULL,
                       qr_expires_at=NULL,detail='扫码登录成功（原生）',updated_at=? WHERE id=?""",
                    (
                        cookies, iso(now), unb or account.get("platform_user_id"),
                        token["token"], f"real_at_****{token['token'][-4:]}",
                        token["device_id"], iso(now + timedelta(hours=24)),
                        iso(now + timedelta(days=7)),
                        iso(now + timedelta(hours=random.uniform(*config.SESSION_WS_REFRESH_HOURS))),
                        iso(now + timedelta(hours=random.uniform(*config.SESSION_H5_REFRESH_HOURS))),
                        iso(now), iso(now), iso(now), account_id,
                    ),
                )
                await self._set_only_active(account_id)
                self._applied_qr.add(account["qr_session_id"])
                await self._event(account_id, "login_success", {"channel": "passport", "unb": unb, "active": True})
                if self.on_session_refreshed:
                    await self.on_session_refreshed(account_id)
                data["account"] = await self.get(account_id)
            except Exception as exc:
                await self.db.execute(
                    "UPDATE accounts SET session_state='expired',status='offline',detail=?,updated_at=? WHERE id=?",
                    (f"扫码成功但取 Token 失败：{str(exc)[:120]}", iso(), account_id),
                )
                await self._event(account_id, "refresh_failed", {"reason": "qr_token_failed", "error": str(exc)[:160]})
                await self.alerts.create(
                    "P0", "session_expired", f"扫码后取 Token 失败：{account['nickname']}",
                    str(exc)[:300], dedupe_minutes=10,
                )
                data["status"] = "failed"
                data["message"] = str(exc)[:200]
        return data

    async def refresh(self, account_id: str, *, kind: str = "manual") -> dict[str, Any]:
        account = await self.get(account_id)
        if not account:
            raise KeyError("账号不存在")
        if account["session_state"] in ("logged_out", "qr_pending", "expired"):
            raise ValueError("账号未登录")
        if not account.get("cookies"):
            raise ValueError("账号没有 Cookie，请重新扫码登录")
        return await self._refresh_native(account, kind=kind)

    async def _refresh_native(self, account: dict[str, Any], *, kind: str = "manual") -> dict[str, Any]:
        from yuxiaoer.seller.platform.xianyu.session import (
            fetch_im_token,
            renew_cookies,
        )

        now = now_utc()
        try:
            renewed = await renew_cookies(str(account.get("cookies") or ""))
            cookies = renewed["cookies"]
            token = await fetch_im_token(cookies, device_id=str(account.get("device_id") or ""))
            cookies = token["cookies"]
            access = token["token"]
            await self.db.execute(
                """UPDATE accounts SET session_state='authenticated',status='online',cookies=?,cookie_updated_at=?,
                   access_token=?,access_token_masked=?,device_id=?,access_expires_at=?,ws_token_expires_at=?,
                   h5_token_expires_at=?,refresh_expires_at=?,last_refresh_at=?,last_heartbeat_at=?,
                   detail=?,updated_at=? WHERE id=?""",
                (
                    cookies, iso(now), access, f"real_at_****{access[-4:]}", token["device_id"],
                    iso(now + timedelta(hours=24)),
                    iso(now + timedelta(hours=random.uniform(*config.SESSION_WS_REFRESH_HOURS))),
                    iso(now + timedelta(hours=random.uniform(*config.SESSION_H5_REFRESH_HOURS))),
                    iso(now + timedelta(days=7)), iso(now), iso(now),
                    f"原生刷新完成（{kind}）", iso(now), account["id"],
                ),
            )
            await self._event(account["id"], "token_refresh", {
                "kind": kind, "channel": "native",
                "cookie_changed": bool(renewed.get("changed")),
            })
            if self.on_session_refreshed:
                await self.on_session_refreshed(account["id"])
            return await self.get(account["id"]) or {}
        except Exception as exc:
            await self.db.execute(
                "UPDATE accounts SET session_state='expired',status='offline',detail=?,updated_at=? WHERE id=?",
                (f"原生刷新失败：{str(exc)[:120]}", iso(now), account["id"]),
            )
            await self._event(account["id"], "refresh_failed", {"reason": "native_refresh_failed", "error": str(exc)[:180]})
            await self.alerts.create(
                "P0", "session_refresh_failed", f"账号刷新失败：{account['nickname']}",
                str(exc)[:300], dedupe_minutes=30,
            )
            return await self.get(account["id"]) or {}

    async def logout(self, account_id: str) -> dict[str, Any]:
        account = await self.get(account_id)
        if not account:
            raise KeyError("账号不存在")
        was_active = bool(account.get("is_active"))
        await self.db.execute(
            """UPDATE accounts SET session_state='logged_out',status='offline',is_active=0,
               access_token=NULL,access_token_masked=NULL,access_expires_at=NULL,refresh_expires_at=NULL,
               ws_token_expires_at=NULL,h5_token_expires_at=NULL,qr_session_id=NULL,cookies=NULL,
               qr_expires_at=NULL,detail='已退出登录',updated_at=? WHERE id=?""",
            (iso(), account_id),
        )
        await self._event(account_id, "logout", {"was_active": was_active})
        if was_active:
            # 自动激活另一个已登录账号，保持单店主多账号可用
            row = await self.db.fetchone(
                "SELECT id FROM accounts WHERE session_state IN ('authenticated','expiring') AND id!=? LIMIT 1",
                (account_id,),
            )
            if row:
                await self.activate(row["id"])
        if self.on_session_refreshed:
            await self.on_session_refreshed(account_id)
        return await self.get(account_id) or {}

    async def activate(self, account_id: str) -> dict[str, Any]:
        account = await self.get(account_id)
        if not account:
            raise KeyError("账号不存在")
        if account["session_state"] not in ("authenticated", "expiring"):
            raise ValueError("只有已登录账号可以设为当前账号")
        await self._set_only_active(account_id)
        await self._event(account_id, "activate", {})
        if self.on_session_refreshed:
            await self.on_session_refreshed(account_id)
        return await self.get(account_id) or {}

    async def _set_only_active(self, account_id: str) -> None:
        await self.db.execute("UPDATE accounts SET is_active=0 WHERE id!=?", (account_id,))
        await self.db.execute("UPDATE accounts SET is_active=1,updated_at=? WHERE id=?", (iso(), account_id))

    async def events(self, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT * FROM account_events WHERE account_id=? ORDER BY id DESC LIMIT ?",
            (account_id, limit),
        )
        out = []
        for row in rows:
            data = dict(row)
            data["detail"] = loads(data.get("detail_json"), {})
            data["when"] = human_time(data.get("created_at"))
            out.append(data)
        return out

    async def due_refresh(self, account: dict[str, Any]) -> list[str]:
        now = now_utc()
        due: list[str] = []
        access = account.get("access_expires_at")
        h5 = account.get("h5_token_expires_at")
        ws = account.get("ws_token_expires_at")
        if access and parse_iso(access) <= now:
            due.append("access")
        if h5 and parse_iso(h5) <= now:
            due.append("h5")
        if ws and parse_iso(ws) <= now:
            due.append("ws")
        return due


class SessionKeeper:
    """后台会话保活：token 刷新 + 心跳 + 多账号错开。"""

    def __init__(self, accounts: AccountService, alerts: AlertService):
        self.accounts = accounts
        self.alerts = alerts
        self.worker: asyncio.Task | None = None
        self.running = False
        self.last_tick_at: str | None = None
        self.last_tick_summary: dict[str, Any] = {}
        self.ticks = 0

    async def start(self) -> None:
        if self.worker is None:
            self.running = True
            self.worker = asyncio.create_task(self._loop(), name="session-keeper")

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
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("session keeper tick failed")
            await asyncio.sleep(15)

    async def tick(self) -> dict[str, Any]:
        self.last_tick_at = iso()
        self.ticks += 1
        rows = await self.accounts.db.fetchall(
            "SELECT * FROM accounts WHERE session_state IN ('authenticated','expiring') ORDER BY is_active DESC"
        )
        refreshed: list[str] = []
        expired: list[str] = []
        for idx, row in enumerate(rows):
            account = dict(row)
            now = now_utc()
            last_hb = account.get("last_heartbeat_at")
            if not last_hb or parse_iso(last_hb) <= now - timedelta(minutes=config.SESSION_COOKIE_CHECK_MINUTES):
                await self.accounts.db.execute(
                    "UPDATE accounts SET last_heartbeat_at=?,status='online',updated_at=? WHERE id=?",
                    (iso(now), iso(now), account["id"]),
                )
            due = await self.accounts.due_refresh(account)
            if not due:
                continue
            if len(rows) > 1 and idx:
                # 多账号错开，避免同一时刻打平台
                await asyncio.sleep(random.uniform(*config.SESSION_ACCOUNT_STAGGER_SECONDS))
            try:
                await self.accounts.refresh(account["id"], kind="auto")
                refreshed.append(account["nickname"])
            except Exception as exc:  # noqa: BLE001
                expired.append(account["nickname"])
                await self.alerts.create(
                    "P0", "session_refresh_failed", f"会话刷新失败：{account['nickname']}",
                    str(exc)[:200], dedupe_minutes=30,
                )
        self.last_tick_summary = {"refreshed": refreshed, "failed": expired, "checked": len(rows)}
        return {**self.last_tick_summary, "at": human_time(self.last_tick_at)}

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "last_tick_at": self.last_tick_at,
            "last_tick_human": human_time(self.last_tick_at) if self.last_tick_at else "—",
            "ticks": self.ticks,
            "last_summary": self.last_tick_summary,
            "h5_refresh_hours": list(config.SESSION_H5_REFRESH_HOURS),
            "ws_refresh_hours": list(config.SESSION_WS_REFRESH_HOURS),
            "cookie_check_minutes": config.SESSION_COOKIE_CHECK_MINUTES,
            "stagger_seconds": list(config.SESSION_ACCOUNT_STAGGER_SECONDS),
        }
