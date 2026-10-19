"""卖家指令共享助手测试：查询词清洗 + 确认卡提案。"""

from __future__ import annotations

import unittest
from typing import Any

from yuxiaoer.seller.commands._shared import clean_query, propose


class CleanQueryTests(unittest.TestCase):
    def test_strips_verb_prefix_and_filler(self) -> None:
        self.assertEqual(clean_query("把 Kindle 商品 下架", r"(下架|撤下)"), "Kindle")

    def test_price_tokens_are_removed(self) -> None:
        query = clean_query(
            "把 Kindle 改价到 199 元",
            r"(改价|调价)",
            extra=r"(到|改成|改为|至)\s*\d+(?:\.\d{1,2})?\s*(?:元|块)?|\d+(?:\.\d{1,2})?\s*(?:元|块)?",
        )
        self.assertEqual(query, "Kindle")

    def test_no_verb_keeps_words(self) -> None:
        self.assertEqual(clean_query("手写笔记", r"(下架)"), "手写笔记")


class _FakeConfirmations:
    def __init__(self) -> None:
        self.created: tuple[Any, ...] | None = None

    async def create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.created = (args, kwargs)
        return {"id": "cfm_test"}


class _FakeToolbox:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, args: dict[str, Any], fn: Any) -> dict[str, Any]:
        self.calls.append((name, args))
        return {"ok": True}


class ProposeTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_confirmation_and_card(self) -> None:
        confirmations = _FakeConfirmations()
        toolbox = _FakeToolbox()
        preview = {"kind": "offline_item", "item_id": "item_1"}
        result = await propose(
            confirmations,
            toolbox,  # type: ignore[arg-type]
            kind="offline_item",
            title="下架商品：测试",
            preview=preview,
            payload={"item_id": "item_1"},
            text="要下架吗？",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "要下架吗？")
        self.assertEqual(result["card"]["confirmation_id"], "cfm_test")
        self.assertEqual(result["card"]["preview"], preview)
        self.assertEqual(toolbox.calls, [("offline_item", {"item_id": "item_1"})])


if __name__ == "__main__":
    unittest.main()
