"""商品索引：FTS 搜索与 LIKE 兜底。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yuxiaoer.core.db import Database
from yuxiaoer.shared.knowledge import KnowledgeService

ITEM_SQL = """INSERT INTO items(id,title,description,price_cents,floor_price_cents,max_discount_pct,
    category,condition,delivery_mode,stock,status,created_at,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)"""


class ItemSearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="yx-search-")
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name) / "t.db"
        self.db = Database(self.tmp)
        await self.db.connect()
        await self.db.execute(
            ITEM_SQL,
            ("i1", "白色空军一号 42", "Nike AF1 白色 42码 9成新", 39900, 30000, 25,
             "鞋", "9成新", "physical", 1, "live", "2026-10-20T00:00:00Z", "2026-10-20T00:00:00Z"),
        )
        await self.db.execute(
            ITEM_SQL,
            ("i2", "黑色跑鞋 43", "轻量跑鞋 43码", 25900, 20000, 22,
             "鞋", "全新", "physical", 0, "sold_out", "2026-10-20T00:00:00Z", "2026-10-20T00:00:00Z"),
        )
        self.knowledge = KnowledgeService(self.db)
        await self.knowledge.bootstrap()
        await self.knowledge.sync_item("i1")
        await self.knowledge.sync_item("i2")

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_fts_hit(self) -> None:
        hits = await self.knowledge.search_items("白色")
        self.assertEqual(hits[0]["id"], "i1")

    async def test_size_and_description_hit(self) -> None:
        hits = await self.knowledge.search_items("42码")
        self.assertEqual([h["id"] for h in hits], ["i1"])

    async def test_no_result(self) -> None:
        self.assertEqual(await self.knowledge.search_items("红色高跟鞋"), [])

    async def test_empty_query_returns_recent(self) -> None:
        hits = await self.knowledge.search_items("")
        self.assertEqual({h["id"] for h in hits}, {"i1", "i2"})


if __name__ == "__main__":
    unittest.main()
