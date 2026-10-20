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


if __name__ == "__main__":
    unittest.main()
