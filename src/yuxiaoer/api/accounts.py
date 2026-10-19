"""账号生命周期、会话保活与风控。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..runtime import runtime
from ._models import AccountCreateIn

router = APIRouter()

def _account_public(account: dict[str, Any]) -> dict[str, Any]:
    data = dict(account)
    data.pop("refresh_policy_json", None)
    data.pop("meta_json", None)
    data.pop("cookies", None)
    data.pop("access_token", None)
    return data


@router.get("/accounts")
async def accounts() -> list[dict[str, Any]]:
    return [_account_public(a) for a in await runtime.accounts.list()]


@router.post("/accounts")
async def create_account(payload: AccountCreateIn) -> dict[str, Any]:
    try:
        account = await runtime.accounts.create(payload.nickname, payload.platform)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "account": _account_public(account)}


@router.get("/accounts/{account_id}")
async def account_detail(account_id: str) -> dict[str, Any]:
    account = await runtime.accounts.get(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    return _account_public(account)


@router.get("/accounts/{account_id}/events")
async def account_events(account_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return await runtime.accounts.events(account_id, limit)


@router.post("/accounts/{account_id}/login/start")
async def account_login_start(account_id: str) -> dict[str, Any]:
    try:
        return await runtime.accounts.start_login(account_id)
    except KeyError:
        raise HTTPException(404, "账号不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


@router.get("/accounts/{account_id}/login/status")
async def account_login_status(account_id: str) -> dict[str, Any]:
    try:
        data = await runtime.accounts.login_status(account_id)
    except KeyError:
        raise HTTPException(404, "账号不存在")
    data.pop("cookies", None)
    if data.get("account"):
        data["account"] = _account_public(data["account"])
    return data


@router.post("/accounts/{account_id}/sync")
async def account_sync(account_id: str) -> dict[str, Any]:
    sync = getattr(runtime.channel, "sync_account_for", None)
    if not sync:
        raise HTTPException(400, "当前通道不支持账号同步")
    try:
        result = await sync(account_id)
    except KeyError:
        raise HTTPException(404, "账号不存在")
    except Exception as exc:
        raise HTTPException(400, str(exc)[:300])
    return result


@router.post("/accounts/{account_id}/refresh")
async def account_refresh(account_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "account": _account_public(await runtime.accounts.refresh(account_id, kind="manual"))}
    except KeyError:
        raise HTTPException(404, "账号不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


@router.post("/accounts/{account_id}/logout")
async def account_logout(account_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "account": _account_public(await runtime.accounts.logout(account_id))}
    except KeyError:
        raise HTTPException(404, "账号不存在")


@router.post("/accounts/{account_id}/activate")
async def account_activate(account_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "account": _account_public(await runtime.accounts.activate(account_id))}
    except KeyError:
        raise HTTPException(404, "账号不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


@router.post("/accounts/tick")
async def accounts_tick() -> dict[str, Any]:
    return {"ok": True, "result": await runtime.session_keeper.tick(), "status": runtime.session_keeper.status()}


# ---------------- 风控 / 反检测 ----------------

@router.get("/risk")
async def risk_status() -> dict[str, Any]:
    return {
        "status": await runtime.risk.status(),
        "keeper": runtime.session_keeper.status(),
        "write_queue": runtime.queue.stats(),
        "events": await runtime.risk.recent_events(10),
    }


@router.post("/risk/reset")
async def risk_reset() -> dict[str, Any]:
    return {"ok": True, "status": await runtime.risk.reset("manual_reset")}
