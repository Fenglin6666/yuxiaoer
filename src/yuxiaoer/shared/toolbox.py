"""工具调用记录器：统一契约 + 步数上限 + 重复调用检测。"""

from __future__ import annotations

import inspect
import json
import logging
import time
from typing import Any, Awaitable, Callable

from yuxiaoer.core.db import Database
from yuxiaoer.core.util import dumps, iso

log = logging.getLogger("yuxiaoer.tools")


class ToolBox:
    """工具调用记录器：统一契约 + 步数上限 + 重复调用检测。"""

    def __init__(self, db: Database, *, turn_id: str, session_id: str, agent: str, limit: int):
        self.db = db
        self.turn_id = turn_id
        self.session_id = session_id
        self.agent = agent
        self.limit = limit
        self.steps = 0
        self.last_key: str | None = None
        self.repeat = False
        self.calls: list[dict[str, Any]] = []

    async def call(
        self,
        name: str,
        args: dict[str, Any],
        fn: Callable[[], Awaitable[Any]],
    ) -> dict[str, Any]:
        self.steps += 1
        if self.steps > self.limit:
            return {"ok": False, "error": "工具步数超限", "error_type": "logic"}
        key = name + ":" + json.dumps(args, ensure_ascii=False, sort_keys=True)
        if key == self.last_key:
            self.repeat = True
        self.last_key = key
        started = time.monotonic()
        ok = True
        error = None
        try:
            data = fn()
            if inspect.isawaitable(data):
                data = await data
        except Exception as exc:  # noqa: BLE001
            ok = False
            data = None
            error = str(exc)
            log.warning("tool %s failed: %s", name, exc)
        latency = int((time.monotonic() - started) * 1000)
        result = {"ok": ok, "data": data}
        if error:
            result["error"] = error
        await self.db.execute(
            "INSERT INTO tool_calls(turn_id,session_id,agent,tool,args_json,result_json,ok,error,latency_ms,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (self.turn_id, self.session_id, self.agent, name, dumps(args),
             dumps(result)[:8000], 1 if ok else 0, error, latency, iso()),
        )
        self.calls.append({"tool": name, "args": args, "ok": ok, "latency_ms": latency,
                           "result": data if ok else None, "error": error})
        return result
