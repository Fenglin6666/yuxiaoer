"""通知渠道发送器：一个渠道一个小函数 + 注册表。

新增渠道只需要写一个 `async def send_xxx(cfg, msg) -> str` 并注册到 `SENDERS`，
`NotificationService` 不用改。失败抛异常，由上层统一重试/记日志。
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Awaitable, Callable

import httpx

Sender = Callable[[dict[str, Any], "Message"], Awaitable[str]]


@dataclass(slots=True)
class Message:
    title: str
    body: str
    level: str
    alert: dict[str, Any]

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"


async def post(url: str, **kwargs: Any) -> str:
    """统一的 HTTP 投递：8 秒超时、非 2xx 抛错、返回体截断。"""
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.post(url, **kwargs)
    response.raise_for_status()
    return response.text[:200]


def _required(cfg: dict[str, Any], key: str, label: str) -> str:
    value = str(cfg.get(key) or "").strip()
    if not value:
        raise ValueError(f"缺少{label}")
    return value


async def send_log(cfg: dict[str, Any], msg: Message) -> str:
    return "recorded"


async def send_wecom(cfg: dict[str, Any], msg: Message) -> str:
    url = _required(cfg, "url", "企业微信 webhook url")
    return await post(url, json={"msgtype": "text", "text": {"content": msg.text[:1800]}})


async def send_bark(cfg: dict[str, Any], msg: Message) -> str:
    url = _required(cfg, "url", "Bark server url").rstrip("/")
    return await post(
        url,
        json={"title": msg.title, "body": msg.body[:1800], "group": "yuxiaoer"},
    )


async def send_serverchan(cfg: dict[str, Any], msg: Message) -> str:
    token = _required(cfg, "token", "Server酱 token")
    return await post(
        f"https://sctapi.ftqq.com/{token}.send",
        data={"title": msg.title[:100], "desp": msg.body[:1800]},
    )


async def send_ntfy(cfg: dict[str, Any], msg: Message) -> str:
    url = _required(cfg, "url", "ntfy url").rstrip("/")
    topic = str(cfg.get("topic") or "yuxiaoer")
    return await post(
        f"{url}/{topic}",
        content=msg.text[:1800],
        headers={
            "Title": msg.title[:100],
            "Priority": "high" if msg.level == "P0" else "default",
        },
    )


async def send_telegram(cfg: dict[str, Any], msg: Message) -> str:
    token = _required(cfg, "token", "Telegram token")
    chat_id = _required(cfg, "chat_id", "Telegram chat_id")
    return await post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": msg.text[:4000], "disable_web_page_preview": True},
    )


async def send_pushplus(cfg: dict[str, Any], msg: Message) -> str:
    token = _required(cfg, "token", "PushPlus token")
    return await post(
        "http://www.pushplus.plus/send",
        json={"token": token, "title": msg.title[:100], "content": msg.body[:1800], "template": "txt"},
    )


async def send_gotify(cfg: dict[str, Any], msg: Message) -> str:
    url = _required(cfg, "url", "Gotify url").rstrip("/")
    token = str(cfg.get("token") or "")
    return await post(
        f"{url}/message",
        params={"token": token},
        json={
            "title": msg.title[:100],
            "message": msg.body[:1800],
            "priority": 8 if msg.level == "P0" else 5,
        },
    )


async def send_generic(cfg: dict[str, Any], msg: Message) -> str:
    url = _required(cfg, "url", "webhook url")
    return await post(
        url,
        json={"title": msg.title, "body": msg.body, "level": msg.level, "alert": msg.alert},
    )


def send_email_sync(
    cfg: dict[str, Any],
    title: str,
    body: str,
    to_addr: str | None = None,
    html: str | None = None,
) -> str:
    host = str(cfg.get("smtp_host") or "").strip()
    if not host:
        raise ValueError("缺少 SMTP host")
    ssl_on = bool(cfg.get("smtp_ssl", True))
    port = int(cfg.get("smtp_port") or (465 if ssl_on else 587))
    user = str(cfg.get("smtp_user") or "").strip()
    password = str(cfg.get("smtp_password") or "")
    from_addr = str(cfg.get("from_addr") or user).strip()
    to_addr = str(to_addr or cfg.get("to_addr") or "").strip()
    if not from_addr or not to_addr:
        raise ValueError("缺少发件人/收件人邮箱")
    msg = EmailMessage()
    msg["Subject"] = title[:180]
    msg["From"] = formataddr(("鱼小二", from_addr))
    msg["To"] = to_addr
    msg["X-Yuxiaoer-Agent"] = "1"
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body or title)
    if html:
        msg.add_alternative(html, subtype="html")
    smtp = smtplib.SMTP_SSL(host, port, timeout=25) if ssl_on else smtplib.SMTP(host, port, timeout=25)
    try:
        if not ssl_on and cfg.get("smtp_starttls", True):
            smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)
    finally:
        try:
            smtp.quit()
        except Exception:
            pass
    return "sent"


async def send_email(cfg: dict[str, Any], msg: Message) -> str:
    return await asyncio.to_thread(send_email_sync, cfg, msg.title, msg.body)


SENDERS: dict[str, Sender] = {
    "log": send_log,
    "wecom": send_wecom,
    "bark": send_bark,
    "serverchan": send_serverchan,
    "ntfy": send_ntfy,
    "telegram": send_telegram,
    "pushplus": send_pushplus,
    "gotify": send_gotify,
    "generic": send_generic,
    "email": send_email,
}
