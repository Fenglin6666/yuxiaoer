"""原生协议单元测试：签名/WS 帧/消息归一化/订单字段。"""

from __future__ import annotations

import asyncio
import base64
import json
import unittest

from yuxiaoer.seller.platform.xianyu.mtop import generate_mid, generate_sign, merge_set_cookies
from yuxiaoer.seller.platform.xianyu.orders import OrderSyncService
from yuxiaoer.seller.platform.xianyu.ws import XianyuIM, normalize_message


class FakeWS:
    def __init__(self):
        self.frames = []

    async def send(self, frame):
        self.frames.append(frame)


def _packet(obj):
    return base64.b64encode(json.dumps(obj, ensure_ascii=False).encode()).decode()


class ProtocolTest(unittest.IsolatedAsyncioTestCase):
    def test_sign_and_mid(self):
        token = "abc123"
        t = "1700000000000"
        data = '{"x":1}'
        expected = __import__("hashlib").md5(f"{token}&{t}&34839810&{data}".encode()).hexdigest()
        self.assertEqual(generate_sign(t, token, data), expected)
        self.assertTrue(generate_mid().endswith(" 0"))

    def test_cookie_merge(self):
        merged, changed = merge_set_cookies(
            "unb=1; _m_h5_tk=old",
            ["_m_h5_tk=new_123; Path=/", "cookie2=x; Path=/", "unb=; Max-Age=0"],
        )
        self.assertIn("_m_h5_tk=new_123", merged)
        self.assertIn("cookie2=x", merged)
        self.assertNotIn("unb=", merged + ";")
        self.assertEqual(changed.get("_m_h5_tk"), "new_123")

    def test_normalize_chat(self):
        content = json.dumps({"contentType": 1, "text": {"text": "在吗，能便宜吗"}}, ensure_ascii=False)
        packet = {
            "1": {
                "2": "chat_abc@goofish",
                "5": 1700000000000,
                "10": {
                    "senderUserId": "buyer_1", "senderNick": "小鹿",
                    "bizTag": "m-1", "extJson": json.dumps({"messageId": "m-1"}),
                },
                "6": {"3": {"5": content}},
            }
        }
        msg = normalize_message({"body": {"syncPushPackage": {"data": [{"data": _packet(packet)}]}}})
        self.assertIsNotNone(msg)
        self.assertEqual(msg["chat_id"], "chat_abc")
        self.assertEqual(msg["buyer_id"], "buyer_1")
        self.assertEqual(msg["text"], "在吗，能便宜吗")

    def test_normalize_card_update(self):
        packet = {
            "1": "card",
            "2": "chat_abc@goofish",
            "4": {
                "reminderContent": "我已付款，等待你发货",
                "senderUserId": "buyer_1", "senderNick": "小鹿",
            },
            "5": 1700000000000,
        }
        msg = normalize_message({"body": {"syncPushPackage": {"data": [{"data": _packet(packet)}]}}})
        self.assertIsNotNone(msg)
        self.assertEqual(msg["kind"], "card_update")
        self.assertIn("已付款", msg["text"])

    async def test_send_frame(self):
        im = XianyuIM(cookies="unb=1", token="t", user_id="1")
        im.connected = True
        im.ws = FakeWS()
        mid = await im.send_text("chat_abc", "buyer_1", "你好", timeout=0.01)
        self.assertTrue(mid)
        frame = json.loads(im.ws.frames[0])
        self.assertEqual(frame["lwp"], "/r/MessageSend/sendByReceiverScope")
        payload = frame["body"][0]
        self.assertEqual(payload["cid"], "chat_abc@goofish")
        inner = json.loads(base64.b64decode(payload["content"]["custom"]["data"]))
        self.assertEqual(inner["text"]["text"], "你好")
        self.assertEqual(frame["body"][1]["actualReceivers"], ["buyer_1@goofish", "1@goofish"])

    def test_parse_order(self):
        service = OrderSyncService(None)
        parsed = service._parse({
            "commonData": {
                "orderId": "O123", "itemId": "I456", "orderStatus": "待发货",
                "createTime": "2026-10-17 12:00:00", "inRefund": "false",
            },
            "buyerInfoVO": {
                "buyerId": "B1", "userNick": "买家", "name": "张三",
                "phone": "13800000000", "address": "杭州市",
            },
            "priceVO": {"totalPrice": "99.00", "buyNum": "2"},
            "rightVO": {"btnList": [{"tradeAction": "SKIP_PIN"}]},
        }, {"id": "acc1", "platform_user_id": "22001"})
        self.assertEqual(parsed["status"], "paid")
        self.assertEqual(parsed["amount_cents"], 9900)
        self.assertEqual(parsed["quantity"], 2)
        self.assertEqual(parsed["receiver_name"], "张三")
        self.assertTrue(parsed["is_bargain"])


if __name__ == "__main__":
    unittest.main()
