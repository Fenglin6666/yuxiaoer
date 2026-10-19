"""邮箱双向通道：SMTP 发告警/回复，IMAP 收店主指令交给小二 Agent。"""

from __future__ import annotations

import asyncio
import email
import html as html_lib
import imaplib
import logging
import re
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from uuid import uuid4

from yuxiaoer.core import config
from yuxiaoer.seller.notifications.email_actions import urls as email_action_urls
from yuxiaoer.core.util import iso, loads
from yuxiaoer.seller.notifications.channels import send_email_sync

log = logging.getLogger("yuxiaoer.email")

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _body_text(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html" and "attachment" not in str(part.get("Content-Disposition") or ""):
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace")
                return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


def _strip_quoted(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if line.strip().startswith(">"):
            continue
        if re.match(r"^(On .+wrote:|在 .+写道:|-----Original Message-----)", line.strip(), re.I):
            break
        if line.strip().startswith("发件人:"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


class EmailGateway:
    def __init__(self, runtime: Any):
        self.runtime = runtime
        self._task: asyncio.Task | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self.last_poll_at: str | None = None
        self.last_result: dict[str, Any] = {}

    async def start(self) -> None:
        if self._task is None:
            self._running = True
            self._task = asyncio.create_task(self._loop(), name="email-gateway")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _channel(self) -> dict[str, Any] | None:
        rows = await self.runtime.notifications.list_channels()
        return next((c for c in rows if c["kind"] == "email" and c["enabled"]), None)

    async def _loop(self) -> None:
        await asyncio.sleep(4)
        while self._running:
            try:
                channel = await self._channel()
                if channel:
                    await self.poll_once(channel)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("email poll failed: %s", str(exc)[:160])
            await asyncio.sleep(60)

    async def poll_once(self, channel: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._lock:
            channel = channel or await self._channel()
            if not channel:
                return {"ok": False, "error": "未配置启用的邮箱渠道"}
            cfg = channel.get("config") or {}
            if not str(cfg.get("imap_host") or "").strip():
                return {"ok": False, "error": "邮箱渠道缺少 IMAP host"}
            allowed = self._allowed_senders(cfg)
            if not allowed:
                return {"ok": False, "error": "邮箱渠道未配置允许发件人，拒绝接收指令"}
            try:
                messages = await asyncio.to_thread(self._fetch_unseen, cfg, allowed)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"IMAP 收取失败：{str(exc)[:200]}"}
            processed = 0
            replied = 0
            errors: list[str] = []
            for item in messages:
                uid = item["uid"]
                try:
                    sender = _sender_address(item["message"])
                    if sender not in allowed:
                        errors.append(f"忽略未知发件人 {sender}")
                        await asyncio.to_thread(self._mark_seen, cfg, uid)
                        continue
                    if str(item["message"].get("X-Yuxiaoer-Agent") or "") == "1":
                        await asyncio.to_thread(self._mark_seen, cfg, uid)
                        continue
                    command = _strip_quoted(_body_text(item["message"])) or _decode(item["message"].get("Subject"))
                    command = command.strip()[:2000]
                    images = self._save_images(item["message"])
                    if not command and not images:
                        await asyncio.to_thread(self._mark_seen, cfg, uid)
                        continue
                    result = await self.runtime.seller.handle(command or "上架", images=images)
                    reply, card = await self._last_agent_message()
                    if not reply:
                        reply = "已处理。" if result.get("ok") else f"处理失败：{result.get('error') or '未知错误'}"
                    text_body, html_body = self._render_reply(reply, card)
                    await asyncio.to_thread(
                        send_email_sync, cfg,
                        f"Re: {_decode(item['message'].get('Subject')) or '鱼小二指令'}",
                        text_body,
                        to_addr=sender,
                        html=html_body,
                    )
                    await asyncio.to_thread(self._mark_seen, cfg, uid)
                    processed += 1
                    replied += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc)[:200])
                    log.warning("email command failed: %s", str(exc)[:160])
                    try:
                        await asyncio.to_thread(self._mark_seen, cfg, uid)
                    except Exception:
                        pass
            self.last_poll_at = iso()
            self.last_result = {
                "ok": True, "fetched": len(messages), "processed": processed,
                "replied": replied, "errors": errors[:10], "at": self.last_poll_at,
            }
            return self.last_result

    @staticmethod
    def _allowed_senders(cfg: dict[str, Any]) -> set[str]:
        raw = str(cfg.get("allowed_senders") or "")
        values = [x.strip().lower() for x in re.split(r"[\s,;，；]+", raw) if x.strip()]
        if not values:
            owner = str(cfg.get("to_addr") or "").strip().lower()
            values = [owner] if owner else []
        return set(values)

    @staticmethod
    def _fetch_unseen(cfg: dict[str, Any], allowed: set[str]) -> list[dict[str, Any]]:
        host = str(cfg.get("imap_host") or "").strip()
        ssl_on = bool(cfg.get("imap_ssl", True))
        port = int(cfg.get("imap_port") or (993 if ssl_on else 143))
        imap = imaplib.IMAP4_SSL(host, port, timeout=25) if ssl_on else imaplib.IMAP4(host, port, timeout=25)
        try:
            user = str(cfg.get("imap_user") or "")
            password = str(cfg.get("imap_password") or "")
            if user:
                imap.login(user, password)
            imap.select(str(cfg.get("imap_folder") or "INBOX"), readonly=False)
            uid_set: set[bytes] = set()
            # 每个允许发件人单独 SEARCH，避免 100 封无关未读被 fetch。
            for address in (sorted(allowed) or [None]):
                criteria = "UNSEEN" if address is None else f'UNSEEN FROM "{address}"'
                typ, data = imap.uid("search", None, criteria)
                if typ == "OK" and data:
                    uid_set.update((data[0] or b"").split())
            out = []
            for uid in uid_set:
                typ, msg_data = imap.uid("fetch", uid, "(RFC822)")
                if typ != "OK" or not msg_data:
                    continue
                raw = next((part[1] for part in msg_data if isinstance(part, tuple)), b"")
                if raw:
                    out.append({"uid": uid, "message": email.message_from_bytes(raw)})
            return out
        finally:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass

    @staticmethod
    def _mark_seen(cfg: dict[str, Any], uid: bytes) -> None:
        host = str(cfg.get("imap_host") or "").strip()
        ssl_on = bool(cfg.get("imap_ssl", True))
        port = int(cfg.get("imap_port") or (993 if ssl_on else 143))
        imap = imaplib.IMAP4_SSL(host, port, timeout=25) if ssl_on else imaplib.IMAP4(host, port, timeout=25)
        try:
            user = str(cfg.get("imap_user") or "")
            password = str(cfg.get("imap_password") or "")
            if user:
                imap.login(user, password)
            imap.select(str(cfg.get("imap_folder") or "INBOX"), readonly=False)
            imap.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    @staticmethod
    def _save_images(msg: Message) -> list[str]:
        media = Path(config.DATA_DIR) / "media"
        media.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            filename = _decode(part.get_filename())
            ext = Path(filename or "").suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTS:
                continue
            payload = part.get_payload(decode=True) or b""
            if not payload or len(payload) > 10 * 1024 * 1024 or len(paths) >= 9:
                continue
            path = media / f"mail_{uuid4().hex}{ext}"
            path.write_bytes(payload)
            paths.append(str(path))
        return paths

    async def _last_agent_message(self) -> tuple[str, dict[str, Any] | None]:
        conv = await self.runtime.messaging.seller_conversation()
        rows = await self.runtime.db.fetchall(
            "SELECT role,text,meta_json FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 8",
            (conv["id"],),
        )
        for row in rows:
            if row["role"] in ("agent", "system") and row["text"]:
                meta = loads(row["meta_json"], {}) or {}
                card = meta.get("card") if isinstance(meta.get("card"), dict) else None
                return str(row["text"])[:4000], card
        return "", None

    @staticmethod
    def _render_reply(reply: str, card: dict[str, Any] | None) -> tuple[str, str | None]:
        if not card or card.get("type") != "confirmation":
            return reply, None
        cfm_id = str(card.get("confirmation_id") or "")
        preview = card.get("preview") or {}
        if not cfm_id:
            return reply, None
        urls = email_action_urls(cfm_id)
        kind = preview.get("kind") or card.get("kind") or "confirmation"
        labels = {
            "publish_listing": "发布商品", "change_price": "改价",
            "offline_item": "下架", "relist_item": "重新上架",
            "bargain_price": "买家议价", "publish_batch": "批量发布",
        }
        label = labels.get(kind, "待确认操作")
        rows: list[tuple[str, str]] = [("操作", label), ("确认项", cfm_id)]
        if preview.get("title"):
            rows.append(("商品", str(preview["title"])))
        if preview.get("price_cents"):
            rows.append(("价格", f"¥{preview['price_cents'] / 100:.2f}"))
        if preview.get("old_price_cents") is not None and preview.get("new_price_cents") is not None:
            rows.append(("改价", f"¥{preview['old_price_cents'] / 100:.2f} → ¥{preview['new_price_cents'] / 100:.2f}"))
        if preview.get("publish_category"):
            rows.append(("发布分类", str(preview["publish_category"])))
        if preview.get("publish_address"):
            rows.append(("所在地", str(preview["publish_address"])))
        if preview.get("images"):
            rows.append(("图片", f"{len(preview['images'])} 张"))
        text_lines = [reply, "", "——— 待确认操作 ———"]
        text_lines += [f"{k}：{v}" for k, v in rows]
        text_lines += [
            "",
            f"确认执行：回复「确认 {cfm_id}」",
            f"取消操作：回复「取消 {cfm_id}」",
            f"或在浏览器打开：{urls['confirm']}",
            f"取消链接：{urls['cancel']}",
        ]
        table = "".join(
            f'<tr><td style="color:#688076;padding:5px 10px 5px 0;white-space:nowrap">{html_lib.escape(k)}</td>'
            f'<td style="padding:5px 0;color:#24332d">{html_lib.escape(v)}</td></tr>'
            for k, v in rows
        )
        html = f"""<div style="border:1px solid #dce9e1;border-radius:12px;padding:14px;margin:18px 0;background:#f7fbf8">
<strong style="font-size:15px;color:#147a55">待确认 · {html_lib.escape(label)}</strong>
<table style="border-collapse:collapse;margin-top:8px;font-size:13px">{table}</table>
<p style="color:#688076;font-size:12px;line-height:1.6;margin:10px 0 0">确认后 Agent 才会调用平台；为避免邮件客户端预加载误触，链接先打开确认页，再点一次执行。</p>
<p style="margin:12px 0 0">
<a href="{html_lib.escape(urls['confirm'])}" style="background:#147a55;color:#fff;text-decoration:none;padding:9px 14px;border-radius:7px;display:inline-block">确认执行</a>
<a href="{html_lib.escape(urls['cancel'])}" style="background:#edf5f0;color:#2d5c47;text-decoration:none;padding:9px 14px;border-radius:7px;display:inline-block;margin-left:8px">取消</a>
</p>
<p style="color:#688076;font-size:11px;margin:10px 0 0">也可以直接回复：确认 {html_lib.escape(cfm_id)} / 取消 {html_lib.escape(cfm_id)}</p>
</div>"""
        return "\n".join(text_lines), html


def _sender_address(msg: Message) -> str:
    return parseaddr(str(msg.get("From") or ""))[1].strip().lower()
