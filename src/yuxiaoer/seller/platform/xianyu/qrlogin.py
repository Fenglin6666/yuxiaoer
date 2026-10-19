"""闲鱼扫码登录（真实 passport.goofish.com 流程，clean-room）。

流程事实：
1. 预热 m_h5_tk；
2. 从 mini_login.htm 的 window.viewData.loginFormData 取登录参数；
3. generate.do 取二维码 codeContent；
4. query.do 轮询 NEW/SCANED/CONFIRMED/EXPIRED；
5. CONFIRMED 后收集 Set-Cookie，提取 unb。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

import httpx
import qrcode

from yuxiaoer.core import config
from .mtop import merge_set_cookies, parse_cookies

log = logging.getLogger("yuxiaoer.xianyu.qr")

HOST = "https://passport.goofish.com"
H5_URL = "https://h5api.m.goofish.com/h5/mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get/1.0/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _headers() -> dict[str, str]:
    return {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Origin": HOST,
        "Referer": f"{HOST}/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }


@dataclass
class QRSession:
    id: str
    status: str = "waiting"
    qr_code_url: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 300)
    cookies_str: str = ""
    unb: str = ""
    message: str = ""
    verification_url: str = ""
    task: asyncio.Task | None = None

    def public(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "status": self.status,
            "qr_code_url": self.qr_code_url,
            "unb": self.unb,
            "message": self.message,
            "verification_url": self.verification_url,
            "expires_in": max(0, int(self.expires_at - time.time())),
        }


def _image_data_url(content: str) -> str:
    qr = qrcode.QRCode(
        version=5, error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10, border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)
    image = qr.make_image()
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _cookie_string(values: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in values.items() if k)


class QRLoginManager:
    def __init__(self):
        self.sessions: dict[str, QRSession] = {}
        self.timeout = httpx.Timeout(connect=20.0, read=30.0, write=20.0, pool=20.0)

    async def start(self) -> dict[str, Any]:
        session = QRSession(id=uuid.uuid4().hex)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            await self._warm_h5(client, session)
            await self._login_params(client, session)
            response = await client.get(
                f"{HOST}/newlogin/qrcode/generate.do",
                params=session.params,
                headers=_headers(),
                cookies=session.cookies,
            )
            try:
                payload = response.json()
            except Exception:
                raise RuntimeError(f"二维码接口返回非 JSON：{response.text[:120]}")
            if not payload.get("content", {}).get("success"):
                raise RuntimeError("获取登录二维码失败")
            data = payload["content"]["data"]
            session.params["t"] = data.get("t")
            session.params["ck"] = data.get("ck")
            session.qr_code_url = _image_data_url(str(data.get("codeContent") or ""))
            session.status = "waiting"
        self.sessions[session.id] = session
        session.task = asyncio.create_task(self._poll(session), name=f"qr-poll:{session.id}")
        return {"success": True, "session_id": session.id, "qr_code_url": session.qr_code_url, "expires_in": 300}

    async def status(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if not session:
            return {"session_id": session_id, "status": "not_found", "message": "二维码会话不存在"}
        if time.time() > session.expires_at and session.status in ("waiting", "scanned"):
            session.status = "expired"
            session.message = "二维码已过期"
        data = session.public()
        if session.status == "success":
            data["cookies"] = session.cookies_str
            data["unb"] = session.unb
        return data

    async def cancel(self, session_id: str) -> None:
        session = self.sessions.pop(session_id, None)
        if session and session.task:
            session.task.cancel()

    async def close(self) -> None:
        for session in list(self.sessions.values()):
            if session.task:
                session.task.cancel()
        self.sessions.clear()

    async def _warm_h5(self, client: httpx.AsyncClient, session: QRSession) -> None:
        try:
            response = await client.get(H5_URL, headers=_headers(), cookies=session.cookies)
            session.cookies.update({k: v for k, v in response.cookies.items()})
            token = session.cookies.get("m_h5_tk", "").split("_")[0]
            data_value = json.dumps({"bizScene": "home"}, separators=(",", ":"))
            t = str(int(time.time() * 1000))
            sign = hashlib.md5(f"{token}&{t}&34839810&{data_value}".encode()).hexdigest()
            await client.post(
                H5_URL,
                params={
                    "jsv": "2.7.2", "appKey": "34839810", "t": t, "sign": sign,
                    "v": "1.0", "type": "originaljson", "dataType": "json",
                    "timeout": 20000, "api": "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get",
                    "data": data_value,
                },
                headers=_headers(),
                cookies=session.cookies,
            )
        except Exception as exc:
            log.debug("h5 token warmup failed: %s", exc)

    async def _login_params(self, client: httpx.AsyncClient, session: QRSession) -> None:
        response = await client.get(
            f"{HOST}/mini_login.htm",
            params={
                "lang": "zh_cn", "appName": "xianyu", "appEntrance": "web",
                "styleType": "vertical", "bizParams": "", "notLoadSsoView": "False",
                "notKeepLogin": "False", "isMobile": "False", "qrCodeFirst": "False",
                "stie": "77", "rnd": random.random(),
            },
            headers=_headers(),
            cookies=session.cookies,
        )
        match = re.search(r"window\.viewData\s*=\s*(\{.*?\});", response.text, re.S)
        if not match:
            raise RuntimeError("获取登录参数失败（viewData 未找到）")
        view = json.loads(match.group(1))
        data = view.get("loginFormData")
        if not data:
            raise RuntimeError("获取登录参数失败（loginFormData 缺失）")
        data["umidTag"] = "SERVER"
        session.params.update(data)

    async def _poll(self, session: QRSession) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                while time.time() < session.expires_at:
                    if session.status in ("success", "expired", "cancelled", "verification_required"):
                        return
                    try:
                        response = await client.post(
                            f"{HOST}/newlogin/qrcode/query.do",
                            data=session.params,
                            headers=_headers(),
                            cookies=session.cookies,
                        )
                        for header in response.headers.get_list("set-cookie"):
                            first = header.split(";", 1)[0]
                            if "=" in first:
                                key, value = first.split("=", 1)
                                session.cookies[key.strip()] = value.strip()
                        payload = response.json()
                        status = str(payload.get("content", {}).get("data", {}).get("qrCodeStatus") or "")
                        data = payload.get("content", {}).get("data", {})
                        if status == "SCANED":
                            session.status = "scanned"
                            session.message = "已扫码，请在手机端确认"
                        elif status == "CONFIRMED":
                            if data.get("iframeRedirect") is True:
                                session.status = "verification_required"
                                session.verification_url = str(data.get("iframeRedirectUrl") or "")
                                session.message = "平台要求人脸验证，请在手机端完成后再刷新"
                                return
                            session.cookies_str = _cookie_string(session.cookies)
                            session.unb = str(parse_cookies(session.cookies_str).get("unb") or "")
                            if not session.unb:
                                session.status = "cancelled"
                                session.message = "登录成功但 Cookie 缺少 unb"
                                return
                            session.status = "success"
                            session.message = "登录成功"
                            return
                        elif status == "EXPIRED":
                            session.status = "expired"
                            session.message = "二维码已过期"
                            return
                        elif status in ("NEW", ""):
                            session.status = "waiting"
                        else:
                            session.status = "cancelled"
                            session.message = f"扫码状态异常：{status}"
                            return
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        log.debug("qr poll error: %s", str(exc)[:120])
                    await asyncio.sleep(0.8)
                session.status = "expired"
                session.message = "二维码已过期"
        except asyncio.CancelledError:
            return
        finally:
            if session.status in ("success", "expired", "cancelled"):
                # 保留结果供前端读取，稍后由 cleanup 删除
                pass
