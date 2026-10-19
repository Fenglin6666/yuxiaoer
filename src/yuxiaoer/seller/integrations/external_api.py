"""公开外部接口：兼容 xianyu-auto-reply 的真实数据子集。

只保留有真实数据来源的接口：
- 账号列表
- 外部 Cookie 回传
- 订单查询
- 消息日志查询（auto_reply / auto_delivery）

模拟分类、媒体上传、发布、能力检测接口已删除；原生发布联调后再加回。
所有业务错误固定 HTTP 200 + `{success:false, code, message}`。
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from yuxiaoer.core import config
from yuxiaoer.runtime import runtime
from yuxiaoer.core.util import dumps, iso, now_utc

router = APIRouter(prefix="/api/v1", tags=["公开接口"], route_class=None)  # 下方替换


class ExternalApiRoute(APIRoute):
    """把 FastAPI 默认 422 转成公开接口统一的 HTTP 200 业务错误。"""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                errors = exc.errors()
                loc = errors[0].get("loc") if errors else []
                last = loc[-1] if isinstance(loc, (list, tuple)) and loc else None
                message = f"请求参数{last}不正确" if isinstance(last, str) else "请求体格式不正确"
                return JSONResponse(status_code=200, content=_err(40008, message))

        return handler


router.route_class = ExternalApiRoute


class ExternalResponse(BaseModel):
    success: bool
    code: int
    message: str
    data: Any = None


def _ok(data: Any = None, message: str = "成功") -> dict[str, Any]:
    return {"success": True, "code": 200, "message": message, "data": data}


def _err(code: int, message: str) -> dict[str, Any]:
    return {"success": False, "code": code, "message": message, "data": None}


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "-"


async def _audit_external(
    request: Request, endpoint: str, secret: str, status: str, *,
    account_id: str | None = None, detail: dict[str, Any] | None = None,
) -> None:
    try:
        await runtime.db.execute(
            """INSERT INTO external_api_logs(endpoint,client_ip,secret_masked,account_id,status,detail_json,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (endpoint, _client_ip(request), _mask_secret(secret), account_id, status,
             dumps(detail or {}), iso()),
        )
    except Exception:
        pass


def _validate_secret(secret: str | None) -> tuple[str, dict[str, Any] | None]:
    normalized = (secret or "").strip()
    if not normalized:
        return "", _err(40001, "秘钥不能为空")
    if len(normalized) > 128:
        return "", _err(40001, "秘钥长度不能超过128位")
    expected = (config.EXTERNAL_SECRET_KEY or "").strip()
    if not expected:
        return "", _err(40001, "本机未配置外部接口秘钥")
    if not hmac.compare_digest(normalized, expected):
        return "", _err(40001, "秘钥不存在")
    return normalized, None


