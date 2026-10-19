"""通知渠道注册表测试：渠道覆盖、分发与错误。"""

from __future__ import annotations

import unittest

from yuxiaoer.seller.notifications.channels import SENDERS, Message
from yuxiaoer.seller.notifications.notifications import KINDS, NotificationService


class ChannelRegistryTests(unittest.IsolatedAsyncioTestCase):
    def test_every_declared_kind_has_sender(self) -> None:
        self.assertEqual(set(KINDS), set(SENDERS))

    async def test_log_channel_records(self) -> None:
        service = NotificationService(None)  # _send 不碰数据库
        result = await service._send(
            {"kind": "log", "config": {}},
            {"level": "P1", "title": "测试", "body": "正文"},
        )
        self.assertEqual(result, "recorded")

    async def test_unknown_channel_raises(self) -> None:
        service = NotificationService(None)
        with self.assertRaises(ValueError):
            await service._send({"kind": "nope", "config": {}}, {"level": "P1", "title": "x"})

    def test_message_text_contains_title_and_body(self) -> None:
        msg = Message(title="标题", body="正文", level="P0", alert={})
        self.assertEqual(msg.text, "标题\n正文")


if __name__ == "__main__":
    unittest.main()
