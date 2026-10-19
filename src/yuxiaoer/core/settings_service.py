"""运行时可调设置（DB settings 表 + 默认值）。"""

from __future__ import annotations

from typing import Any

from yuxiaoer.core import config
from yuxiaoer.core.db import Database


class SettingsService:
    def __init__(self, db: Database):
        self.db = db

    async def get(self, key: str) -> str:
        value = await self.db.fetchval("SELECT value FROM settings WHERE key=?", (key,))
        if value is None:
            return config.DEFAULT_SETTINGS.get(key, "")
        return str(value)

    async def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(float(await self.get(key) or default))
        except (TypeError, ValueError):
            return default

    async def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(await self.get(key) or default)
        except (TypeError, ValueError):
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        raw = (await self.get(key)).strip().lower()
        if not raw:
            return default
        return raw in ("1", "true", "yes", "on")

    async def set(self, key: str, value: Any) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value))
        )

    async def all(self) -> dict[str, str]:
        rows = await self.db.fetchall("SELECT key,value FROM settings")
        return {r["key"]: r["value"] for r in rows}

    async def public(self) -> dict[str, Any]:
        data = await self.all()
        public = dict(config.DEFAULT_SETTINGS)
        public.update({k: v for k, v in data.items() if k in config.EDITABLE_SETTINGS})
        return public
