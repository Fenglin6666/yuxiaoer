"""多店控制面：注册表、进程守护、排期、汇总、按店权限。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .aggregator import ShopAggregator
from .auth import ControlUser, UserRegistry
from .registry import ShopRegistry
from .scheduler import ShopScheduler
from .supervisor import ShopSupervisor

security = HTTPBasic(auto_error=False)
STATIC = Path(__file__).parent / "static" / "control.html"


def current_user(request: Request, credentials: HTTPBasicCredentials | None = Depends(security)) -> ControlUser:
    if credentials is None:
        raise HTTPException(401, "需要登录", headers={"WWW-Authenticate": "Basic"})
    user = request.app.state.users.authenticate(credentials.username, credentials.password)
    if user is None:
        raise HTTPException(401, "用户名或密码错误", headers={"WWW-Authenticate": "Basic"})
    return user


def admin_only(user: ControlUser = Depends(current_user)) -> ControlUser:
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


def allowed_shop(request: Request, user: ControlUser, shop_id: str):
    shop = request.app.state.registry.get(shop_id)
    if shop is None or not user.can_access(shop.id):
        raise HTTPException(404, "店铺不存在")
    return shop


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.registry = ShopRegistry()
    app.state.users = UserRegistry()
    app.state.supervisor = ShopSupervisor(app.state.registry)
    app.state.scheduler = ShopScheduler(app.state.registry)
    app.state.aggregator = ShopAggregator()
    app.state.supervisor.start_monitor()
    app.state.scheduler.start()
    if os.getenv("YUXIAOER_CONTROL_AUTOSTART", "1") not in ("0", "false", "off"):
        await app.state.supervisor.start_all()
    yield
    await app.state.scheduler.shutdown()
    await app.state.supervisor.shutdown()


app = FastAPI(title="鱼小二 · 多店控制面", lifespan=lifespan)


@app.get("/")
async def index(user: ControlUser = Depends(current_user)):
    return FileResponse(STATIC)


@app.get("/api/control/me")
async def me(user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    return {"username": user.username, "role": user.role, "shops": user.shops}


@app.get("/api/control/shops")
async def list_shops(request: Request, user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    shops = request.app.state.registry.list(
        owner=user.username, is_admin=user.role == "admin", allowed=user.shops
    )
    rows = [await request.app.state.supervisor.status(shop) for shop in shops]
    return {"shops": rows}


@app.post("/api/control/shops")
async def upsert_shop(request: Request, payload: dict[str, Any], user: ControlUser = Depends(admin_only)) -> dict[str, Any]:
    try:
        shop = request.app.state.registry.upsert(payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    request.app.state.scheduler.invalidate(shop.id)
    if payload.get("auto_start"):
        await request.app.state.supervisor.start(shop)
    return {"ok": True, "shop": shop.to_dict()}


@app.delete("/api/control/shops/{shop_id}")
async def delete_shop(request: Request, shop_id: str, user: ControlUser = Depends(admin_only)) -> dict[str, Any]:
    shop = request.app.state.registry.get(shop_id)
    if shop is not None:
        await request.app.state.supervisor.stop(shop)
    if not request.app.state.registry.delete(shop_id):
        raise HTTPException(404, "店铺不存在")
    return {"ok": True}


async def _shop_action(request: Request, user: ControlUser, shop_id: str, action: str) -> dict[str, Any]:
    shop = allowed_shop(request, user, shop_id)
    supervisor = request.app.state.supervisor
    if action == "start":
        return await supervisor.start(shop)
    if action == "stop":
        return await supervisor.stop(shop)
    if action == "restart":
        return await supervisor.restart(shop)
    raise HTTPException(400, "未知操作")


@app.post("/api/control/shops/{shop_id}/start")
async def start_shop(request: Request, shop_id: str, user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    return await _shop_action(request, user, shop_id, "start")


@app.post("/api/control/shops/{shop_id}/stop")
async def stop_shop(request: Request, shop_id: str, user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    return await _shop_action(request, user, shop_id, "stop")


@app.post("/api/control/shops/{shop_id}/restart")
async def restart_shop(request: Request, shop_id: str, user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    return await _shop_action(request, user, shop_id, "restart")


@app.post("/api/control/shops/{shop_id}/sync")
async def sync_shop(request: Request, shop_id: str, user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    shop = allowed_shop(request, user, shop_id)
    return await request.app.state.scheduler.sync_shop_items(shop)


@app.post("/api/control/shops/{shop_id}/schedule")
async def schedule_shop(request: Request, shop_id: str, user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    shop = allowed_shop(request, user, shop_id)
    return await request.app.state.scheduler.apply_schedule(shop)


@app.get("/api/control/overview")
async def overview(request: Request, user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    shops = request.app.state.registry.list(
        owner=user.username, is_admin=user.role == "admin", allowed=user.shops
    )
    return await request.app.state.aggregator.overview(shops)


@app.get("/api/control/alerts")
async def alerts(request: Request, status: str = "open", user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    shops = request.app.state.registry.list(
        owner=user.username, is_admin=user.role == "admin", allowed=user.shops
    )
    return {"alerts": await request.app.state.aggregator.alerts(shops, status)}


@app.get("/api/control/daily")
async def daily(request: Request, user: ControlUser = Depends(current_user)) -> dict[str, Any]:
    shops = request.app.state.registry.list(
        owner=user.username, is_admin=user.role == "admin", allowed=user.shops
    )
    return await request.app.state.aggregator.daily(shops)


@app.get("/api/control/users")
async def list_users(request: Request, user: ControlUser = Depends(admin_only)) -> dict[str, Any]:
    return {
        "users": [
            {"username": item.username, "role": item.role, "shops": item.shops}
            for item in request.app.state.users.list()
        ]
    }


@app.post("/api/control/users")
async def upsert_user(request: Request, payload: dict[str, Any], user: ControlUser = Depends(admin_only)) -> dict[str, Any]:
    try:
        item = request.app.state.users.upsert(
            str(payload.get("username") or ""),
            payload.get("password"),
            str(payload.get("role") or "owner"),
            [str(shop) for shop in payload.get("shops") or []],
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "user": {"username": item.username, "role": item.role, "shops": item.shops}}


@app.delete("/api/control/users/{username}")
async def delete_user(request: Request, username: str, user: ControlUser = Depends(admin_only)) -> dict[str, Any]:
    try:
        if not request.app.state.users.delete(username):
            raise HTTPException(404, "用户不存在")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}
