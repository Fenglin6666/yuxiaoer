"""店铺注册表：JSON 持久化，一店一条记录。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from yuxiaoer.core import config

DEFAULT_SHOPS: list[dict[str, Any]] = [
    {
        "id": "default",
        "name": "我的店",
        "port": 8787,
        "owner": "admin",
        "enabled": True,
        "auto_start": True,
        "auto_restart": True,
        "polish_time": "10:05",
        "daily_report_time": "21:00",
        "sync_time": "09:00",
        "note": "",
    }
]


@dataclass
class Shop:
    id: str
    name: str
    port: int
    owner: str = "admin"
    enabled: bool = True
    auto_start: bool = True
    auto_restart: bool = True
    polish_time: str = "10:05"
    daily_report_time: str = "21:00"
    sync_time: str = "09:00"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ShopRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(
            os.getenv("YUXIAOER_CONTROL_DIR", config.PROJECT_ROOT / "data" / "control")
        ) / "shops.json"
        self._shops: dict[str, Shop] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._shops = {shop["id"]: Shop(**shop) for shop in DEFAULT_SHOPS}
            self.save()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = []
        self._shops = {}
        for row in data:
            try:
                shop = Shop(**row)
                shop.id = config.normalize_shop_id(shop.id)
                self._shops[shop.id] = shop
            except TypeError:
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([shop.to_dict() for shop in self._shops.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def list(
        self, *, owner: str | None = None, is_admin: bool = False,
        allowed: list[str] | None = None,
    ) -> list[Shop]:
        shops = sorted(self._shops.values(), key=lambda shop: shop.id)
        if is_admin or (allowed and "*" in allowed):
            return shops
        if allowed is not None:
            return [shop for shop in shops if shop.id in allowed]
        if owner:
            return [shop for shop in shops if shop.owner == owner]
        return shops

    def get(self, shop_id: str) -> Shop | None:
        return self._shops.get(config.normalize_shop_id(shop_id))

    def upsert(self, payload: dict[str, Any]) -> Shop:
        shop_id = config.normalize_shop_id(str(payload.get("id") or ""))
        if not shop_id:
            raise ValueError("店铺 ID 不能为空")
        port = int(payload.get("port") or 0)
        if not 1 <= port <= 65535:
            raise ValueError("端口必须在 1-65535")
        for other in self._shops.values():
            if other.id != shop_id and other.port == port:
                raise ValueError(f"端口 {port} 已被店铺 {other.id} 使用")
        current = self._shops.get(shop_id)
        data = current.to_dict() if current else {}
        data.update({
            "id": shop_id,
            "name": str(payload.get("name") or data.get("name") or shop_id).strip()[:80],
            "port": port,
            "owner": str(payload.get("owner") or data.get("owner") or "admin").strip()[:40],
            "enabled": bool(payload.get("enabled", data.get("enabled", True))),
            "auto_start": bool(payload.get("auto_start", data.get("auto_start", True))),
            "auto_restart": bool(payload.get("auto_restart", data.get("auto_restart", True))),
            "polish_time": str(payload.get("polish_time") or data.get("polish_time") or "10:05"),
            "daily_report_time": str(payload.get("daily_report_time") or data.get("daily_report_time") or "21:00"),
            "sync_time": str(payload.get("sync_time") or data.get("sync_time") or "09:00"),
            "note": str(payload.get("note") or data.get("note") or "")[:500],
        })
        shop = Shop(**data)
        self._shops[shop.id] = shop
        self.save()
        return shop

    def delete(self, shop_id: str) -> bool:
        shop_id = config.normalize_shop_id(shop_id)
        if shop_id not in self._shops:
            return False
        self._shops.pop(shop_id)
        self.save()
        return True
