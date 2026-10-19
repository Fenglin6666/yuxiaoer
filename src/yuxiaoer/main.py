"""FastAPI 入口：`python -m uvicorn yuxiaoer.main:app --port 8787`."""

from __future__ import annotations

import base64
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from yuxiaoer.core import config
from .api import router
from yuxiaoer.seller.integrations.external_api import router as external_router
from .runtime import runtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s · %(message)s",
)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runtime.initialize()
    yield
    await runtime.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="鱼小二 · 托管客服", version=config.VERSION, lifespan=lifespan)
    app.include_router(router)
    app.include_router(external_router)

    @app.middleware("http")
    async def console_auth(request: Request, call_next):
        """可选 Basic Auth：配置了用户名+密码才启用。

        健康检查与外部接口（自带共享秘钥）不拦截；其余控制台路由要求 Basic 凭据，
        浏览器访问 UI 时会自动弹一次登录框。
        """
        user, password = config.CONSOLE_USER, config.CONSOLE_PASSWORD
        path = request.url.path
        if not user or not password or path == "/api/health" or path.startswith("/api/v1/external/"):
            return await call_next(request)
        header = request.headers.get("authorization", "")
        if header.startswith("Basic "):
            try:
                supplied = base64.b64decode(header[6:]).decode("utf-8")
                supplied_user, sep, supplied_password = supplied.partition(":")
                if (
                    sep
                    and secrets.compare_digest(supplied_user.encode(), user.encode())
                    and secrets.compare_digest(supplied_password.encode(), password.encode())
                ):
                    return await call_next(request)
            except (ValueError, UnicodeDecodeError):
                pass
        return Response(
            "Unauthorized",
            status_code=401,
            media_type="text/plain",
            headers={"WWW-Authenticate": 'Basic realm="yuxiaoer", charset="UTF-8"'},
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logging.exception("unhandled API error: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico")
    async def favicon():
        return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")

    return app


app = create_app()
