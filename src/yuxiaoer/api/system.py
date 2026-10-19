"""系统状态：健康检查、运行状态、总览、指标。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..core import config
from ..core.util import iso
from ..runtime import runtime

router = APIRouter()

@router.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "app": config.APP_NAME, "version": config.VERSION, "time": iso()}


@router.get("/status")
async def status() -> dict[str, Any]:
    return await runtime.system_status()


@router.get("/overview")
async def overview() -> dict[str, Any]:
    return await runtime.overview()


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    return await runtime.metrics.overview()
