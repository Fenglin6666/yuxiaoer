"""入口直投与历史补拉的上限逻辑测试。"""

from __future__ import annotations

import time
import unittest

from yuxiaoer.buyer.conversation.ingest import IngestService
from yuxiaoer.seller.platform.xianyu.ws import XianyuIM, rotate_batch


class _FakeMessaging:
    def __init__(self, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.inbound: list[dict] = []

    async def ensure_conversation(self, buyer_id: str, item_id: str | None, nick: str = "") -> dict:
        return {"id": "conv_1", "meta_json": "{}"}

    async def add_inbound(self, conversation_id: str, text: str, **kwargs) -> dict:
        self.inbound.append({"text": text, **kwargs})
        if self.duplicate:
            return {"id": "msg_dup", "duplicate": True}
        return {"id": f"msg_{len(self.inbound)}", "duplicate": False}


class _FakeBuyer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def handle_message(self, conversation_id: str, message_id: str) -> None:
        self.calls.append((conversation_id, message_id))


class IngestDirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_message_becomes_one_turn_in_order(self) -> None:
        messaging = _FakeMessaging()
        buyer = _FakeBuyer()
        service = IngestService(None, messaging, buyer)  # type: ignore[arg-type]
        for text in ("第一条", "第二条", "第三条"):
            await service.submit_buyer_message(
                buyer_id="buyer_1", text=text, item_id="item_1"
            )
        count = await service.flush()
        service.stop()
        self.assertEqual(count, 3)
        self.assertEqual([c[1] for c in buyer.calls], ["msg_1", "msg_2", "msg_3"])
        self.assertEqual([m["text"] for m in messaging.inbound], ["第一条", "第二条", "第三条"])

    async def test_duplicate_does_not_enter_agent(self) -> None:
        messaging = _FakeMessaging(duplicate=True)
        buyer = _FakeBuyer()
        service = IngestService(None, messaging, buyer)  # type: ignore[arg-type]
        await service.submit_buyer_message(
            buyer_id="buyer_1", text="重复", item_id="item_1", external_id="same"
        )
        await service.flush()
        service.stop()
        self.assertEqual(buyer.calls, [])

    async def test_no_pre_agent_wait(self) -> None:
        messaging = _FakeMessaging()
        buyer = _FakeBuyer()
        service = IngestService(None, messaging, buyer)  # type: ignore[arg-type]
        started = time.monotonic()
        await service.submit_buyer_message(buyer_id="buyer_1", text="现在", item_id="item_1")
        await service.flush()
        elapsed = time.monotonic() - started
        service.stop()
        self.assertLess(elapsed, 0.3, "进入 Agent 不应有 debounce 等待")


class RotateBatchTests(unittest.TestCase):
    def test_first_batch(self) -> None:
        batch, nxt = rotate_batch(list(range(50)), 0, 20)
        self.assertEqual(batch, list(range(20)))
        self.assertEqual(nxt, 20)

    def test_tail_batch_returns_to_start(self) -> None:
        batch, nxt = rotate_batch(list(range(50)), 40, 20)
        self.assertEqual(batch, list(range(40, 50)))
        self.assertEqual(nxt, 0)

    def test_empty(self) -> None:
        self.assertEqual(rotate_batch([], 0, 20), ([], 0))


class _HistoryIM(XianyuIM):
    def __init__(self) -> None:
        super().__init__(cookies="", token="", user_id="u1")

    async def get_conversations(self, limit: int = 50) -> dict:
        now = int(time.time() * 1000)
        return {
            "userConvs": [
                {"singleChatConversation": {"cid": f"c{i}"}, "modifyTime": now}
                for i in range(30)
            ]
        }

    async def get_messages(self, cid: str, limit: int = 50) -> dict:
        return {"userMessageModels": []}


class HistoryBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_rotates_across_passes(self) -> None:
        im = _HistoryIM()
        self.assertFalse(await im._poll_history_locked(0))
        self.assertEqual(im._history_offset, 20)
        self.assertTrue(await im._poll_history_locked(0))
        self.assertEqual(im._history_offset, 0)


if __name__ == "__main__":
    unittest.main()
