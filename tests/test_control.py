"""控制面基础件测试：注册表、鉴权、排期抖动。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yuxiaoer.control.auth import ControlUser, UserRegistry, hash_password, verify_password
from yuxiaoer.control.registry import ShopRegistry
from yuxiaoer.control.scheduler import jittered_time

import os


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="yx-control-")) / "shops.json"
        self.registry = ShopRegistry(self.tmp)

    def test_seed_default(self) -> None:
        self.assertIsNotNone(self.registry.get("default"))

    def test_upsert_and_port_conflict(self) -> None:
        self.registry.upsert({"id": "shop-b", "name": "B", "port": 8788, "owner": "alice"})
        self.assertEqual(self.registry.get("shop-b").name, "B")
        with self.assertRaises(ValueError):
            self.registry.upsert({"id": "shop-c", "name": "C", "port": 8788})

    def test_owner_filter(self) -> None:
        self.registry.upsert({"id": "shop-b", "name": "B", "port": 8788, "owner": "alice"})
        self.assertEqual([s.id for s in self.registry.list(owner="alice")], ["shop-b"])
        self.assertEqual(len(self.registry.list(is_admin=True)), 2)


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["YUXIAOER_CONTROL_PASSWORD"] = "admin"
        self.tmp = Path(tempfile.mkdtemp(prefix="yx-users-")) / "users.json"
        self.users = UserRegistry(self.tmp)

    def test_password_hash(self) -> None:
        stored = hash_password("secret")
        self.assertTrue(verify_password("secret", stored))
        self.assertFalse(verify_password("wrong", stored))

    def test_owner_access(self) -> None:
        user = ControlUser("alice", "x", "owner", ["shop-b"])
        self.assertTrue(user.can_access("shop-b"))
        self.assertFalse(user.can_access("shop-c"))
        admin = ControlUser("admin", "x", "admin", ["*"])
        self.assertTrue(admin.can_access("anything"))

    def test_create_and_authenticate(self) -> None:
        self.users.upsert("alice", "pw", "owner", ["shop-b"])
        self.assertIsNotNone(self.users.authenticate("alice", "pw"))
        self.assertIsNone(self.users.authenticate("alice", "bad"))

    def test_admin_password_env_default(self) -> None:
        self.assertIsNotNone(self.users.authenticate("admin", "admin"))


class JitterTests(unittest.TestCase):
    def test_deterministic_and_bounded(self) -> None:
        first = jittered_time("10:05", "shop-b", jitter_minutes=20)
        second = jittered_time("10:05", "shop-b", jitter_minutes=20)
        self.assertEqual(first, second)
        hour, minute = (int(x) for x in first.split(":"))
        self.assertTrue(0 <= hour < 24 and 0 <= minute < 60)

    def test_shops_are_staggered(self) -> None:
        times = {jittered_time("10:05", f"shop-{i}") for i in range(8)}
        self.assertGreater(len(times), 1)


if __name__ == "__main__":
    unittest.main()
