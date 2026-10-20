"""多账号注册表与排期抖动测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yuxiaoer.control.registry import ShopRegistry
from yuxiaoer.control.scheduler import jittered_time


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="yx-control-")) / "accounts.json"
        self.registry = ShopRegistry(self.tmp)

    def test_seed_default(self) -> None:
        self.assertIsNotNone(self.registry.get("default"))

    def test_add_account_auto_port(self) -> None:
        shop = self.registry.upsert({"name": "主号"})
        self.assertEqual(shop.port, 8802)
        self.assertNotEqual(shop.id, "default")
        self.assertEqual(self.registry.get(shop.id).name, "主号")

    def test_explicit_port_conflict(self) -> None:
        self.registry.upsert({"id": "a", "name": "A", "port": 8788})
        with self.assertRaises(ValueError):
            self.registry.upsert({"id": "b", "name": "B", "port": 8788})

    def test_delete(self) -> None:
        shop = self.registry.upsert({"name": "临时"})
        self.assertTrue(self.registry.delete(shop.id))
        self.assertIsNone(self.registry.get(shop.id))


class JitterTests(unittest.TestCase):
    def test_deterministic_and_bounded(self) -> None:
        first = jittered_time("10:05", "acct_1", jitter_minutes=20)
        second = jittered_time("10:05", "acct_1", jitter_minutes=20)
        self.assertEqual(first, second)
        hour, minute = (int(x) for x in first.split(":"))
        self.assertTrue(0 <= hour < 24 and 0 <= minute < 60)

    def test_accounts_are_staggered(self) -> None:
        times = {jittered_time("10:05", f"acct_{i}") for i in range(8)}
        self.assertGreater(len(times), 1)


if __name__ == "__main__":
    unittest.main()
