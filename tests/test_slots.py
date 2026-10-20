"""实体/槽位抽取测试。"""

from __future__ import annotations

import unittest

from yuxiaoer.buyer.conversation.bargain import parse_offer
from yuxiaoer.buyer.conversation.slots import extract_slots

ITEM = {
    "id": "i1",
    "price_cents": 39900,
    "floor_price_cents": 30000,
}


class SlotTests(unittest.TestCase):
    def test_size_color_and_item(self) -> None:
        slots = extract_slots("这双 42 码白色还有吗", ITEM)
        self.assertEqual(slots["item_id"], "i1")
        self.assertEqual(slots["size"], "42")
        self.assertEqual(slots["color"], "白")

    def test_size_is_not_offer(self) -> None:
        self.assertIsNone(parse_offer("42码还有吗", 39900))
        self.assertNotIn("offer_cents", extract_slots("42码还有吗", ITEM))

    def test_budget(self) -> None:
        self.assertEqual(extract_slots("预算500以内有什么", ITEM)["budget_cents"], 50000)
        self.assertEqual(extract_slots("不超过 300 元", ITEM)["budget_cents"], 30000)

    def test_order_no(self) -> None:
        self.assertEqual(extract_slots("订单 ord_abc123 到哪了", ITEM)["order_no"], "ord_abc123")

    def test_keywords(self) -> None:
        self.assertEqual(extract_slots("有别的鞋吗", None)["keywords"], ["鞋"])

    def test_use_hint(self) -> None:
        self.assertIn("跑步", extract_slots("适合跑步的鞋", ITEM)["use"])


if __name__ == "__main__":
    unittest.main()
