"""8787 多账号 Web：现有 static 前端 + 按账号代理 API + 账号实例管理。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .proxy import ShopProxy
from .registry import ShopRegistry
from .scheduler import ShopScheduler
from .supervisor import ShopSupervisor

STATIC = Path(__file__).resolve().parent.parent / "static"


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
    app.state.proxy = ShopProxy()
    app.state.supervisor.start_monitor()
    app.state.scheduler.start()
    if os.getenv("YUXIAOER_CONTROL_AUTOSTART", "1") not in ("0", "false", "off"):
        await app.state.supervisor.start_all()
    yield
    await app.state.scheduler.shutdown()
    await app.state.supervisor.shutdown()


app = FastAPI(title="鱼小二 · 多账号", lifespan=lifespan)
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/hub/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "accounts": len(app.state.registry.list())}


@app.get("/api/hub/accounts")
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
    return {"accounts": rows, "selected": request.headers.get("x-account-id") or ""}


@app.post("/api/hub/accounts")
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


@app.delete("/api/hub/accounts/{shop_id}")
async def delete_account(request: Request, shop_id: str) -> dict[str, Any]:
    shop = request.app.state.registry.get(shop_id)
    if shop is not None:
        await request.app.state.supervisor.stop(shop)
    if not request.app.state.registry.delete(shop_id):
        raise HTTPException(404, "账号实例不存在")
    return {"ok": True}


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


@app.post("/api/hub/accounts/{shop_id}/start")
async def start_account(request: Request, shop_id: str) -> dict[str, Any]:
    return await _account_action(request, shop_id, "start")


@app.post("/api/hub/accounts/{shop_id}/stop")
async def stop_account(request: Request, shop_id: str) -> dict[str, Any]:
    return await _account_action(request, shop_id, "stop")


@app.post("/api/hub/accounts/{shop_id}/restart")
async def restart_account(request: Request, shop_id: str) -> dict[str, Any]:
    return await _account_action(request, shop_id, "restart")


@app.post("/api/hub/accounts/{shop_id}/login/start")
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
        active = next(
            (item for item in accounts if item.get("status") == "online" or item.get("is_active")),
            accounts[0],
        )
        account_id = active.get("id")
    data = await proxy.login_start(shop, str(account_id))
    return {"ok": True, "account_id": account_id, **data}


@app.get("/api/hub/accounts/{shop_id}/login/status")
async def login_status(request: Request, shop_id: str, account_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.proxy.login_status(shop, account_id)


@app.post("/api/hub/accounts/{shop_id}/login/sync")
async def login_sync(request: Request, shop_id: str, account_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.proxy.sync_account(shop, account_id)


@app.post("/api/hub/accounts/{shop_id}/sync")
async def sync_account(request: Request, shop_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.scheduler.sync_shop_items(shop)


@app.post("/api/hub/accounts/{shop_id}/schedule")
async def schedule_account(request: Request, shop_id: str) -> dict[str, Any]:
    shop = get_shop(request, shop_id)
    return await request.app.state.scheduler.apply_schedule(shop)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_api(request: Request, path: str) -> Response:
    """把现有前端的 /api/* 转发到当前选中的账号实例。"""
    account_id = request.headers.get("x-account-id", "").strip()
    if account_id:
        shop = get_shop(request, account_id)
    else:
        shops = request.app.state.registry.list()
        if not shops:
            raise HTTPException(400, "还没有闲鱼账号")
        shop = request.app.state.registry.get("default") or shops[0]
    headers = {}
    content_type = request.headers.get("content-type")
    if content_type:
        headers["content-type"] = content_type
    response = await request.app.state.proxy.forward(
        shop, request.method, f"/api/{path}",
        params=request.query_params, content=await request.body(), headers=headers,
    )
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
    )
