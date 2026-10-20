"""店铺实例隔离：ID 归一化与数据目录。"""

from __future__ import annotations

import unittest

from yuxiaoer.core import config


class ShopConfigTests(unittest.TestCase):
    def test_default_shop_uses_data_dir(self) -> None:
        self.assertEqual(config.shop_data_dir("default"), config.PROJECT_ROOT / "data")

    def test_custom_shop_uses_shops_dir(self) -> None:
        self.assertEqual(config.shop_data_dir("shop-a"), config.SHOPS_DIR / "shop-a")

    def test_shop_id_is_sanitized(self) -> None:
        self.assertEqual(config.normalize_shop_id(" shop/../A "), "shop-A")
        self.assertEqual(config.normalize_shop_id(""), "default")
        self.assertEqual(config.normalize_shop_id("中文店"), "default")

    def test_shop_id_length_cap(self) -> None:
        self.assertEqual(len(config.normalize_shop_id("a" * 100)), 40)


if __name__ == "__main__":
    unittest.main()
