"""邮件确认链接的签名与 URL。链接只用于打开落地页，真正执行走 POST。"""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import quote

from yuxiaoer.core import config


def token(confirmation_id: str, action: str) -> str:
    message = f"{confirmation_id}:{action}".encode("utf-8")
    return hmac.new(config.EMAIL_ACTION_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify(confirmation_id: str, action: str, value: str) -> bool:
    if action not in ("confirm", "cancel"):
        return False
    return hmac.compare_digest(token(confirmation_id, action), value or "")


def urls(confirmation_id: str) -> dict[str, str]:
    base = config.PUBLIC_BASE_URL.rstrip("/")
    cid = quote(confirmation_id, safe="")
    confirm_token = token(confirmation_id, "confirm")
    cancel_token = token(confirmation_id, "cancel")
    return {
        "confirm": f"{base}/api/email/action/{cid}/confirm?token={confirm_token}",
        "cancel": f"{base}/api/email/action/{cid}/cancel?token={cancel_token}",
    }
