"""设置读写。"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException

from ..core import config
from ..runtime import runtime
from ._models import SettingsIn

router = APIRouter()

@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    return {
        "values": await runtime.settings.public(),
        "llm": runtime.llm.status(),
        "system": await runtime.system_status(),
        "editable": sorted(config.EDITABLE_SETTINGS),
    }


@router.post("/settings")
async def set_settings(payload: SettingsIn) -> dict[str, Any]:
    for key, value in payload.values.items():
        if key not in config.EDITABLE_SETTINGS:
            continue
        if key == "floor_discount_pct":
            value = max(50, min(100, int(value)))
        if key == "merge_window_seconds":
            value = max(0.0, min(30.0, float(value)))
        if key in ("night_mode", "auto_relist", "auto_review", "human_typing"):
            value = 1 if str(value).lower() in ("1", "true", "on", "yes") else 0
        if key == "relist_limit":
            value = max(1, min(100, int(value)))
        if key == "bargain_max_rounds":
            value = max(1, min(10, int(value)))
        if key == "risk_cooldown_minutes":
            value = max(1, min(180, int(value)))
        if key in ("polish_time", "daily_report_time"):
            value = str(value).strip()
            if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", value):
                raise HTTPException(400, "时间格式应为 HH:MM")
        if key == "llm_enabled" and str(value).lower() in ("1", "true", "on", "yes") and not runtime.llm.has_key():
            raise HTTPException(400, "未配置 LLM_API_KEY，无法开启 LLM 模式")
        await runtime.settings.set(key, value)
    if "polish_time" in payload.values:
        await runtime.patrol.update_job("polish", local_time=str(payload.values["polish_time"]))
    if "daily_report_time" in payload.values:
        await runtime.patrol.update_job("daily_report", local_time=str(payload.values["daily_report_time"]))
    await runtime.apply_settings()
    await runtime.knowledge.sync_all_items()
    return {"ok": True, "values": await runtime.settings.public(), "llm": runtime.llm.status()}