async def _account_by_external_id(account_id: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized = (account_id or "").strip()
    if not normalized:
        return None, _err(40002, "闲鱼账号ID不能为空")
    if len(normalized) > 80:
        return None, _err(40002, "闲鱼账号ID长度不能超过80位")
    row = await runtime.db.fetchone(
        "SELECT * FROM accounts WHERE platform_user_id=? OR id=? LIMIT 1",
        (normalized, normalized),
    )
    if not row:
        return None, _err(40002, "闲鱼账号不存在或不属于该秘钥用户")
    return dict(row), None


def _external_account_id(account: dict[str, Any] | None) -> str:
    if not account:
        return ""
    return str(account.get("platform_user_id") or account.get("id") or "")


def _account_enabled(account: dict[str, Any]) -> bool:
    return (
        str(account.get("status") or "").lower() in ("active", "online")
        and str(account.get("session_state") or "") in ("authenticated", "expiring")
        and not account.get("disable_reason")
    )


def _serialize_account(account: dict[str, Any]) -> dict[str, Any]:
    enabled = _account_enabled(account)
    raw_status = str(account.get("status") or "").strip()
    return {
        "account_id": _external_account_id(account),
        "remark": str(account.get("nickname") or "").strip(),
        "enabled": enabled,
        "status": "active" if enabled and raw_status.lower() == "online" else raw_status,
        "status_name": "启用" if enabled else "禁用",
        "disable_reason": str(account.get("disable_reason") or ("请先登录" if not enabled else "")),
    }


def _parse_cookies(raw: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in (raw or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            parsed[key] = value.strip()
    return parsed


# ---------------- 请求模型 ----------------

class EnabledAccountsIn(BaseModel):
    secret_key: str | None = None


class CookieSyncIn(BaseModel):
    secret_key: str | None = None
    account_id: str | None = None
    cookies: str | None = None


class ExternalOrderIn(BaseModel):
    secret_key: str | None = None
    item_ids: list[str] = Field(default_factory=list, max_length=100)
    item_id: str | None = Field(default=None, max_length=1000)
    order_no: str | None = Field(default=None, max_length=64)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class MessageLogIn(BaseModel):
    secret_key: str | None = None
    item_id: str | None = Field(default=None, max_length=64)
    message_type: str = Field(default="auto_reply", pattern="^(auto_reply|auto_delivery)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ---------------- 账号 ----------------

@router.post("/external/enabled-accounts", response_model=ExternalResponse, summary="公开账号列表")
async def list_enabled_accounts(
    request: Request,
    payload: EnabledAccountsIn | None = Body(default=None),
) -> Any:
    secret, error = _validate_secret(payload.secret_key if payload else None)
    if error:
        await _audit_external(request, "enabled-accounts", payload.secret_key if payload else "", "error")
        return JSONResponse(status_code=200, content=error)
    rows = await runtime.db.fetchall("SELECT * FROM accounts")
    accounts = [_serialize_account(dict(row)) for row in rows]
    accounts.sort(key=lambda a: a["account_id"])
    enabled = sum(1 for a in accounts if a["enabled"])
    await _audit_external(request, "enabled-accounts", secret, "ok")
    return _ok({
        "accounts": accounts,
        "total": len(accounts),
        "enabled_total": enabled,
        "disabled_total": len(accounts) - enabled,
    }, "查询成功")


@router.post("/external/account-cookie/sync", response_model=ExternalResponse, summary="外部账号 Cookie 同步")
async def sync_account_cookie(request: Request, payload: CookieSyncIn | None = Body(default=None)) -> Any:
    secret, error = _validate_secret(payload.secret_key if payload else None)
    if error:
        await _audit_external(request, "account-cookie/sync", payload.secret_key if payload else "", "error")
        return JSONResponse(status_code=200, content=error)
    if payload is None:
        return JSONResponse(status_code=200, content=_err(40008, "请求参数不能为空"))
    account_id = (payload.account_id or "").strip()
    cookies = (payload.cookies or "").strip()
    if not account_id or not cookies:
        return JSONResponse(status_code=200, content=_err(40008, "参数不完整"))
    if len(cookies) > 16384:
        return JSONResponse(status_code=200, content=_err(40007, "Cookie 长度不能超过16384位"))
    account, error = await _account_by_external_id(account_id)
    if error:
        await _audit_external(request, "account-cookie/sync", secret, "error", account_id=account_id)
        return JSONResponse(status_code=200, content=error)
    parsed = _parse_cookies(cookies)
    unb = str(parsed.get("unb") or "").strip()
    if not parsed or not unb:
        return JSONResponse(status_code=200, content=_err(40007, "Cookie 格式不正确或缺少登录态"))
    expected = str(account.get("platform_user_id") or "").strip()
    if expected and unb != expected:
        return JSONResponse(status_code=200, content=_err(40007, "Cookie 与账号不匹配（unb 不一致）"))

    now = now_utc()
    from datetime import timedelta
    await runtime.db.execute(
        """UPDATE accounts SET cookies=?,platform_user_id=?,session_state='authenticated',status='online',
           cookie_updated_at=?,last_refresh_at=?,access_expires_at=?,refresh_expires_at=?,
           ws_token_expires_at=?,h5_token_expires_at=?,disable_reason=NULL,updated_at=? WHERE id=?""",
        (cookies, unb, iso(now), iso(now), iso(now + timedelta(hours=24)),
         iso(now + timedelta(days=7)), iso(now + timedelta(hours=12)),
         iso(now + timedelta(hours=2)), iso(now), account["id"]),
    )
    await runtime.accounts._event(account["id"], "cookie_sync", {"source": "external_api", "unb": unb})
    await _audit_external(request, "account-cookie/sync", secret, "ok", account_id=unb,
                          detail={"cookie_len": len(cookies)})
    return _ok(None, "Cookie 已更新")


# ---------------- 订单 ----------------

async def _delivery_attempt(order_id: str) -> dict[str, Any] | None:
    row = await runtime.db.fetchone(
        "SELECT * FROM delivery_attempts WHERE order_id=? ORDER BY id DESC LIMIT 1", (order_id,)
    )
    return dict(row) if row else None


def _money(cents: int | None) -> str:
    return f"{(int(cents or 0) / 100):.2f}"


def _external_status(status: str) -> str:
    """内部状态 → 上游 external 契约常用状态。"""
    return {
        "new": "pending_payment",
        "paid": "pending_ship",
        "shipped": "shipped",
        "delivered": "shipped",
        "done": "completed",
        "refund_open": "refunding",
        "refund_resolved": "refunded",
        "cancelled": "cancelled",
    }.get(status, status or "unknown")


async def _serialize_order(row: dict[str, Any], account: dict[str, Any] | None) -> dict[str, Any]:
    attempt = await _delivery_attempt(row["id"])
    conv = await runtime.db.fetchone(
        "SELECT id FROM conversations WHERE buyer_id=? AND item_id=? ORDER BY created_at DESC LIMIT 1",
        (row["buyer_id"], row["item_id"]),
    )
    status = str(row.get("status") or "unknown").lower()
    reviewed = bool(row.get("reviewed_at"))
    return {
        "id": str(row["id"]),
        "order_no": str(row.get("platform_order_id") or row["id"]),
        "order_id": str(row.get("platform_order_id") or row["id"]),
        "item_id": str(row.get("platform_item_id") or row["item_id"]),
        "item_title": str(row.get("item_title") or ""),
        "status": _external_status(status),
        "buyer_id": str(row.get("buyer_id") or ""),
        "buyer_nick": str(row.get("buyer_nick") or ""),
        "buyer_fish_nick": str(row.get("buyer_nick") or ""),
        "chat_id": str(conv["id"] if conv else ""),
        "spec_name": "",
        "spec_value": "",
        "sku_info": "",
        "quantity": int(row.get("quantity") or 0),
        "amount": _money(row.get("amount_cents")),
        "currency": "CNY",
        "account_id": _external_account_id(account),
        "cookie_id": _external_account_id(account),
        "account_name": str((account or {}).get("nickname") or ""),
        "is_bargain": False,
        "is_rated": reviewed,
        "is_red_flower": False,
        "is_unregistered": False,
        "unregister_error_reason": "",
        "receiver_name": "",
        "receiver_phone": "",
        "receiver_address": str(row.get("address") or ""),
        "delivery_method": "virtual" if row.get("delivery_mode") == "virtual" else "express",
        "delivery_content": str(row.get("card_content") or ""),
        "delivery_fail_reason": str((attempt or {}).get("error") or ""),
        "card_only_delivered": False,
        "delivery_send_status": (attempt or {}).get("status"),
        "delivery_send_fail_reason": (attempt or {}).get("error"),
        "source": "yuxiaoer",
        "placed_at": row.get("paid_at") or row.get("created_at"),
        "synced_at": row.get("updated_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _normalize_item_ids(item_ids: list[str] | None, item_id: str | None) -> tuple[list[str], str | None]:
    values: list[str] = list(item_ids or [])
    if item_id:
        values.extend(item_id.split(","))
    result: list[str] = []
    for value in values:
        for part in str(value).split(","):
            part = part.strip()
            if len(part) > 64:
                return [], "商品ID长度不能超过64位"
            if part and part not in result:
                result.append(part)
    if len(result) > 100:
        return [], "商品ID数量不能超过100个"
    return result, None


async def _query_orders(
    secret: str, item_ids: list[str], order_no: str | None, page: int, page_size: int,
) -> dict[str, Any]:
    where = ["1=1"]
    params: list[Any] = []
    if order_no:
        where.append("(o.platform_order_id=? OR o.id=?)")
        params.extend([order_no, order_no])
    if item_ids:
        placeholders = ",".join("?" for _ in item_ids)
        where.append(f"(i.platform_item_id IN ({placeholders}) OR o.item_id IN ({placeholders}))")
        params.extend(item_ids + item_ids)
    base = (
        "FROM orders o LEFT JOIN items i ON i.id=o.item_id "
        "LEFT JOIN buyers b ON b.id=o.buyer_id WHERE " + " AND ".join(where)
    )
    total_row = await runtime.db.fetchone("SELECT COUNT(*) AS n " + base, tuple(params))
    total = int(total_row["n"] if total_row else 0)
    rows = await runtime.db.fetchall(
        "SELECT o.*, i.title AS item_title, i.platform_item_id AS platform_item_id, "
        "i.delivery_mode AS delivery_mode, i.card_content AS card_content, b.nick AS buyer_nick "
        + base + " ORDER BY CASE WHEN o.paid_at IS NULL THEN 1 ELSE 0 END, "
        "o.paid_at DESC, o.created_at DESC LIMIT ? OFFSET ?",
        tuple(params + [page_size, (page - 1) * page_size]),
    )
    active = await runtime.db.fetchone(
        "SELECT * FROM accounts WHERE is_active=1 ORDER BY updated_at DESC LIMIT 1"
    )
    account = dict(active) if active else None
    items = [await _serialize_order(dict(r), account) for r in rows]
    return {
        "list": items, "orders": items, "total": total, "page": page,
        "page_size": page_size, "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


@router.post("/external/orders", response_model=ExternalResponse, summary="公开订单查询（POST）")
async def list_external_orders(request: Request, payload: ExternalOrderIn | None = Body(default=None)) -> Any:
    if payload is None:
        return JSONResponse(status_code=200, content=_err(40008, "请求参数不能为空"))
    secret, error = _validate_secret(payload.secret_key)
    if error:
        return JSONResponse(status_code=200, content=error)
    item_ids, item_error = _normalize_item_ids(payload.item_ids, payload.item_id)
    if item_error:
        return JSONResponse(status_code=200, content=_err(40008, item_error))
    data = await _query_orders(secret, item_ids, (payload.order_no or "").strip() or None,
                               payload.page, payload.page_size)
    await _audit_external(request, "orders", secret, "ok", detail={"total": data["total"]})
    return _ok(data, "订单查询成功")


@router.get("/external/orders", response_model=ExternalResponse, summary="公开订单查询（GET）")
async def get_external_orders(
    request: Request,
    secret_key: str | None = Query(default=None),
    item_id: list[str] | None = Query(default=None),
    item_ids: list[str] | None = Query(default=None),
    order_no: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Any:
    secret, error = _validate_secret(secret_key)
    if error:
        return JSONResponse(status_code=200, content=error)
    merged = list(item_id or []) + list(item_ids or [])
    normalized, item_error = _normalize_item_ids(merged, None)
    if item_error:
        return JSONResponse(status_code=200, content=_err(40008, item_error))
    data = await _query_orders(secret, normalized, (order_no or "").strip() or None, page, page_size)
    await _audit_external(request, "orders", secret, "ok", detail={"total": data["total"]})
    return _ok(data, "订单查询成功")


# ---------------- 消息日志 ----------------

async def _find_item(item_id: str) -> dict[str, Any] | None:
    row = await runtime.db.fetchone(
        "SELECT * FROM items WHERE id=? OR platform_item_id=? LIMIT 1", (item_id, item_id)
    )
    return dict(row) if row else None


def _log_common(item: dict[str, Any], account: dict[str, Any] | None, conv_id: str | None) -> dict[str, Any]:
    return {
        "account_id": _external_account_id(account),
        "account_name": str((account or {}).get("nickname") or ""),
        "chat_id": conv_id or "",
        "item_id": str(item.get("platform_item_id") or item.get("id") or ""),
        "item_title": str(item.get("title") or ""),
    }


async def _reply_logs(item: dict[str, Any], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    base = (
        "FROM messages m JOIN conversations c ON c.id=m.conversation_id "
        "WHERE c.item_id=? AND m.direction='out' AND m.role!='system' "
        "AND m.status IN ('sent','delivered') AND COALESCE(m.meta_json,'') NOT LIKE '%virtual_delivery%'"
    )
    total_row = await runtime.db.fetchone("SELECT COUNT(*) AS n " + base, (item["id"],))
    total = int(total_row["n"] if total_row else 0)
    rows = await runtime.db.fetchall(
        "SELECT m.*, c.id AS conv_id, c.buyer_id AS buyer_id, b.nick AS buyer_nick "
        "FROM messages m JOIN conversations c ON c.id=m.conversation_id "
        "LEFT JOIN buyers b ON b.id=c.buyer_id "
        "WHERE c.item_id=? AND m.direction='out' AND m.role!='system' "
        "AND m.status IN ('sent','delivered') AND COALESCE(m.meta_json,'') NOT LIKE '%virtual_delivery%' "
        "ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?",
        (item["id"], page_size, (page - 1) * page_size),
    )
    active = await runtime.db.fetchone(
        "SELECT * FROM accounts WHERE is_active=1 ORDER BY updated_at DESC LIMIT 1"
    )
    account = dict(active) if active else None
    result = []
    for row in rows:
        row = dict(row)
        src = await runtime.db.fetchone(
            "SELECT * FROM messages WHERE conversation_id=? AND direction='in' AND created_at<=? "
            "ORDER BY created_at DESC LIMIT 1",
            (row["conversation_id"], row["created_at"]),
        )
        meta = {}
        try:
            import json
            meta = json.loads(row.get("meta_json") or "{}")
        except Exception:
            meta = {}
        status = str(row.get("status") or "")
        now = str(row.get("created_at") or "")
        order = await runtime.db.fetchone(
            "SELECT platform_order_id FROM orders WHERE buyer_id=? AND item_id=? "
            "ORDER BY created_at DESC LIMIT 1", (row.get("buyer_id"), item["id"]),
        )
        entry = {
            "id": row["id"],
            "order_no": str(order["platform_order_id"] or "") if order else "",
            "source_message_id": (dict(src).get("external_id") or dict(src).get("id")) if src else "",
            "sender_user_id": row.get("buyer_id") or "",
            "sender_user_name": row.get("buyer_nick") or "",
            "source_message": (dict(src).get("text") if src else "") or "",
            "source_message_time": (dict(src).get("created_at") if src else "") or "",
            "process_status": "success" if status in ("sent", "delivered", "received") else (
                "failed" if status in ("failed", "error") else "processing"
            ),
            "decision_reason": "buyer_agent_auto_reply",
            "reply_strategy": "agent",
            "reply_mode": "auto",
            "matched_keyword": str(meta.get("matched_keyword") or ""),
            "matched_rule_type": str(meta.get("rule_type") or ""),
            "default_reply_scope": "",
            "default_reply_once": False,
            "ai_model_name": str(meta.get("model") or ""),
            "ai_provider_name": str(meta.get("provider") or ""),
            "reply_text": row.get("text") or "",
            "reply_image_url": str(meta.get("image_url") or ""),
            "error_message": str(meta.get("error") or ""),
            "send_status": status,
            "send_fail_reason": str(meta.get("error") or ""),
            "created_at": now,
            "updated_at": now,
            **_log_common(item, account, row.get("conv_id")),
        }
        result.append(entry)
    return result, total


async def _delivery_logs(item: dict[str, Any], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    base = (
        "FROM delivery_attempts a JOIN orders o ON o.id=a.order_id "
        "WHERE o.item_id=?"
    )
    total_row = await runtime.db.fetchone("SELECT COUNT(*) AS n " + base, (item["id"],))
    total = int(total_row["n"] if total_row else 0)
    rows = await runtime.db.fetchall(
        "SELECT a.*, o.platform_order_id, o.buyer_id FROM delivery_attempts a "
        "JOIN orders o ON o.id=a.order_id WHERE o.item_id=? ORDER BY a.id DESC LIMIT ? OFFSET ?",
        (item["id"], page_size, (page - 1) * page_size),
    )
    active = await runtime.db.fetchone(
        "SELECT * FROM accounts WHERE is_active=1 ORDER BY updated_at DESC LIMIT 1"
    )
    account = dict(active) if active else None
    result = []
    for row in rows:
        row = dict(row)
        conv = await runtime.db.fetchone(
            "SELECT id FROM conversations WHERE buyer_id=? AND item_id=? ORDER BY created_at DESC LIMIT 1",
            (row["buyer_id"], item["id"]),
        )
        entry = {
            "id": row["id"],
            "order_no": str(row.get("platform_order_id") or row.get("order_id") or ""),
            "source_message_id": "",
            "sender_user_id": row.get("buyer_id") or "",
            "sender_user_name": "",
            "source_message": "",
            "source_message_time": "",
            "process_status": "success" if row.get("status") == "sent" else "failed",
            "decision_reason": "auto_delivery",
            "reply_strategy": "delivery",
            "reply_mode": "auto",
            "matched_keyword": "",
            "matched_rule_type": "",
            "default_reply_scope": "",
            "default_reply_once": False,
            "ai_model_name": "",
            "ai_provider_name": "",
            "reply_text": str(row.get("content_snippet") or ""),
            "reply_image_url": "",
            "error_message": str(row.get("error") or ""),
            "send_status": str(row.get("status") or ""),
            "send_fail_reason": str(row.get("error") or ""),
            "created_at": row.get("created_at"),
            "updated_at": row.get("created_at"),
            **_log_common(item, account, conv["id"] if conv else None),
        }
        result.append(entry)
    return result, total


async def _query_message_logs(
    item_id: str, message_type: str, page: int, page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    item = await _find_item(item_id)
    if not item:
        return [], 0
    if message_type == "auto_delivery":
        return await _delivery_logs(item, page, page_size)
    return await _reply_logs(item, page, page_size)


@router.post("/external/message-logs", response_model=ExternalResponse, summary="公开消息日志（POST）")
async def list_external_message_logs(
    request: Request, payload: MessageLogIn | None = Body(default=None),
) -> Any:
    if payload is None:
        return JSONResponse(status_code=200, content=_err(40008, "请求参数不能为空"))
    secret, error = _validate_secret(payload.secret_key)
    if error:
        return JSONResponse(status_code=200, content=error)
    item_id = (payload.item_id or "").strip()
    if not item_id:
        return JSONResponse(status_code=200, content=_err(40008, "商品ID不能为空"))
    if len(item_id) > 64:
        return JSONResponse(status_code=200, content=_err(40008, "商品ID长度不能超过64位"))
    items, total = await _query_message_logs(item_id, payload.message_type, payload.page, payload.page_size)
    data = {
        "list": items, "logs": items, "total": total, "page": payload.page,
        "page_size": payload.page_size,
        "total_pages": (total + payload.page_size - 1) // payload.page_size if total else 0,
    }
    await _audit_external(request, "message-logs", secret, "ok",
                          detail={"item_id": item_id, "total": total})
    return _ok(data, "消息日志查询成功")


@router.get("/external/message-logs", response_model=ExternalResponse, summary="公开消息日志（GET）")
async def get_external_message_logs(
    request: Request,
    secret_key: str | None = Query(default=None),
    item_id: str | None = Query(default=None),
    message_type: str = Query(default="auto_reply"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Any:
    secret, error = _validate_secret(secret_key)
    if error:
        return JSONResponse(status_code=200, content=error)
    if message_type not in ("auto_reply", "auto_delivery"):
        return JSONResponse(status_code=200, content=_err(40008, "message_type仅支持auto_reply或auto_delivery"))
    item_id = (item_id or "").strip()
    if not item_id:
        return JSONResponse(status_code=200, content=_err(40008, "商品ID不能为空"))
    items, total = await _query_message_logs(item_id, message_type, page, page_size)
    data = {
        "list": items, "logs": items, "total": total, "page": page, "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }
    await _audit_external(request, "message-logs", secret, "ok", detail={"total": total})
    return _ok(data, "消息日志查询成功")


__all__ = ["router"]
