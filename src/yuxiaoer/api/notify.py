"""通知渠道、邮件轮询与邮件确认落地页。"""

from __future__ import annotations

import html as html_lib
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import HTMLResponse

from ..core import config
from ..core.util import yuan
from ..runtime import runtime
from ..seller.notifications.email_actions import token as email_action_token, verify as verify_email_action
from ._models import NotifyChannelIn, TestAlertIn

router = APIRouter()

@router.get("/notify/channels")
async def notify_channels() -> list[dict[str, Any]]:
    return await runtime.notifications.list_channels()


@router.post("/notify/channels")
async def notify_channel_create(payload: NotifyChannelIn) -> dict[str, Any]:
    try:
        channel = await runtime.notifications.upsert(payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "channel": channel}


@router.put("/notify/channels/{channel_id}")
async def notify_channel_update(channel_id: str, payload: NotifyChannelIn) -> dict[str, Any]:
    try:
        channel = await runtime.notifications.upsert(payload.model_dump(), channel_id)
    except KeyError:
        raise HTTPException(404, "渠道不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "channel": channel}


@router.delete("/notify/channels/{channel_id}")
async def notify_channel_delete(channel_id: str) -> dict[str, Any]:
    return {"ok": await runtime.notifications.delete(channel_id)}


@router.post("/notify/channels/{channel_id}/test")
async def notify_channel_test(channel_id: str) -> dict[str, Any]:
    try:
        log = await runtime.notifications.send_test(channel_id)
    except KeyError:
        raise HTTPException(404, "渠道不存在")
    if log.get("status") != "sent":
        raise HTTPException(400, log.get("error") or "发送失败")
    return {"ok": True, "log": log}


@router.get("/notify/logs")
async def notify_logs(limit: int = 50) -> list[dict[str, Any]]:
    return await runtime.notifications.logs(limit)


@router.post("/notify/email/poll")
async def notify_email_poll() -> dict[str, Any]:
    return await runtime.email_gateway.poll_once()


def _email_action_page(*, title: str, body: str, status_code: int = 200) -> HTMLResponse:
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_lib.escape(title)} · 鱼小二</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:#f4f7f4;color:#24332d;margin:0;padding:28px}}
.card{{max-width:560px;margin:8vh auto;background:#fff;border:1px solid #dfe9e3;border-radius:16px;padding:26px;box-shadow:0 12px 40px rgba(29,64,48,.08)}}
h2{{margin:0 0 10px;font-size:20px}}p{{line-height:1.7;color:#52655c}}.meta{{background:#f6faf7;border:1px solid #e3eee7;border-radius:10px;padding:12px;margin:16px 0;white-space:pre-wrap;line-height:1.6}}
.btn{{display:inline-block;border:0;border-radius:9px;padding:11px 18px;font-size:14px;cursor:pointer;text-decoration:none;margin:6px 8px 6px 0}}
.ok{{background:#147a55;color:#fff}}.danger{{background:#b23a3a;color:#fff}}.ghost{{background:#edf5f0;color:#2d5c47}}</style></head>
<body><div class="card"><h2>{html_lib.escape(title)}</h2>{body}
<p><a class="btn ghost" href="{html_lib.escape(config.PUBLIC_BASE_URL)}/#/seller">打开控制台</a></p></div></body></html>"""
    return HTMLResponse(page, status_code=status_code, headers={"Cache-Control": "no-store"})


def _email_action_detail(cfm: dict[str, Any]) -> str:
    preview = cfm.get("preview") or {}
    lines = [f"商品：{preview.get('title') or '—'}"]
    if preview.get("price_cents"):
        lines.append(f"价格：¥{yuan(preview['price_cents'])}")
    if preview.get("old_price_cents") is not None and preview.get("new_price_cents") is not None:
        lines.append(f"改价：¥{yuan(preview['old_price_cents'])} → ¥{yuan(preview['new_price_cents'])}")
    if preview.get("publish_category"):
        lines.append(f"分类：{preview['publish_category']}")
    if preview.get("publish_address"):
        lines.append(f"所在地：{preview['publish_address']}")
    lines.append(f"确认项：{cfm['id']}")
    return "\n".join(lines)


@router.get("/email/action/{confirmation_id}/{action}", response_class=HTMLResponse)
async def email_action_landing(confirmation_id: str, action: str, token: str = Query("")) -> HTMLResponse:
    if not verify_email_action(confirmation_id, action, token):
        return _email_action_page(title="链接无效", body="<p>确认链接无效或已过期。</p>", status_code=403)
    cfm = await runtime.confirmations.get(confirmation_id)
    if not cfm or cfm["status"] != "pending":
        return _email_action_page(
            title="确认项已处理", body="<p>这个确认项已执行、取消或过期，无需重复操作。</p>"
        )
    label = "确认执行" if action == "confirm" else "确认取消"
    kind = "确认执行" if action == "confirm" else "取消操作"
    opposite = "cancel" if action == "confirm" else "confirm"
    opposite_label = "改为取消" if action == "confirm" else "改为确认"
    body = f"""<p>你正在通过邮件链接{html_lib.escape(kind)}下面这个操作。请再点击一次按钮，防止邮件客户端预加载链接误触发。</p>
<div class="meta">{html_lib.escape(_email_action_detail(cfm))}</div>
<form method="post" action="/api/email/action/{html_lib.escape(confirmation_id)}/{action}">
  <input type="hidden" name="token" value="{html_lib.escape(token)}">
  <button class="btn {'ok' if action == 'confirm' else 'danger'}" type="submit">{html_lib.escape(label)}</button>
</form>
<a class="btn ghost" href="/api/email/action/{html_lib.escape(confirmation_id)}/{opposite}?token={html_lib.escape(email_action_token(confirmation_id, opposite))}">{html_lib.escape(opposite_label)}</a>"""
    return _email_action_page(title="邮件确认", body=body)


@router.post("/email/action/{confirmation_id}/{action}", response_class=HTMLResponse)
async def email_action_execute(confirmation_id: str, action: str, token: str = Form("")) -> HTMLResponse:
    if not verify_email_action(confirmation_id, action, token):
        return _email_action_page(title="链接无效", body="<p>确认链接无效或已过期。</p>", status_code=403)
    cfm = await runtime.confirmations.get(confirmation_id)
    if not cfm or cfm["status"] != "pending":
        return _email_action_page(title="确认项已处理", body="<p>这个确认项已执行、取消或过期。</p>")
    ok = await runtime.seller.resolve(confirmation_id, action == "confirm")
    if ok:
        title = "已执行" if action == "confirm" else "已取消"
        body = "<p>操作已处理，Agent 的回复已写入「让小二做点什么」。</p>"
    else:
        title = "未执行"
        body = "<p>确认项状态已变化或执行失败，请打开控制台查看待确认项和告警。</p>"
    return _email_action_page(title=title, body=body)


@router.post("/notify/test")
async def notify_test(payload: TestAlertIn) -> dict[str, Any]:
    alert_id = await runtime.alerts.create(payload.level, "notify_test", payload.title, payload.body)
    return {"ok": True, "alert_id": alert_id}
