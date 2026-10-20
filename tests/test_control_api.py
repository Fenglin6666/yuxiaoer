"""多账号控制台 API：无登录、账号实例、工作台代理。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from yuxiaoer.control.main import app


class ControlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="yx-control-api-"))
        os.environ["YUXIAOER_CONTROL_DIR"] = str(self.tmp)
        os.environ["YUXIAOER_CONTROL_AUTOSTART"] = "0"

    def test_open_access_and_add_account(self) -> None:
        with TestClient(app) as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("多账号控制台", response.text)

            response = client.get("/api/control/accounts")
            self.assertEqual(response.status_code, 200)
            self.assertEqual([a["id"] for a in response.json()["accounts"]], ["default"])

            client.app.state.supervisor.start = AsyncMock(return_value={"ok": True})
            response = client.post("/api/control/accounts", json={"name": "主号"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["account"]["name"], "主号")

            response = client.get("/api/control/accounts")
            self.assertEqual(len(response.json()["accounts"]), 2)

    def test_workbench_proxy(self) -> None:
        with TestClient(app) as client:
            client.app.state.supervisor.start = AsyncMock(return_value={"ok": True})
            response = client.post("/api/control/accounts", json={"name": "工作台号"})
            shop_id = response.json()["account"]["id"]

            async def fake_request(shop, method, path, json=None):
                if path.startswith("/api/conversations?") and method == "GET":
                    return [{"id": "conv_1", "buyer_nick": "买家A", "item_title": "鞋",
                             "last_text": "在吗", "last_at": "2026-10-20T10:00:00Z"}]
                if path.startswith("/api/conversations/conv_1") and method == "GET":
                    return {"conversation": {"id": "conv_1"},
                            "messages": [{"text": "在吗", "direction": "in"}]}
                if path.endswith("/reply"):
                    return {"ok": True}
                if path == "/api/seller/messages":
                    return {"messages": [], "pending": []}
                if path == "/api/accounts":
                    return [{"id": "acc_1", "nickname": "卖家"}]
                if path.endswith("/login/start"):
                    return {"account_id": "acc_1", "qr_code_url": "data:image/png;base64,x"}
                if path.endswith("/login/status"):
                    return {"account_id": "acc_1", "status": "success"}
                return {"ok": True}

            client.app.state.proxy.request = fake_request
            response = client.get(f"/api/control/workbench/conversations?shop_id={shop_id}")
            self.assertEqual(response.status_code, 200, response.text)
            conversation = response.json()["conversations"][0]
            self.assertEqual(conversation["shop_id"], shop_id)

            response = client.get(f"/api/control/workbench/{shop_id}/conversations/conv_1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["messages"][0]["text"], "在吗")

            response = client.post(
                f"/api/control/workbench/{shop_id}/conversations/conv_1/reply",
                json={"text": "在的"},
            )
            self.assertEqual(response.status_code, 200)

            response = client.post(f"/api/control/accounts/{shop_id}/login/start")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["account_id"], "acc_1")


if __name__ == "__main__":
    unittest.main()
