"""FastAPI 入口：`python -m uvicorn yuxiaoer.main:app --port 8787`."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
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
