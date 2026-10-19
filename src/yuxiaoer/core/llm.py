"""LLM 网关：OpenAI 兼容端点，可选、可熔断、失败自动降级为规则模式。

产品默认规则模式即可跑通全部闭环；配置 LLM_API_KEY 后可开启润色/理解增强。
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from yuxiaoer.core import config
from yuxiaoer.core.db import Database
from yuxiaoer.core.util import iso


class LLMClient:
    def __init__(self, db: Database):
        self.db = db
        self.key = config.LLM_API_KEY
        self.base_url = config.LLM_BASE_URL
        self.model = config.LLM_MODEL
        self.enabled_pref = config.LLM_ENABLED
        self.calls = 0
        self.failures = 0
        self.last_error: str | None = None
        self.last_success_at: str | None = None
        self.cooldown_until = 0.0

    def has_key(self) -> bool:
        return bool(self.key)

    def available(self) -> bool:
        if not self.has_key():
            return False
        if self.enabled_pref == "off":
            return False
        return time.time() >= self.cooldown_until

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str = "chat",
        temperature: float = 0.5,
        max_tokens: int = 500,
        json_mode: bool = False,
    ) -> str | None:
        if not self.available():
            return None
        started = time.time()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:180]}")
            data = resp.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = content.strip()
            if not content:
                raise RuntimeError("空响应")
            self.calls += 1
            self.last_success_at = iso()
            self.last_error = None
            await self._log(purpose, True, int((time.time() - started) * 1000), None)
            return content
        except Exception as exc:  # noqa: BLE001
            self.calls += 1
            self.failures += 1
            self.last_error = str(exc)[:300]
            self.cooldown_until = time.time() + config.LLM_COOLDOWN_SECONDS
            await self._log(purpose, False, int((time.time() - started) * 1000), self.last_error)
            return None

    async def _log(self, purpose: str, ok: bool, latency_ms: int, error: str | None) -> None:
        try:
            await self.db.execute(
                "INSERT INTO llm_calls(purpose,ok,latency_ms,error,created_at) VALUES(?,?,?,?,?)",
                (purpose, 1 if ok else 0, latency_ms, error, iso()),
            )
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        if not self.has_key():
            mode = "未配置（规则模式）"
        elif not self.available():
            mode = "熔断冷却（规则模式）"
        elif self.enabled_pref == "off":
            mode = "已配置但关闭（规则模式）"
        else:
            mode = f"在线 · {self.model}"
        return {
            "has_key": self.has_key(),
            "enabled": self.available(),
            "mode": mode,
            "model": self.model,
            "base_url": self.base_url,
            "calls": self.calls,
            "failures": self.failures,
            "last_error": self.last_error,
            "last_success_at": self.last_success_at,
        }
