"""原生闲鱼通道：WebSocket 收发 + 订单同步 + 发布/下架/改价 + 会话映射。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from yuxiaoer.core import config
from yuxiaoer.seller.platform.channels import BaseChannel, ChannelError
from yuxiaoer.core.util import dumps, iso, loads, new_id
from .account_sync import AccountSyncService
from .mtop import MtopClient, new_device_id, parse_cookies
from .orders import OrderSyncService
from .publish import PublishError, publish as publish_native
from .session import fetch_im_token
from .ws import XianyuIM

log = logging.getLogger("yuxiaoer.xianyu.channel")


class NativeXianyuChannel(BaseChannel):
    name = "xianyu"
    label = "原生闲鱼协议"

    def __init__(self, db):
        self.db = db
        self.runtime: Any = None
        self.im: XianyuIM | None = None
        self.account: dict[str, Any] | None = None
        self.online = False
        self.detail = "未启动"
        self._sync_task: asyncio.Task | None = None
        self._connect_task: asyncio.Task | None = None
        self._running = False
        self._last_sync: dict[str, Any] = {}
        self._last_account_sync: dict[str, Any] = {}
        self._last_inbound_at: str | None = None

    def bind(self, runtime: Any) -> None:
        self.runtime = runtime

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._connect_task = asyncio.create_task(self._connect_active(), name="xianyu-native-connect")
        self._sync_task = asyncio.create_task(self._sync_loop(), name="xianyu-order-sync")
        self.detail = "正在连接"

    async def stop(self) -> None:
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sync_task = None
        if self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except (asyncio.CancelledError, Exception):
                pass
            self._connect_task = None
        if self.im:
            await self.im.stop()
            self.im = None
        self.online = False
        self.detail = "已停止"

    async def restart(self, account_id: str | None = None) -> None:
        if not self._running:
            return
        if self.im:
            await self.im.stop()
            self.im = None
        self._connect_task = asyncio.create_task(self._connect_active(), name="xianyu-native-reconnect")

    async def _active(self) -> dict[str, Any] | None:
        row = await self.db.fetchone(
            "SELECT * FROM accounts WHERE is_active=1 AND session_state IN ('authenticated','expiring') "
            "ORDER BY updated_at DESC LIMIT 1"
        )
        if not row:
            row = await self.db.fetchone(
                "SELECT * FROM accounts WHERE session_state IN ('authenticated','expiring') "
                "ORDER BY is_active DESC, updated_at DESC LIMIT 1"
            )
        if not row:
            return None
        account = dict(row)
        # 种子演示账号没有真实 Cookie，禁止拿 mock token 去打真实平台
        if "mock_" in str(account.get("cookies") or ""):
            return None
        return account

    async def _connect_active(self) -> None:
        try:
            account = await self._active()
            if not account or not account.get("cookies"):
                self.online = False
                self.detail = "没有已登录账号或 Cookie"
                return
            cookies = str(account.get("cookies") or "")
            token = str(account.get("access_token") or "")
            device_id = str(account.get("device_id") or "")
            if not device_id:
                device_id = new_device_id(str(parse_cookies(cookies).get("unb") or ""))
                await self.db.execute(
                    "UPDATE accounts SET device_id=?,updated_at=? WHERE id=?", (device_id, iso(), account["id"])
                )
            if not token:
                result = await fetch_im_token(cookies, device_id=device_id)
                token = result["token"]
                cookies = result["cookies"]
                device_id = result["device_id"]
                await self.db.execute(
                    """UPDATE accounts SET access_token=?,access_token_masked=?,device_id=?,cookies=?,
                       session_state='authenticated',status='online',last_refresh_at=?,updated_at=? WHERE id=?""",
                    (token, f"real_at_****{token[-4:]}", device_id, cookies, iso(), iso(), account["id"]),
                )
            self.account = {**account, "cookies": cookies, "access_token": token, "device_id": device_id}
            user_id = str(account.get("platform_user_id") or "").strip()
            if not user_id:
                user_id = str(parse_cookies(cookies).get("unb") or "")
            if not user_id:
                self.online = False
                self.detail = "Cookie 缺少 unb"
                return
            self.im = XianyuIM(
                cookies=cookies, token=token, user_id=user_id, device_id=device_id,
                on_message=self._on_message, on_state=self._on_state,
            )
            await self.im.start()
            self.detail = f"账号 {account.get('nickname') or user_id} 连接中"
            if self.runtime:
                asyncio.create_task(self._initial_account_sync(), name="xianyu-account-sync")
        except Exception as exc:
            self.online = False
            self.detail = f"连接失败：{str(exc)[:160]}"
            log.warning("native connect failed: %s", exc)

    async def _on_state(self, state: str) -> None:
        self.online = state == "connected"
        self.detail = {
            "connected": "WebSocket 已连接", "connecting": "正在连接",
            "disconnected": "WebSocket 已断开",
        }.get(state, state)
        if self.account:
            await self.db.execute(
                "UPDATE accounts SET ws_state=?,last_ws_at=?,updated_at=? WHERE id=?",
                (state, iso() if state == "connected" else None, iso(), self.account["id"]),
            )
        if self.runtime:
            await self.runtime.bus.emit("channel.ws_state", {
                "account_id": (self.account or {}).get("id"), "state": state,
            })

    async def _on_message(self, msg: dict[str, Any]) -> None:
        if not self.runtime:
            return
        if msg.get("kind") == "card_update":
            # 付款/退款卡片变化：立即拉一次订单，不进入自动回复
            asyncio.create_task(self.sync_orders())
            return
        text = str(msg.get("text") or "").strip()
        if not text:
            return
        platform_item_id = msg.get("item_id")
        item_id = None
        if platform_item_id:
            row = await self.db.fetchone(
                "SELECT id FROM items WHERE platform_item_id=? LIMIT 1", (str(platform_item_id),)
            )
            item_id = row["id"] if row else await self._ensure_item(str(platform_item_id))
        buyer_id = str(msg.get("buyer_id") or "").strip()
        if not buyer_id:
            return
        external_id = str(msg.get("external_id") or "").strip()
        if not external_id:
            external_id = "ws:" + hashlib.sha1(
                f"{msg.get('chat_id')}:{msg.get('timestamp')}:{text}".encode("utf-8")
            ).hexdigest()[:24]
        result = await self.runtime.ingest.submit_buyer_message(
            buyer_id=buyer_id, nick=str(msg.get("buyer_nick") or "闲鱼买家"),
            item_id=item_id, text=text, external_id=external_id,
            platform_chat_id=str(msg.get("chat_id") or ""),
        )
        if not result.get("duplicate"):
            self._last_inbound_at = iso()
            log.info("native inbound buyer=%s text=%s", buyer_id, text[:80])
        # 保存平台 chat_id，后续发消息用
        row = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (result["conversation_id"],))
        if row:
            meta = loads(row["meta_json"], {}) or {}
            meta.update({"platform_chat_id": msg.get("chat_id"), "platform_buyer_id": buyer_id, "source": "xianyu_ws"})
            await self.db.execute(
                "UPDATE conversations SET meta_json=?,updated_at=? WHERE id=?",
                (dumps(meta), iso(), row["id"]),
            )
        if any(k in text for k in ("已付款", "待发货", "已拍下", "退款申请")):
            asyncio.create_task(self.sync_orders())

    async def _ensure_item(self, platform_id: str) -> str:
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

    async def send_message(self, buyer_id: str, text: str, *, conversation_id: str, item_id: str | None = None) -> str:
        if not self.im or not self.im.connected:
            raise ChannelError("原生 WebSocket 未连接", retryable=True)
        conversation = await self.db.fetchone("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        conversation = dict(conversation) if conversation else None
        meta = loads(conversation["meta_json"], {}) if conversation else {}
        chat_id = str(meta.get("platform_chat_id") or "").replace("@goofish", "")
        raw_buyer = str(meta.get("platform_buyer_id") or buyer_id).replace("@goofish", "")
        if not chat_id:
            try:
                create_item = item_id or (conversation or {}).get("item_id")
                if create_item:
                    item_row = await self.db.fetchone("SELECT platform_item_id FROM items WHERE id=?", (create_item,))
                    if item_row and item_row["platform_item_id"]:
                        create_item = item_row["platform_item_id"]
                chat_id = await self.im.create_conversation(raw_buyer, create_item)
                if conversation:
                    meta["platform_chat_id"] = chat_id
                    meta["platform_buyer_id"] = raw_buyer
                    meta["source"] = "xianyu_ws"
                    await self.db.execute(
                        "UPDATE conversations SET meta_json=?,updated_at=? WHERE id=?",
                        (dumps(meta), iso(), conversation["id"]),
                    )
            except Exception:
                chat_id = raw_buyer
        try:
            return await self.im.send_text(chat_id, raw_buyer, text)
        except Exception as exc:
            raise ChannelError(f"原生消息发送失败：{str(exc)[:160]}", retryable=True) from exc

    async def health(self) -> dict[str, Any]:
        return {
            "online": bool(self.im and self.im.connected),
            "mode": self.name,
            "label": self.label,
            "detail": self.detail,
            "last_heartbeat_at": (self.im.last_heartbeat if self.im else None),
            "account_id": (self.account or {}).get("id"),
            "account_name": (self.account or {}).get("nickname"),
            "order_sync": self._last_sync,
            "account_sync": self._last_account_sync,
            "last_inbound_at": self._last_inbound_at,
        }

    async def sync_orders(self) -> dict[str, Any]:
        if not self.runtime or not self.account:
            return {"ok": False, "error": "原生通道未绑定账号"}
        result = await OrderSyncService(self.runtime).sync_account(self.account)
        self._last_sync = {**result, "at": iso()}
        return result

    async def sync_account(self) -> dict[str, Any]:
        if not self.runtime or not self.account:
            return {"ok": False, "error": "原生通道未绑定账号"}
        return await AccountSyncService(self.runtime).sync_account(self.account)

    async def sync_account_for(self, account_id: str) -> dict[str, Any]:
        if not self.runtime:
            return {"ok": False, "error": "runtime 未启动"}
        account = await self.runtime.accounts.get(account_id)
        if not account:
            return {"ok": False, "error": "账号不存在"}
        return await AccountSyncService(self.runtime).sync_account(account)

    async def _initial_account_sync(self) -> None:
        try:
            result = await self.sync_account()
            self._last_account_sync = {**result, "at": iso()}
            if self.runtime:
                await self.runtime.bus.emit("account.synced", result)
        except Exception as exc:
            log.warning("initial account sync failed: %s", str(exc)[:160])
            if self.runtime:
                await self.runtime.bus.emit("account.sync_failed", {"error": str(exc)[:200]})

    async def _sync_loop(self) -> None:
        await asyncio.sleep(3)
        while self._running:
            try:
                if self.account:
                    await self.sync_orders()
            except Exception as exc:
                log.warning("native order sync failed: %s", str(exc)[:160])
                self._last_sync = {"ok": False, "error": str(exc)[:160], "at": iso()}
            await asyncio.sleep(max(30, config.XY_ORDER_SYNC_SECONDS))

    # 原生发布/下架/改价
    async def publish_item(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self.account or not self.account.get("cookies"):
            raise ChannelError("没有已登录账号，无法发布")
        meta = loads(item.get("meta_json"), {}) or {}
        options = meta.get("publish") if isinstance(meta.get("publish"), dict) else {}
        if not options:
            raise ChannelError("商品缺少发布参数：图片、分类、所在地；请先在商品详情填写")
        client = MtopClient(self.account["cookies"], device_id=str(self.account.get("device_id") or ""))
        try:
            result = await publish_native(client, item, options)
        except PublishError as exc:
            raise ChannelError(str(exc)) from exc
        except Exception as exc:
            raise ChannelError(f"原生发布失败：{str(exc)[:200]}") from exc
        await self._save_cookies(client.cookies)
        return result

    async def offline_item(self, item: dict[str, Any]) -> None:
        if not self.account or not self.account.get("cookies"):
            raise ChannelError("没有已登录账号，无法下架")
        platform_id = str(item.get("platform_item_id") or "").strip()
        if not platform_id:
            raise ChannelError("商品没有平台商品 ID，无法下架")
        client = MtopClient(self.account["cookies"], device_id=str(self.account.get("device_id") or ""))
        try:
            data = await client.offline_items([platform_id])
            if isinstance(data, dict) and data.get("success") is False:
                raise ChannelError(str(data.get("message") or "平台拒绝下架"))
        except ChannelError:
            raise
        except Exception as exc:
            raise ChannelError(f"原生下架失败：{str(exc)[:200]}") from exc
        await self._save_cookies(client.cookies)

    async def change_price(self, item: dict[str, Any], price_cents: int) -> None:
        if not self.account or not self.account.get("cookies"):
            raise ChannelError("没有已登录账号，无法改价")
        platform_id = str(item.get("platform_item_id") or "").strip()
        if not platform_id:
            raise ChannelError("商品没有平台商品 ID，无法改价")
        if price_cents <= 0:
            raise ChannelError("改价必须大于 0")
        client = MtopClient(self.account["cookies"], device_id=str(self.account.get("device_id") or ""))
        try:
            data = await client.update_price(
                platform_id, round(price_cents / 100, 2), int(item.get("stock") or 1),
            )
            if isinstance(data, dict) and data.get("success") is False:
                raise ChannelError(str(data.get("message") or "平台拒绝改价"))
        except ChannelError:
            raise
        except Exception as exc:
            raise ChannelError(f"原生改价失败：{str(exc)[:200]}") from exc
        await self._save_cookies(client.cookies)

    async def _save_cookies(self, cookies: str) -> None:
        if self.account and cookies and cookies != self.account.get("cookies"):
            await self.db.execute(
                "UPDATE accounts SET cookies=?,updated_at=? WHERE id=?",
                (cookies, iso(), self.account["id"]),
            )
            self.account["cookies"] = cookies

    async def recommend_category(self, title: str, description: str) -> list[dict[str, Any]]:
        if not self.account or not self.account.get("cookies"):
            raise ChannelError("没有已登录账号，无法推荐分类")
        client = MtopClient(self.account["cookies"], device_id=str(self.account.get("device_id") or ""))
        try:
            rows = await client.recommend_category(title, description, str(self.account.get("id") or ""))
        except Exception as exc:
            raise ChannelError(f"分类推荐失败：{str(exc)[:200]}") from exc
        await self._save_cookies(client.cookies)
        return rows

    async def polish_items(self, items: list[dict[str, Any]]) -> int:
        if not items:
            return 0
        if not self.account or not self.account.get("cookies"):
            return 0
        client = MtopClient(self.account["cookies"], device_id=str(self.account.get("device_id") or ""))
        count = 0
        for item in items:
            platform_id = str(item.get("platform_item_id") or "").strip()
            if not platform_id:
                continue
            await client.polish_item(platform_id)
            count += 1
        if client.cookies != self.account.get("cookies"):
            await self.db.execute(
                "UPDATE accounts SET cookies=?,updated_at=? WHERE id=?",
                (client.cookies, iso(), self.account["id"]),
            )
            self.account["cookies"] = client.cookies
        return count

    async def relist_item(self, item: dict[str, Any]) -> None:
        raise ChannelError("原生重新上架尚未联调，请先在闲鱼手动上架")

    def stats(self) -> dict[str, Any]:
        return {
            "mode": self.name, "label": self.label,
            "online": bool(self.im and self.im.connected),
            "account": (self.account or {}).get("nickname"),
        }
