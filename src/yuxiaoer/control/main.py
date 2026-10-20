"""个人多账号控制台：真实闲鱼账号的启动、扫码、会话与店主指令。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from .aggregator import ShopAggregator
from .proxy import ShopProxy
from .registry import ShopRegistry
from .scheduler import ShopScheduler
from .supervisor import ShopSupervisor

STATIC = Path(__file__).parent / "static" / "control.html"


def get_shop(request: Request, shop_id: str):
    shop = request.app.state.registry.get(shop_id)
    if shop is None:
        raise HTTPException(404, "账号实例不存在")
    return shop


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.registry = ShopRegistry()
    app.state.supervisor = ShopSupervisor(app.state.registry)
    app.state.scheduler = ShopScheduler(app.state.registry)
    app.state.aggregator = ShopAggregator()
    app.state.proxy = ShopProxy()
    app.state.supervisor.start_monitor()
    app.state.scheduler.start()
    if os.getenv("YUXIAOER_CONTROL_AUTOSTART", "1") not in ("0", "false", "off"):
        await app.state.supervisor.start_all()
    yield
    await app.state.scheduler.shutdown()
    await app.state.supervisor.shutdown()


app = FastAPI(title="鱼小二 · 多账号控制台", lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(STATIC)


@app.get("/api/control/accounts")
async def list_accounts(request: Request) -> dict[str, Any]:
    rows = []
    for shop in request.app.state.registry.list():
        status = await request.app.state.supervisor.status(shop)
        account = None
        if status.get("running"):
            try:
                live = await request.app.state.proxy.status(shop)
                account = live.get("account")
            except HTTPException:
                account = None
        status["account"] = account
        rows.append(status)
    return {"accounts": rows}


@app.post("/api/control/accounts")
async def create_account(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        shop = request.app.state.registry.upsert({
            "name": payload.get("name") or "闲鱼账号",
            "enabled": True,
            "auto_start": True,
            "auto_restart": True,
        })
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    request.app.state.scheduler.invalidate(shop.id)
    await request.app.state.supervisor.start(shop)
    return {"ok": True, "account": shop.to_dict()}


@app.delete("/api/control/accounts/{shop_id}")
async def delete_account(request: Request, shop_id: str) -> dict[str, Any]:
    shop = request.app.state.registry.get(shop_id)
    if shop is not None:
        await request.app.state.supervisor.stop(shop)
    if not request.app.state.registry.delete(shop_id):
        raise HTTPException(404, "账号实例不存在")
    return {"ok": True}


@app.post("/api/control/accounts/{shop_id}/login/start")
async def login_start(request: Request, shop_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    proxy: ShopProxy = request.app.state.proxy
    accounts = await proxy.accounts(shop)
    if not accounts:
        created = await proxy.create_account(shop, shop.name)
        account_id = created.get("id")
        if not account_id:
            raise HTTPException(502, "创建账号失败")
    else:
        account_id = accounts[0].get("id")
    data = await proxy.login_start(shop, str(account_id))
    return {"ok": True, "account_id": account_id, **data}


@app.get("/api/control/accounts/{shop_id}/login/status")
async def login_status(request: Request, shop_id: str, account_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.proxy.login_status(shop, account_id)


@app.post("/api/control/accounts/{shop_id}/login/sync")
async def login_sync(request: Request, shop_id: str, account_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.proxy.sync_account(shop, account_id)


async def _account_action(request: Request, shop_id: str, action: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    supervisor = request.app.state.supervisor
    if action == "start":
        return await supervisor.start(shop)
    if action == "stop":
        return await supervisor.stop(shop)
    if action == "restart":
        return await supervisor.restart(shop)
    raise HTTPException(400, "未知操作")


@app.post("/api/control/accounts/{shop_id}/start")
async def start_account(request: Request, shop_id: str) -> dict[str, Any]:
    return await _account_action(request, shop_id, "start")


@app.post("/api/control/accounts/{shop_id}/stop")
async def stop_account(request: Request, shop_id: str) -> dict[str, Any]:
    return await _account_action(request, shop_id, "stop")


@app.post("/api/control/accounts/{shop_id}/restart")
async def restart_account(request: Request, shop_id: str) -> dict[str, Any]:
    return await _account_action(request, shop_id, "restart")


@app.post("/api/control/accounts/{shop_id}/sync")
async def sync_account(request: Request, shop_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.scheduler.sync_shop_items(shop)


@app.post("/api/control/accounts/{shop_id}/schedule")
async def schedule_account(request: Request, shop_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.scheduler.apply_schedule(shop)


@app.get("/api/control/workbench/conversations")
async def workbench_conversations(
    request: Request, shop_id: str = "", filter: str = "active"
) -> dict[str, Any]:
    shops = [get_shop(request, shop_id)] if shop_id else request.app.state.registry.list()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for shop in shops:
        try:
            items = await request.app.state.proxy.conversations(shop, filter)
            for item in items:
                item["shop_id"] = shop.id
                item["shop_name"] = shop.name
                rows.append(item)
        except HTTPException as exc:
            errors.append({"shop_id": shop.id, "error": str(exc.detail)})
    rows.sort(key=lambda row: row.get("last_at") or "", reverse=True)
    return {"conversations": rows[:200], "errors": errors}


@app.get("/api/control/workbench/{shop_id}/conversations/{conversation_id}")
async def workbench_conversation(request: Request, shop_id: str, conversation_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    data = await request.app.state.proxy.conversation(shop, conversation_id)
    data["shop_id"] = shop.id
    data["shop_name"] = shop.name
    return data


@app.post("/api/control/workbench/{shop_id}/conversations/{conversation_id}/reply")
async def workbench_reply(
    request: Request, shop_id: str, conversation_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "回复内容不能为空")
    return await request.app.state.proxy.reply(shop, conversation_id, text[:1000])


@app.post("/api/control/workbench/{shop_id}/conversations/{conversation_id}/{action}")
async def workbench_conversation_action(
    request: Request, shop_id: str, conversation_id: str, action: str
) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    if action == "takeover":
        return await request.app.state.proxy.takeover(shop, conversation_id)
    if action == "resume":
        return await request.app.state.proxy.resume(shop, conversation_id)
    raise HTTPException(400, "未知操作")


@app.get("/api/control/workbench/{shop_id}/seller")
async def workbench_seller(request: Request, shop_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    data = await request.app.state.proxy.seller_messages(shop)
    data["shop_id"] = shop.id
    data["shop_name"] = shop.name
    return data


@app.post("/api/control/workbench/{shop_id}/seller")
async def workbench_seller_send(
    request: Request, shop_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "指令不能为空")
    return await request.app.state.proxy.seller_send(shop, text[:1000])


@app.post("/api/control/workbench/{shop_id}/confirmations/{confirmation_id}/{action}")
async def workbench_confirm(
    request: Request, shop_id: str, confirmation_id: str, action: str
) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.proxy.confirm(shop, confirmation_id, action)


@app.get("/api/control/overview")
async def overview(request: Request) -> dict[str, Any]:
    return await request.app.state.aggregator.overview(request.app.state.registry.list())


@app.get("/api/control/alerts")
async def alerts(request: Request, status: str = "open") -> dict[str, Any]:
    return {"alerts": await request.app.state.aggregator.alerts(request.app.state.registry.list(), status)}


@app.get("/api/control/daily")
async def daily(request: Request) -> dict[str, Any]:
    return await request.app.state.aggregator.daily(request.app.state.registry.list())
