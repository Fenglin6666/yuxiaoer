"""纯规则单测：网关分类 + 议价引擎 + 中文检索分词。"""

from __future__ import annotations

import unittest

from yuxiaoer.buyer.conversation.bargain import decide, parse_offer
from yuxiaoer.buyer.conversation.gateway import classify
from yuxiaoer.core.util import cjk_tokens, fts_query

ITEM = {
    "price_cents": 990,
    "floor_price_cents": 690,
    "delivery_mode": "virtual",
    "title": "奥数资料",
}


class GatewayTests(unittest.TestCase):
    def test_risk_is_silent(self):
        d = classify("你这个骗子，我要举报你")
        self.assertEqual(d.category, "risk")
        self.assertEqual(d.action, "silent")
        self.assertTrue(d.risk_level)

    def test_off_platform_is_silent(self):
        d = classify("能加个微信聊吗")
        self.assertEqual(d.category, "off_platform")
        self.assertEqual(d.action, "silent")

    def test_chitchat_template(self):
        d = classify("在吗")
        self.assertEqual(d.category, "chitchat")
        self.assertEqual(d.action, "template")
        self.assertIn("在", d.template or "")

    def test_after_sale_takes_priority(self):
        d = classify("快递到哪了")
        self.assertEqual(d.category, "after_sale")

    def test_bargain(self):
        d = classify("能便宜点吗")
        self.assertEqual(d.category, "bargain")
        self.assertEqual(d.action, "agent")

    def test_pre_sale(self):
        d = classify("这个还有吗")
        self.assertEqual(d.category, "pre_sale")

    def test_unknown_is_cautious(self):
        d = classify("今天天气怎么样")
        self.assertTrue(d.cautious)
        self.assertEqual(d.action, "agent")


class BargainTests(unittest.TestCase):
    def test_parse_yuan(self):
        self.assertEqual(parse_offer("8块卖不卖", 990), 800)
        self.assertEqual(parse_offer("便宜2块", 990), 790)

    def test_accept_above_floor(self):
        d = decide(ITEM, "8块卖不卖", 0)
        self.assertEqual(d.kind, "accept")
        self.assertEqual(d.target_cents, 800)

    def test_reject_below_floor(self):
        d = decide(ITEM, "5块钱可以吗", 0)
        self.assertEqual(d.kind, "decline")
        self.assertIn("最低", d.message)

    def test_generic_counter(self):
        d = decide(ITEM, "能便宜点吗", 0)
        self.assertEqual(d.kind, "counter")
        self.assertGreaterEqual(d.target_cents, ITEM["floor_price_cents"])

    def test_floor_never_broken(self):
        d = decide(ITEM, "1块钱", 0)
        self.assertGreaterEqual(d.target_cents, ITEM["floor_price_cents"])


class TokenizerTests(unittest.TestCase):
    def test_chinese_bigram(self):
        tokens = cjk_tokens("发货时间")
        self.assertIn("发货", tokens)
        self.assertIn("时间", tokens)

    def test_fts_query(self):
        q = fts_query("PDF 怎么发")
        self.assertIn("pdf", q)
        self.assertIn(" OR ", q)


if __name__ == "__main__":
    unittest.main()
