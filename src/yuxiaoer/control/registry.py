"""闲鱼账号实例注册表：一个实例 = 一个真实闲鱼账号的工作目录。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from yuxiaoer.core import config

DEFAULT_SHOPS: list[dict[str, Any]] = [
    {
        "id": "default",
        "name": "闲鱼账号",
        "port": 8787,
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
        ) / "accounts.json"
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
        allowed = {item.name for item in fields(Shop)}
        self._shops = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            try:
                shop = Shop(**{key: value for key, value in row.items() if key in allowed})
                shop.id = config.normalize_shop_id(shop.id)
                self._shops[shop.id] = shop
            except (TypeError, ValueError):
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([shop.to_dict() for shop in self._shops.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def list(self) -> list[Shop]:
        return sorted(self._shops.values(), key=lambda shop: shop.id)

    def get(self, shop_id: str) -> Shop | None:
        return self._shops.get(config.normalize_shop_id(shop_id))

    def next_port(self) -> int:
        used = {shop.port for shop in self._shops.values()}
        port = 8787
        while port in used:
            port += 1
        return port

    def upsert(self, payload: dict[str, Any]) -> Shop:
        raw_id = str(payload.get("id") or "").strip()
        current = self._shops.get(config.normalize_shop_id(raw_id)) if raw_id else None
        if current:
            shop_id = current.id
        else:
            candidate = config.normalize_shop_id(raw_id or str(payload.get("name") or ""))
            shop_id = "acct_" + candidate if candidate != "default" else f"acct_{len(self._shops) + 1}"
            if shop_id == "acct_default":
                shop_id = f"acct_{len(self._shops) + 1}"
            if not raw_id:
                current = self._shops.get(shop_id)
        port = int(payload.get("port") or (current.port if current else self.next_port()))
        if not 1 <= port <= 65535:
            raise ValueError("端口必须在 1-65535")
        for other in self._shops.values():
            if other.id != shop_id and other.port == port:
                raise ValueError(f"端口 {port} 已被账号 {other.id} 使用")
        data = current.to_dict() if current else {}
        data.update({
            "id": shop_id,
            "name": str(payload.get("name") or data.get("name") or "闲鱼账号").strip()[:80],
            "port": port,
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
