"""Cookie 保活与 IM Token 获取（真实接口，clean-room）。

- silentHasLogin.do：短登录态续期
- setLoginSettings.do：长登录 Cookie 续期（status=0）
- mtop.taobao.idlemessage.pc.login.token：获取 WebSocket accessToken
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from yuxiaoer.core import config
from .mtop import MtopClient, merge_set_cookies

log = logging.getLogger("yuxiaoer.xianyu.session")

PASSPORT = "https://passport.goofish.com"
SILENT_URL = f"{PASSPORT}/newlogin/silentHasLogin.do"
SETTINGS_URL = f"{PASSPORT}/ac/account/setLoginSettings.do"


def _headers(cookies: str) -> dict[str, str]:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.goofish.com",
        "referer": "https://www.goofish.com/",
        "user-agent": config.XY_USER_AGENT,
        "cookie": (cookies or "").replace("\n", "").replace("\r", ""),
    }


async def renew_cookies(cookies: str) -> dict[str, Any]:
    """返回 {success, cookies, changed, message}。失败不抛异常，保留原 Cookie。"""
    current = cookies or ""
    changed: dict[str, str] = {}
    messages: list[str] = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        try:
            response = await client.post(
                SILENT_URL,
                params={
                    "documentReferer": "https://www.goofish.com/",
                    "appName": "xianyu", "appEntrance": "xianyu_sdkSilent",
                    "fromSite": "0", "ltl": "true",
                },
                headers=_headers(current),
            )
            headers = response.headers.get_list("set-cookie")
            if headers:
                current, delta = merge_set_cookies(current, headers)
                changed.update(delta)
            try:
                payload = response.json()
                content = payload.get("content") if isinstance(payload, dict) else {}
                if isinstance(content, dict) and content.get("success"):
                    messages.append("silentHasLogin 成功")
                else:
                    messages.append("silentHasLogin 未成功")
            except Exception:
                messages.append("silentHasLogin 返回非 JSON")
        except Exception as exc:
            messages.append(f"silentHasLogin 失败：{str(exc)[:80]}")

        try:
            response = await client.post(
                SETTINGS_URL,
                params={"fromSite": "77", "appName": "xianyu", "bizEntrance": "web"},
                data={"status": "0"},
                headers=_headers(current),
            )
            headers = [
                h for h in response.headers.get_list("set-cookie")
                if "max-age=0" not in h.lower() and "1970" not in h
            ]
            if headers:
                current, delta = merge_set_cookies(current, headers)
                changed.update(delta)
                messages.append("setLoginSettings 已下发新 Cookie")
            else:
                messages.append("setLoginSettings 未下发 Cookie")
        except Exception as exc:
            messages.append(f"setLoginSettings 失败：{str(exc)[:80]}")

    return {
        "success": bool(changed) or any("成功" in m for m in messages),
        "cookies": current,
        "changed": changed,
        "message": "；".join(messages),
    }


async def fetch_im_token(cookies: str, device_id: str = "") -> dict[str, Any]:
    """取 IM accessToken，返回 {token, device_id, cookies, data}。"""
    client = MtopClient(cookies, device_id=device_id)
    token, returned_device = await client.get_im_token()
    return {
        "token": token,
        "device_id": returned_device,
        "cookies": client.cookies,
        "data": {},
    }
