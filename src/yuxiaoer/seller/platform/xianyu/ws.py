"""原生闲鱼 IM WebSocket。

协议事实来自公开抓包与社区实现：
- wss://wss-goofish.dingtalk.com/
- /reg 认证帧 + /r/SyncStatus/ackDiff 同步帧
- 15s 心跳 `/!`
- 入站 base64 → JSON / MessagePack；出站 `/r/MessageSend/sendByReceiverScope`
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Awaitable, Callable

import msgpack
import websockets

from yuxiaoer.core import config
from .mtop import generate_mid, generate_uuid

log = logging.getLogger("yuxiaoer.xianyu.ws")

IM_APP_KEY = "444e9908a51d1cb236a27862abc769c9"
IM_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36 "
    "DingTalk(2.1.5) OS(Windows/10) "
    "Browser(Chrome/146.0.0.0) DingWeb/2.1.5 "
    "IMPaaS DingWeb/2.1.5"
)


def _decode_data(raw: Any) -> Any:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).decode("utf-8", errors="ignore")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith(("{", "[")):
        try:
            return json.loads(text)
        except Exception:
            pass
    try:
        text = base64.b64decode(raw).decode("utf-8")
        return json.loads(text)
    except Exception:
        try:
            return msgpack.unpackb(base64.b64decode(raw), raw=False)
        except Exception:
            return None


def _load_content(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.startswith(("{", "[")):
        try:
            return json.loads(text)
        except Exception:
            pass
    try:
        return json.loads(base64.b64decode(text).decode("utf-8"))
    except Exception:
        return None


def _content_text(content: Any) -> str:
    """兼容明文 JSON、base64 JSON、文本/图片/语音内容。"""
    decoded = _load_content(content)
    if isinstance(decoded, dict):
        content_type = decoded.get("contentType")
        if content_type == 2 or "image" in decoded:
            return "[图片]"
        if content_type == 3 or "audio" in decoded:
            return "[语音消息]"
        text = decoded.get("text")
        if isinstance(text, dict):
            return str(text.get("text") or "")
        if isinstance(text, str):
            return text
        if decoded.get("picUrl"):
            return "[图片]"
        return ""
    if isinstance(content, str):
        return content
    return ""


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        decoded = _load_content(content)
        if decoded is None:
            return content if not content.strip().startswith("{") else ""
        content = decoded
    if not isinstance(content, dict):
        return ""
    if isinstance(content.get("text"), (dict, str)):
        return _content_text(content)
    if isinstance(content.get("dxCard"), dict):
        card = content["dxCard"]
        main = card.get("item", {}).get("main", {}) if isinstance(card.get("item"), dict) else {}
        title = main.get("exContent", {}).get("title") if isinstance(main.get("exContent"), dict) else ""
        return str(title or "")
    if content.get("2"):
        return str(content["2"])
    return ""


def _extract_item_id(content: Any, info: dict[str, Any]) -> str | None:
    try:
        ext = info.get("extJson")
        if isinstance(ext, str):
            parsed = json.loads(ext)
            if isinstance(parsed, dict):
                for key in ("itemId", "item_id"):
                    if parsed.get(key):
                        return str(parsed[key])
    except Exception:
        pass
    if isinstance(content, dict):
        card = content.get("dxCard")
        if isinstance(card, dict):
            main = card.get("item", {}).get("main", {})
            if isinstance(main, dict):
                for key in ("itemId", "id"):
                    if main.get(key):
                        return str(main[key])
            raw = json.dumps(card, ensure_ascii=False)
            for token in ("item?id=", "itemId=", "itemId%22%3A%22"):
                if token in raw:
                    tail = raw.split(token, 1)[1]
                    return tail.split("&", 1)[0].split('"', 1)[0][:32]
    return None


def _iter_messages(payload: dict[str, Any]):
    """把 LWP 业务包归一化为内部消息；一帧可包含多条。"""
    body = payload.get("body")
    packets: list[Any] = []
    if isinstance(body, dict) and isinstance(body.get("syncPushPackage"), dict):
        packets = body["syncPushPackage"].get("data") or []
        if isinstance(packets, dict):
            packets = [packets]
    elif isinstance(body, dict):
        packets = [body]
    elif isinstance(body, list):
        packets = body
    for packet in packets:
        raw = packet.get("data") if isinstance(packet, dict) else packet
        obj = _decode_data(raw)
        if not isinstance(obj, dict):
            continue
        one = obj.get("1")
        two = obj.get("2")
        info = obj.get("10")
        kind = "chat"
        if isinstance(one, str) and one.strip().startswith("{"):
            try:
                one = json.loads(one)
            except Exception:
                pass
        if isinstance(one, dict):
            chat_id = one.get("2")
            ts = one.get("5")
            info = one.get("10") if isinstance(one.get("10"), dict) else {}
            six = one.get("6")
            content = six.get("3", {}) if isinstance(six, dict) else {}
            if not isinstance(content, dict):
                content = {}
            text = _extract_text(content.get("5"))
            if not text and content.get("1"):
                text = _extract_text(content.get("1"))
            item_id = _extract_item_id(content.get("5"), info)
            if not text:
                text = str(info.get("reminderContent") or "")
        elif isinstance(one, str):
            kind = "card_update"
            chat_id = two
            ts = obj.get("5")
            info = obj.get("4") if isinstance(obj.get("4"), dict) else {}
            content = {}
            text = str(info.get("reminderContent") or "")
            item_id = _extract_item_id({}, info)
        else:
            continue
        ext_json = info.get("extJson") if isinstance(info, dict) else None
        if isinstance(ext_json, str):
            try:
                ext = json.loads(ext_json)
                if isinstance(ext, dict) and ext.get("msgArg1") == "MsgTips":
                    continue
                message_id = ext.get("messageId") if isinstance(ext, dict) else None
            except Exception:
                message_id = None
        else:
            message_id = None
        if not message_id and isinstance(info, dict):
            message_id = info.get("bizTag")
        if not chat_id:
            continue
        chat_id = str(chat_id).replace("@goofish", "")
        buyer_id = str(info.get("senderUserId") or "") if isinstance(info, dict) else ""
        nick = str(info.get("senderNick") or "闲鱼买家") if isinstance(info, dict) else "闲鱼买家"
        if not buyer_id:
            continue
        yield {
            "kind": kind,
            "chat_id": chat_id,
            "buyer_id": buyer_id.replace("@goofish", ""),
            "buyer_nick": nick,
            "text": text.strip(),
            "item_id": item_id,
            "external_id": str(message_id or ""),
            "timestamp": ts,
            "raw": obj,
        }


def normalize_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(_iter_messages(payload))


def normalize_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    """兼容旧调用：只取第一条。"""
    for message in _iter_messages(payload):
        return message
    return None


class XianyuIM:
    def __init__(
        self,
        *,
        cookies: str,
        token: str,
        user_id: str,
        device_id: str = "",
        on_message: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_state: Callable[[str], Any] | None = None,
    ):
        self.cookies = cookies or ""
        self.token = token or ""
        self.user_id = (user_id or "").replace("@goofish", "")
        self.device_id = device_id or ""
        self.on_message = on_message
        self.on_state = on_state
        self.ws: Any = None
        self.running = False
        self.connected = False
        self.last_heartbeat: str | None = None
        self._task: asyncio.Task | None = None
        self._hb_task: asyncio.Task | None = None
        self._history_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._send_lock = asyncio.Lock()
        self._history_lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._raw_seen = 0
        self.registered = False

    def _state(self, state: str) -> None:
        if not self.on_state:
            return
        try:
            result = self.on_state(state)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        except Exception:
            log.exception("ws state callback failed")

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name=f"xianyu-ws:{self.user_id}")
        self._history_task = asyncio.create_task(self._history_loop(), name=f"xianyu-history:{self.user_id}")

    async def stop(self) -> None:
        self.running = False
        self._stop.set()
        if self._hb_task:
            self._hb_task.cancel()
        if self._history_task:
            self._history_task.cancel()
            try:
                await self._history_task
            except (asyncio.CancelledError, Exception):
                pass
            self._history_task = None
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        self.connected = False
        self._state("disconnected")

    async def _history_loop(self) -> None:
        """推送不可靠时的兜底：轮询最近会话/消息，交给同一条入站链路。"""
        await asyncio.sleep(4)
        cutoff = int(time.time() * 1000) - 10 * 60 * 1000
        while self.running and not self._stop.is_set():
            if self.connected and self.on_message:
                try:
                    await self._poll_history(cutoff)
                    cutoff = int(time.time() * 1000) - 5 * 60 * 1000
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    log.warning("xianyu history poll failed: %s", str(exc)[:160])
            await asyncio.sleep(7)

    async def get_conversations(self, limit: int = 20) -> dict[str, Any]:
        response = await self.request_lwp(
            "/r/Conversation/listNewestPagination",
            [9007199254740991, limit], timeout=15,
        )
        return response.get("body") if isinstance(response, dict) else {}

    async def get_messages(self, cid: str, limit: int = 20) -> dict[str, Any]:
        full_cid = cid if cid.endswith("@goofish") else f"{cid}@goofish"
        response = await self.request_lwp(
            "/r/MessageManager/listUserMessages",
            [full_cid, False, 9007199254740991, limit, False], timeout=15,
        )
        return response.get("body") if isinstance(response, dict) else {}

    async def _poll_history(self, cutoff: int) -> None:
        # 推送解析失败时也会触发一次立即补偿；并发轮询直接跳过，避免打爆 IM 接口。
        if self._history_lock.locked():
            return
        async with self._history_lock:
            await self._poll_history_locked(cutoff)

    async def _poll_history_locked(self, cutoff: int) -> None:
        body = await self.get_conversations()
        if not isinstance(body, dict):
            return
        convs = body.get("userConvs") or []
        if convs:
            log.debug("xianyu history poll: %s conversations", len(convs))
        polled = 0
        for item in convs[:20]:
            if not isinstance(item, dict):
                continue
            conv = item.get("singleChatUserConversation") if isinstance(item.get("singleChatUserConversation"), dict) else item
            inner = conv.get("singleChatConversation") if isinstance(conv.get("singleChatConversation"), dict) else {}
            cid = str(inner.get("cid") or conv.get("cid") or "").replace("@goofish", "")
            if not cid:
                continue
            unread = int(conv.get("redPoint") or conv.get("unreadCount") or 0)
            modify = int(conv.get("modifyTime") or 0)
            if 0 < modify < 10_000_000_000:
                modify *= 1000
            if unread <= 0 and (not modify or modify < cutoff):
                continue
            messages = await self.get_messages(cid)
            polled += 1
            models = messages.get("userMessageModels") if isinstance(messages, dict) else []
            if isinstance(models, str):
                try:
                    models = json.loads(models)
                except Exception:
                    models = []
            extension = inner.get("extension") if isinstance(inner.get("extension"), dict) else {}
            if isinstance(inner.get("extension"), str):
                try:
                    parsed_extension = json.loads(inner["extension"])
                    if isinstance(parsed_extension, dict):
                        extension = parsed_extension
                except Exception:
                    pass
            for model in models if isinstance(models, list) else []:
                msg = self._history_message(model, cid, extension)
                if not msg:
                    continue
                ts = int(msg.pop("_ts", 0) or 0)
                if ts and ts < cutoff:
                    continue
                try:
                    await self.on_message(msg)
                except Exception:
                    log.exception("xianyu history message failed")
            if polled >= 8:
                break

    def _history_message(self, model: Any, cid: str, conv_extension: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(model, dict):
            return None
        message = model.get("message") if isinstance(model.get("message"), dict) else model
        extension = message.get("extension") if isinstance(message.get("extension"), dict) else {}
        if isinstance(message.get("extension"), str):
            try:
                parsed_extension = json.loads(message["extension"])
                if isinstance(parsed_extension, dict):
                    extension = parsed_extension
            except Exception:
                pass
        sender = str(extension.get("senderUserId") or extension.get("senderId") or "").replace("@goofish", "")
        if not sender or sender == self.user_id:
            return None
        custom = ((message.get("content") or {}).get("custom") or {}) if isinstance(message.get("content"), dict) else {}
        text = _content_text(custom.get("data")) or str(custom.get("summary") or custom.get("degrade") or "")
        text = text.strip()
        if not text:
            return None
        created = int(message.get("createAt") or message.get("createTime") or message.get("time") or 0)
        if 0 < created < 10_000_000_000:
            created *= 1000
        message_id = str(message.get("messageId") or extension.get("messageId") or "")
        if not message_id:
            message_id = f"hist:{cid}:{created}:{sender}"
        item_extension = extension
        item_id = str(item_extension.get("itemId") or conv_extension.get("itemId") or "")
        return {
            "kind": "chat",
            "chat_id": cid,
            "buyer_id": sender,
            "buyer_nick": str(extension.get("reminderTitle") or extension.get("senderNick") or "闲鱼买家"),
            "text": text,
            "item_id": item_id or None,
            "external_id": message_id,
            "timestamp": created,
            "raw": model,
            "_ts": created,
        }

    async def _run(self) -> None:
        backoff = 2
        while self.running and not self._stop.is_set():
            try:
                self._state("connecting")
                async with websockets.connect(
                    config.XY_WS_URL,
                    additional_headers={
                        "Cookie": self.cookies,
                        "Origin": "https://www.goofish.com",
                        "User-Agent": IM_UA,
                        "Pragma": "no-cache",
                        "Cache-Control": "no-cache",
                        "Accept-Language": "zh-CN,zh;q=0.9",
                    },
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=15,
                    max_size=8 * 1024 * 1024,
                ) as ws:
                    self.ws = ws
                    self.connected = True
                    self._state("connected")
                    await self._register(ws)
                    backoff = 2
                    self._hb_task = asyncio.create_task(self._heartbeat(), name="xianyu-heartbeat")
                    async for raw in ws:
                        await self._on_raw(raw)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("xianyu ws disconnected: %s", str(exc)[:180])
            finally:
                self.connected = False
                self.ws = None
                if self._hb_task:
                    self._hb_task.cancel()
                    self._hb_task = None
                self._state("disconnected")
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(RuntimeError("WebSocket 已断开"))
                self._pending.clear()
            if not self.running:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        if not self.ws:
            raise RuntimeError("WebSocket 未连接")
        async with self._send_lock:
            await self.ws.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    async def _register(self, ws: Any) -> None:
        reg_mid = generate_mid()
        frame = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": IM_APP_KEY,
                "token": self.token,
                "ua": IM_UA,
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": reg_mid,
            },
        }
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[reg_mid] = fut
        try:
            await self._send_json(frame)
            try:
                reg_response = await asyncio.wait_for(fut, timeout=5)
                code = reg_response.get("code", 0) if isinstance(reg_response, dict) else 0
                log.info("xianyu IM registered: code=%s", code)
            except asyncio.TimeoutError:
                if self.registered:
                    log.info("xianyu IM registered (server sid accepted)")
                else:
                    log.info("xianyu IM registration sent (no mid echo)")
        finally:
            self._pending.pop(reg_mid, None)
        await asyncio.sleep(1)
        now = int(time.time() * 1000)
        await self._send_json({
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [{
                "pipeline": "sync", "tooLong2Tag": "PNM,1", "channel": "sync",
                "topic": "sync", "highPts": 0, "pts": now * 1000, "seq": 0,
                "timestamp": now,
            }],
        })

    async def _heartbeat(self) -> None:
        failures = 0
        while self.running and self.connected and self.ws:
            try:
                await asyncio.wait_for(
                    self._send_json({"lwp": "/!", "headers": {"mid": generate_mid()}}),
                    timeout=2.0,
                )
                failures = 0
                self.last_heartbeat = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            except Exception:
                failures += 1
                if failures >= 3:
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                    return
            await asyncio.sleep(15)

    async def _on_raw(self, raw: Any) -> None:
        self._raw_seen += 1
        if self._raw_seen <= 8:
            log.debug("xianyu ws raw #%s type=%s %s", self._raw_seen, type(raw).__name__, str(raw)[:500])
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw).decode("utf-8", errors="ignore")
        try:
            payload = json.loads(raw)
        except Exception:
            return
        headers = payload.get("headers") if isinstance(payload, dict) else None
        mid = str(headers.get("mid") or "") if isinstance(headers, dict) else ""
        if isinstance(headers, dict) and headers.get("reg-uid"):
            self.registered = True
        if mid and mid in self._pending:
            fut = self._pending.pop(mid)
            if not fut.done():
                fut.set_result(payload)
            return
        # 入站消息 ACK（不回 ACK 服务端可能断连）
        if isinstance(payload, dict) and "body" in payload and headers:
            ack = {
                "code": 200,
                "headers": {
                    "mid": headers.get("mid") or generate_mid(),
                    "sid": headers.get("sid") or "",
                },
            }
            for key in ("app-key", "ua", "dt"):
                if headers.get(key):
                    ack["headers"][key] = headers[key]
            try:
                await self._send_json(ack)
            except Exception:
                pass
        messages = normalize_messages(payload)
        body = payload.get("body") if isinstance(payload, dict) else None
        if isinstance(body, dict) and isinstance(body.get("syncPushPackage"), dict):
            data = body["syncPushPackage"].get("data") or []
            if data:
                log.info("xianyu sync push: %s packets, normalized=%s", len(data), len(messages))
                log.debug("xianyu sync raw: %s", str(raw)[:4000])
                if not messages and self.on_message:
                    # 推送载荷结构变化时，立即拉一次历史，避免等下一轮轮询。
                    asyncio.create_task(
                        self._poll_history(int(time.time() * 1000) - 5 * 60 * 1000),
                        name="xianyu-push-fallback",
                    )
        if not messages or not self.on_message:
            return
        for msg in messages:
            # 同步包会回显自己发出的消息，必须过滤，否则 Agent 会自问自答。
            if msg.get("kind") == "chat" and str(msg.get("buyer_id") or "") == self.user_id:
                continue
            try:
                await self.on_message(msg)
            except Exception:
                log.exception("xianyu on_message failed")

    async def request_lwp(self, lwp: str, body: Any, *, timeout: float = 15.0) -> dict[str, Any]:
        if not self.connected or not self.ws:
            raise RuntimeError("WebSocket 未连接")
        mid = generate_mid()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        frame = {"lwp": lwp, "headers": {"mid": mid}, "body": body}
        try:
            await self._send_json(frame)
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(mid, None)

    async def create_conversation(self, buyer_id: str, item_id: str | None = None) -> str:
        buyer = buyer_id if buyer_id.endswith("@goofish") else f"{buyer_id}@goofish"
        me = self.user_id if self.user_id.endswith("@goofish") else f"{self.user_id}@goofish"
        body = [{
            "pairFirst": buyer,
            "pairSecond": me,
            "bizType": "1",
            "extension": {"itemId": str(item_id or "")},
            "ctx": {"appVersion": "1.0", "platform": "web"},
        }]
        payload = await self.request_lwp("/r/SingleChatConversation/create", body)
        data = payload.get("body") if isinstance(payload, dict) else None
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            for path in (
                ("singleChatConversation", "cid"),
                ("singleChatUserConversation", "singleChatConversation", "cid"),
                ("data", "singleChatConversation", "cid"),
                ("cid",),
            ):
                value: Any = item
                for key in path:
                    value = value.get(key) if isinstance(value, dict) else None
                if isinstance(value, str) and value:
                    return value.replace("@goofish", "")
        raise RuntimeError("创建会话未返回 cid")

    async def send_text(self, chat_id: str, buyer_id: str, text: str, *, timeout: float = 8.0) -> str:
        if not self.connected or not self.ws:
            raise RuntimeError("WebSocket 未连接")
        cid = chat_id if chat_id.endswith("@goofish") else f"{chat_id}@goofish"
        receiver = buyer_id if buyer_id.endswith("@goofish") else f"{buyer_id}@goofish"
        me = self.user_id if self.user_id.endswith("@goofish") else f"{self.user_id}@goofish"
        inner = json.dumps({"contentType": 1, "text": {"text": text}}, ensure_ascii=False, separators=(",", ":"))
        data = base64.b64encode(inner.encode("utf-8")).decode()
        mid = generate_mid()
        frame = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": mid},
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": cid,
                    "conversationType": 1,
                    "content": {"contentType": 101, "custom": {"type": 1, "data": data}},
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {"actualReceivers": [receiver, me]},
            ],
        }
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self._send_json(frame)
        try:
            response = await asyncio.wait_for(fut, timeout=timeout)
            body = response.get("body") if isinstance(response, dict) else None
            reason = ""
            if isinstance(body, dict):
                reason = str(body.get("reason") or body.get("moreInfo") or "")
            if reason:
                raise RuntimeError(f"消息被平台拦截：{reason}")
        except asyncio.TimeoutError:
            # 没有同步回执不代表失败；上游同样按未拦截处理
            pass
        finally:
            self._pending.pop(mid, None)
        return mid
