"""归一化与轻量意图模型测试。"""

from __future__ import annotations

import unittest

from yuxiaoer.buyer.conversation.normalize import (
    chinese_to_int,
    contact_text,
    match_text,
    normalize_text,
    price_text,
)
from yuxiaoer.buyer.conversation.small_model import small_model


class NormalizeTests(unittest.TestCase):
    def test_nfkc_and_space(self) -> None:
        self.assertEqual(normalize_text("　这个　还有吗？"), "这个 还有吗?")

    def test_match_strips_punctuation(self) -> None:
        self.assertEqual(match_text("这个，还有吗？"), "这个还有吗")

    def test_contact_removes_separators(self) -> None:
        self.assertEqual(contact_text("加 个 微 信"), "加个微信")
        self.assertEqual(contact_text("V X 多少"), "vx多少")

    def test_chinese_price(self) -> None:
        self.assertEqual(chinese_to_int("八"), 8)
        self.assertEqual(chinese_to_int("八十"), 80)
        self.assertEqual(chinese_to_int("八十五"), 85)
        self.assertEqual(price_text("八块卖不卖"), "8块卖不卖")

    def test_price_unit(self) -> None:
        self.assertEqual(price_text("￥ 9.9 元"), "¥ 9.9 元")


class SmallModelTests(unittest.TestCase):
    def test_business_labels(self) -> None:
        cases = {
            "多少钱": "pre_sale",
            "能少点不": "bargain",
            "快递到哪了": "after_sale",
            "我的订单": "order",
            "在吗": "chitchat",
            "转人工": "human",
            "加微信": "off_platform",
        }
        for text, expected in cases.items():
            prediction = small_model.predict(text)
            self.assertIsNotNone(prediction, text)
            self.assertEqual(prediction.label, expected, text)

    def test_unrelated_text_abstains(self) -> None:
        self.assertIsNone(small_model.predict("今天天气怎么样"))


if __name__ == "__main__":
    unittest.main()
