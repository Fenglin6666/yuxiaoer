"""控制台可选 Basic Auth 测试。"""

from __future__ import annotations

import base64
import unittest

import httpx

from yuxiaoer.core import config
from yuxiaoer.main import app


def _auth(user: str, password: str) -> dict[str, str]:
    raw = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


class ConsoleAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._user, self._password = config.CONSOLE_USER, config.CONSOLE_PASSWORD
        config.CONSOLE_USER = "owner"
        config.CONSOLE_PASSWORD = "secret"
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://test")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        config.CONSOLE_USER, config.CONSOLE_PASSWORD = self._user, self._password

    async def test_rejects_without_credentials(self) -> None:
        r = await self.client.get("/openapi.json")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Basic", r.headers.get("www-authenticate", ""))

    async def test_rejects_wrong_credentials(self) -> None:
        r = await self.client.get("/openapi.json", headers=_auth("owner", "nope"))
        self.assertEqual(r.status_code, 401)

    async def test_accepts_correct_credentials(self) -> None:
        r = await self.client.get("/openapi.json", headers=_auth("owner", "secret"))
        self.assertEqual(r.status_code, 200)

    async def test_health_and_external_are_exempt(self) -> None:
        r = await self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)

    async def test_disabled_when_unset(self) -> None:
        config.CONSOLE_USER = ""
        config.CONSOLE_PASSWORD = ""
        r = await self.client.get("/openapi.json")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
