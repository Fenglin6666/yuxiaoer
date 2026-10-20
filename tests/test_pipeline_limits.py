"""消息合并与历史补拉的上限逻辑测试。"""

from __future__ import annotations

import asyncio
import time
import unittest

from yuxiaoer.buyer.conversation.ingest import IngestService, debounce_delay
from yuxiaoer.seller.platform.xianyu.ws import XianyuIM, rotate_batch


class DebounceDelayTests(unittest.TestCase):
    def test_normal_window(self) -> None:
        self.assertEqual(debounce_delay(0, 1.5, 6), 1.5)

    def test_capped_by_max_hold(self) -> None:
        self.assertEqual(debounce_delay(5, 1.5, 6), 1.0)

    def test_never_negative(self) -> None:
        self.assertEqual(debounce_delay(10, 1.5, 6), 0.0)

    def test_zero_max_hold_disables_cap(self) -> None:
        self.assertEqual(debounce_delay(10, 1.5, 0), 1.5)

    def test_negative_elapsed_treated_as_zero(self) -> None:
        self.assertEqual(debounce_delay(-3, 1.5, 6), 1.5)


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


class _FakeSettings:
    async def get_float(self, key: str, default: float = 0.0) -> float:
        return {"merge_window_seconds": 0.05, "merge_max_seconds": 0.12}.get(key, default)


class _FakeMessaging:
    async def pending_inbound(self, conversation_id: str) -> list[dict]:
        return []


class _FakeBuyer:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def handle_pending(self, conversation_id: str) -> None:
        self.calls.append(time.monotonic())


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


class IngestBurstTests(unittest.IsolatedAsyncioTestCase):
    async def test_continuous_messages_hit_max_hold(self) -> None:
        buyer = _FakeBuyer()
        service = IngestService(None, _FakeMessaging(), buyer, _FakeSettings())  # type: ignore[arg-type]
        started = time.monotonic()
        for _ in range(12):
            service._schedule("conv_1")
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.12)
        service.stop()
        self.assertTrue(buyer.calls, "应触发一次处理")
        self.assertLess(buyer.calls[0] - started, 0.2, "连续消息不应无限推迟处理")

    async def test_single_message_waits_window(self) -> None:
        buyer = _FakeBuyer()
        service = IngestService(None, _FakeMessaging(), buyer, _FakeSettings())  # type: ignore[arg-type]
        started = time.monotonic()
        service._schedule("conv_2")
        await asyncio.sleep(0.1)
        service.stop()
        self.assertTrue(buyer.calls)
        self.assertGreaterEqual(buyer.calls[0] - started, 0.03)


if __name__ == "__main__":
    unittest.main()
