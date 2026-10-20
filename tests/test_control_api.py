"""多账号控制台 API：静态 Web、账号管理、按账号代理。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from yuxiaoer.control.main import app


class ControlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="yx-hub-api-"))
        os.environ["YUXIAOER_CONTROL_DIR"] = str(self.tmp)
        os.environ["YUXIAOER_CONTROL_AUTOSTART"] = "0"

    def test_static_web_and_accounts(self) -> None:
        with TestClient(app) as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("manageAccountsTop", response.text)
            self.assertIn("pearl.css", response.text)

            response = client.get("/api/hub/accounts")
            self.assertEqual(response.status_code, 200)
            self.assertEqual([a["id"] for a in response.json()["accounts"]], ["default"])

            client.app.state.supervisor.start = AsyncMock(return_value={"ok": True})
            response = client.post("/api/hub/accounts", json={"name": "主号"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["account"]["name"], "主号")

            response = client.get("/api/hub/accounts")
            self.assertEqual(len(response.json()["accounts"]), 2)

    def test_api_proxy_uses_selected_account(self) -> None:
        with TestClient(app) as client:
            client.app.state.supervisor.start = AsyncMock(return_value={"ok": True})
            response = client.post("/api/hub/accounts", json={"name": "代理号"})
            shop_id = response.json()["account"]["id"]
            seen = {}

            async def fake_forward(shop, method, path, *, params=None, content=None, headers=None):
                seen.update({"shop": shop.id, "method": method, "path": path, "account": headers})
                return httpx.Response(200, json={"ok": True, "account": shop.id}, request=httpx.Request(method, "http://test"))

            client.app.state.proxy.forward = fake_forward
            response = client.get("/api/status", headers={"X-Account-Id": shop_id})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["account"], shop_id)
            self.assertEqual(seen["path"], "/api/status")

            response = client.get("/api/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(seen["shop"], "default")

    def test_login_proxy(self) -> None:
        with TestClient(app) as client:
            client.app.state.supervisor.start = AsyncMock(return_value={"ok": True})
            response = client.post("/api/hub/accounts", json={"name": "扫码号"})
            shop_id = response.json()["account"]["id"]

            async def fake_request(shop, method, path, json=None):
                if path == "/api/accounts":
                    return [{"id": "acc_1", "status": "offline"}]
                if path.endswith("/login/start"):
                    return {"account_id": "acc_1", "qr_code_url": "data:image/png;base64,x"}
                return {"ok": True}

            client.app.state.proxy.request = fake_request
            response = client.post(f"/api/hub/accounts/{shop_id}/login/start")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["account_id"], "acc_1")


if __name__ == "__main__":
    unittest.main()
