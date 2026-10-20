"""控制面 API：鉴权、按店可见性、注册表。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from yuxiaoer.control.main import app


class ControlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="yx-control-api-"))
        os.environ["YUXIAOER_CONTROL_DIR"] = str(self.tmp)
        os.environ["YUXIAOER_CONTROL_PASSWORD"] = "admin"
        os.environ["YUXIAOER_CONTROL_AUTH"] = "1"
        os.environ["YUXIAOER_CONTROL_AUTOSTART"] = "0"

    def test_admin_and_owner_isolation(self) -> None:
        with TestClient(app) as client:
            admin = ("admin", "admin")
            response = client.get("/api/control/shops", auth=admin)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([s["id"] for s in response.json()["shops"]], ["default"])

            for shop_id, port, owner in (("shop-b", 8899, "bob"), ("shop-c", 8900, "bob")):
                response = client.post(
                    "/api/control/shops",
                    auth=admin,
                    json={"id": shop_id, "name": shop_id, "port": port, "owner": owner, "auto_start": False},
                )
                self.assertEqual(response.status_code, 200, response.text)

            response = client.post(
                "/api/control/users",
                auth=admin,
                json={"username": "alice", "password": "pw", "role": "owner", "shops": ["shop-b"]},
            )
            self.assertEqual(response.status_code, 200, response.text)

            response = client.get("/api/control/shops", auth=("alice", "pw"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual([s["id"] for s in response.json()["shops"]], ["shop-b"])

            response = client.post("/api/control/shops/shop-c/start", auth=("alice", "pw"))
            self.assertEqual(response.status_code, 404)

    def test_requires_login(self) -> None:
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/control/shops").status_code, 401)
            self.assertEqual(client.get("/").status_code, 401)
            response = client.get("/", auth=("admin", "admin"))
            self.assertEqual(response.status_code, 200)
            self.assertIn("多店控制台", response.text)

    def test_workbench_proxy(self) -> None:
        with TestClient(app) as client:
            admin = ("admin", "admin")
            response = client.post(
                "/api/control/shops",
                auth=admin,
                json={"id": "shop-wb", "name": "工作台店", "port": 8901, "auto_start": False},
            )
            self.assertEqual(response.status_code, 200, response.text)

            async def fake_request(shop, method, path, json=None):
                if path.startswith("/api/conversations?") and method == "GET":
                    return [{"id": "conv_1", "buyer_nick": "买家A", "item_title": "鞋", "last_text": "在吗", "last_at": "2026-10-20T10:00:00Z"}]
                if path.startswith("/api/conversations/conv_1") and method == "GET":
                    return {"conversation": {"id": "conv_1"}, "messages": [{"text": "在吗", "direction": "in"}]}
                if path.endswith("/reply"):
                    return {"ok": True}
                if path == "/api/seller/messages":
                    return {"messages": [], "pending": []}
                return {"ok": True}

            client.app.state.proxy.request = fake_request
            response = client.get("/api/control/workbench/conversations?shop_id=shop-wb", auth=admin)
            self.assertEqual(response.status_code, 200, response.text)
            conversation = response.json()["conversations"][0]
            self.assertEqual(conversation["shop_id"], "shop-wb")
            self.assertEqual(conversation["shop_name"], "工作台店")

            response = client.get("/api/control/workbench/shop-wb/conversations/conv_1", auth=admin)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["messages"][0]["text"], "在吗")

            response = client.post(
                "/api/control/workbench/shop-wb/conversations/conv_1/reply",
                auth=admin, json={"text": "在的"},
            )
            self.assertEqual(response.status_code, 200)


class ControlOpenAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="yx-control-open-"))
        os.environ["YUXIAOER_CONTROL_DIR"] = str(self.tmp)
        os.environ["YUXIAOER_CONTROL_AUTH"] = "0"
        os.environ["YUXIAOER_CONTROL_AUTOSTART"] = "0"

    def test_direct_access_without_password(self) -> None:
        with TestClient(app) as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("多店控制台", response.text)
            me = client.get("/api/control/me")
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["username"], "local")
            self.assertEqual(client.get("/api/control/shops").status_code, 200)


if __name__ == "__main__":
    unittest.main()