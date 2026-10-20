"""店铺进程守护：启动、健康检查、退出重启。"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from yuxiaoer.core import config

from .registry import Shop, ShopRegistry

log = logging.getLogger("yuxiaoer.control.supervisor")


class ShopSupervisor:
    def __init__(self, registry: ShopRegistry, *, project_root: Path | None = None):
        self.registry = registry
        self.project_root = project_root or config.PROJECT_ROOT
        self.log_dir = Path(
            os.getenv("YUXIAOER_CONTROL_DIR", self.project_root / "data" / "control")
        ) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._monitor: asyncio.Task | None = None
        self._stopping = False

    def _shop_state(self, shop: Shop) -> dict[str, Any]:
        return self._state.setdefault(shop.id, {
            "process": None,
            "desired": False,
            "restarts": 0,
            "failures": 0,
            "last_error": "",
            "started_at": None,
        })

    def _lock(self, shop_id: str) -> asyncio.Lock:
        return self._locks.setdefault(shop_id, asyncio.Lock())

    def base_url(self, shop: Shop) -> str:
        return f"http://127.0.0.1:{shop.port}"

    async def start(self, shop: Shop) -> dict[str, Any]:
        async with self._lock(shop.id):
            state = self._shop_state(shop)
            state["desired"] = True
            process = state.get("process")
            if process is not None and process.poll() is None:
                return {"ok": True, "message": "already running", "pid": process.pid}
            if process is not None:
                state["process"] = None
                handle = state.pop("log_handle", None)
                if handle:
                    handle.close()
            log_path = self.log_dir / f"{shop.id}.log"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root / "src")
            env["YUXIAOER_SHOP_ID"] = shop.id
            env["YUXIAOER_PORT"] = str(shop.port)
            env["YUXIAOER_SHOPS_DIR"] = str(config.SHOPS_DIR)
            cmd = [
                sys.executable, "-m", "uvicorn", "yuxiaoer.main:app",
                "--host", "127.0.0.1", "--port", str(shop.port),
            ]
            try:
                handle = log_path.open("ab")
                process = subprocess.Popen(
                    cmd, cwd=str(self.project_root), env=env,
                    stdout=handle, stderr=subprocess.STDOUT,
                    creationflags=0,
                )
            except Exception as exc:  # noqa: BLE001
                state["last_error"] = str(exc)
                return {"ok": False, "error": str(exc)}
            state.update({
                "process": process,
                "log_handle": handle,
                "started_at": time.time(),
                "last_error": "",
            })
            log.info("shop %s started pid=%s port=%s", shop.id, process.pid, shop.port)
            return {"ok": True, "pid": process.pid, "port": shop.port, "log": str(log_path)}

    async def stop(self, shop: Shop, *, desired: bool = False) -> dict[str, Any]:
        async with self._lock(shop.id):
            state = self._shop_state(shop)
            state["desired"] = desired
            process = state.get("process")
            if process is None or process.poll() is not None:
                state["process"] = None
                return {"ok": True, "message": "already stopped"}
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 8)
            except subprocess.TimeoutExpired:
                process.kill()
            state["process"] = None
            handle = state.pop("log_handle", None)
            if handle:
                handle.close()
            return {"ok": True, "message": "stopped"}

    async def restart(self, shop: Shop) -> dict[str, Any]:
        await self.stop(shop, desired=False)
        await asyncio.sleep(0.3)
        return await self.start(shop)

    async def health(self, shop: Shop) -> dict[str, Any]:
        try:
            auth = None
            if config.CONSOLE_USER and config.CONSOLE_PASSWORD:
                auth = (config.CONSOLE_USER, config.CONSOLE_PASSWORD)
            async with httpx.AsyncClient(timeout=3.0, auth=auth) as client:
                response = await client.get(f"{self.base_url(shop)}/api/health")
                return {
                    "online": response.status_code == 200,
                    "status_code": response.status_code,
                    "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else {},
                }
        except Exception as exc:  # noqa: BLE001
            return {"online": False, "error": str(exc)[:200]}

    async def status(self, shop: Shop) -> dict[str, Any]:
        state = self._shop_state(shop)
        process = state.get("process")
        running = process is not None and process.poll() is None
        health = await self.health(shop) if running else {"online": False}
        return {
            "id": shop.id,
            "name": shop.name,
            "port": shop.port,
            "enabled": shop.enabled,
            "auto_start": shop.auto_start,
            "auto_restart": shop.auto_restart,
            "running": running,
            "pid": process.pid if running else None,
            "health": health,
            "restarts": state["restarts"],
            "last_error": state["last_error"],
        }

    async def monitor_loop(self) -> None:
        interval = max(5, int(os.getenv("YUXIAOER_CONTROL_HEALTH_INTERVAL", "10")))
        while not self._stopping:
            for shop in self.registry.list():
                if not shop.enabled:
                    continue
                try:
                    await self._check(shop)
                except Exception:  # noqa: BLE001
                    log.exception("monitor shop %s failed", shop.id)
            await asyncio.sleep(interval)

    async def _check(self, shop: Shop) -> None:
        state = self._shop_state(shop)
        process = state.get("process")
        restarted = False
        if process is None:
            if state["desired"] and shop.auto_start:
                await self.start(shop)
                return
            return
        if process.poll() is not None:
            state["process"] = None
            handle = state.pop("log_handle", None)
            if handle:
                handle.close()
            state["last_error"] = f"进程退出码 {process.returncode}"
            if shop.auto_restart and state["desired"]:
                state["restarts"] += 1
                await self.start(shop)
                restarted = True
            else:
                state["desired"] = False
            if restarted:
                return
        if state.get("process") is None:
            return
        health = await self.health(shop)
        if health.get("online"):
            state["failures"] = 0
            return
        state["failures"] += 1
        state["last_error"] = health.get("error", "health check failed")
        if state["failures"] >= 3 and shop.auto_restart and state["desired"]:
            state["failures"] = 0
            state["restarts"] += 1
            await self.restart(shop)

    async def start_all(self) -> None:
        for shop in self.registry.list():
            if shop.enabled and shop.auto_start:
                await self.start(shop)

    async def stop_all(self) -> None:
        for shop in self.registry.list():
            if self._state.get(shop.id, {}).get("process") is not None:
                await self.stop(shop, desired=False)

    def start_monitor(self) -> None:
        if self._monitor is None or self._monitor.done():
            self._stopping = False
            self._monitor = asyncio.create_task(self.monitor_loop(), name="shop-monitor")

    async def shutdown(self) -> None:
        self._stopping = True
        if self._monitor:
            self._monitor.cancel()
            try:
                await self._monitor
            except (asyncio.CancelledError, Exception):
                pass
            self._monitor = None
        await self.stop_all()
