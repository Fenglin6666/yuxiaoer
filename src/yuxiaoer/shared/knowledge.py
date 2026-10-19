"""轻量知识库：商品知识 + FAQ + 店铺概览。

- namespace=buyer / seller 隔离；
- SQLite FTS5 + 中文 bigram 召回，BM25 排序；FTS 不可用时退化为 LIKE；
- 商品下架 = 墓碑（tombstone），检索立即失效；
- 版本化：内容 hash 变化才重建 chunk。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from yuxiaoer.core.db import Database
from yuxiaoer.core.util import (
    dumps,
    fts_query,
    fts_text,
    iso,
    loads,
    new_id,
    snippet,
    yuan,
)


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _chunk(text: str, limit: int = 420) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    if len(blocks) <= 1:
        blocks = [b.strip() for b in text.split("\n") if b.strip()]
    chunks: list[str] = []
    buf = ""
    for block in blocks:
        if len(buf) + len(block) + 1 <= limit:
            buf = (buf + "\n" + block).strip()
            continue
        if buf:
            chunks.append(buf)
        while len(block) > limit:
            cut = block.rfind("。", 0, limit)
            cut = cut + 1 if cut > limit // 2 else limit
            chunks.append(block[:cut].strip())
            block = block[cut:].strip()
        buf = block
    if buf:
        chunks.append(buf)
    return chunks or [text[:limit]]


class KnowledgeService:
    def __init__(self, db: Database):
        self.db = db

    # ---------------- 写入 ----------------

    async def upsert_source(
        self,
        source_id: str,
        namespace: str,
        type_: str,
        title: str,
        content: str,
        origin: str = "manual",
        meta: dict[str, Any] | None = None,
        status: str = "live",
    ) -> dict[str, Any]:
        content_hash = _hash(content)
        old = await self.db.fetchone(
            "SELECT * FROM kb_sources WHERE id=?", (source_id,)
        )
        if old and old["content_hash"] == content_hash and old["status"] == status:
            return {"source_id": source_id, "version": old["version"], "changed": False}

        version = (int(old["version"]) + 1) if old else 1
        now = iso()
        if old:
            await self.db.execute(
                """UPDATE kb_sources SET namespace=?,type=?,title=?,origin=?,content=?,meta_json=?,
                   version=?,status=?,content_hash=?,updated_at=? WHERE id=?""",
                (
                    namespace, type_, title, origin, content, dumps(meta or {}),
                    version, status, content_hash, now, source_id,
                ),
            )
        else:
            await self.db.execute(
                """INSERT INTO kb_sources(id,namespace,type,title,origin,content,meta_json,version,status,content_hash,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source_id, namespace, type_, title, origin, content, dumps(meta or {}),
                    version, status, content_hash, now, now,
                ),
            )

        await self._drop_chunks(source_id)
        if status == "live":
            for i, text in enumerate(_chunk(content)):
                await self._add_chunk(source_id, namespace, i, text, meta or {})
        return {"source_id": source_id, "version": version, "changed": True}

    async def _drop_chunks(self, source_id: str) -> None:
        rows = await self.db.fetchall("SELECT id FROM kb_chunks WHERE source_id=?", (source_id,))
        for row in rows:
            await self._fts_delete(row["id"])
        await self.db.execute("DELETE FROM kb_chunks WHERE source_id=?", (source_id,))

    async def _add_chunk(self, source_id: str, namespace: str, ord_: int, text: str, meta: dict) -> None:
        chunk_id = new_id("chunk")
        await self.db.execute(
            "INSERT INTO kb_chunks(id,source_id,namespace,ord,text,meta_json,tombstone,created_at)"
            " VALUES(?,?,?,?,?,?,0,?)",
            (chunk_id, source_id, namespace, ord_, text, dumps(meta), iso()),
        )
        if self.db.fts_enabled:
            try:
                await self.db.execute(
                    "INSERT INTO kb_fts(chunk_id,namespace,search_text) VALUES(?,?,?)",
                    (chunk_id, namespace, fts_text(text)),
                )
            except Exception:
                pass

    async def _fts_delete(self, chunk_id: str) -> None:
        if self.db.fts_enabled:
            try:
                await self.db.execute("DELETE FROM kb_fts WHERE chunk_id=?", (chunk_id,))
            except Exception:
                pass

    async def tombstone(self, source_id: str) -> None:
        await self.db.execute(
            "UPDATE kb_sources SET status='tombstone',updated_at=? WHERE id=?", (iso(), source_id)
        )
        rows = await self.db.fetchall("SELECT id FROM kb_chunks WHERE source_id=?", (source_id,))
        for row in rows:
            await self._fts_delete(row["id"])
        await self.db.execute("UPDATE kb_chunks SET tombstone=1 WHERE source_id=?", (source_id,))

    # ---------------- 商品同步 ----------------

    @staticmethod
    def item_content(item: Any) -> str:
        delivery = "虚拟商品，拍下自动发卡券/网盘链接" if item["delivery_mode"] == "virtual" else "实物，48 小时内发货，默认包邮"
        lines = [
            f"商品：{item['title']}",
            f"价格：{yuan(item['price_cents'])} 元",
            f"成色：{item['condition'] or '未标注'}",
            f"发货：{delivery}",
            f"分类：{item['category'] or '未分类'}",
            f"库存：{item['stock']}",
            f"商品描述：{item['description']}",
        ]
        return "\n".join(lines)

    async def sync_item(self, item_id: str) -> dict[str, Any] | None:
        item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (item_id,))
        if not item:
            return None
        source_id = f"item:{item_id}"
        if item["status"] in ("offline", "draft", "pending_confirm"):
            await self.tombstone(source_id)
            return {"source_id": source_id, "status": "tombstone"}
        meta = {
            "item_id": item_id,
            "price_cents": item["price_cents"],
            "floor_price_cents": item["floor_price_cents"],
            "delivery_mode": item["delivery_mode"],
            "status": item["status"],
        }
        result = await self.upsert_source(
            source_id, "buyer", "item", item["title"], self.item_content(item),
            origin=f"item:{item_id}", meta=meta,
        )
        await self.db.execute(
            "UPDATE items SET knowledge_version=?,updated_at=? WHERE id=?",
            (result["version"], iso(), item_id),
        )
        return result

    async def sync_all_items(self) -> None:
        rows = await self.db.fetchall("SELECT id,status FROM items")
        for row in rows:
            await self.sync_item(row["id"])

    async def bootstrap(self) -> None:
        await self.sync_all_items()

    # ---------------- 检索 ----------------

    async def search(
        self,
        query: str,
        *,
        namespace: str = "buyer",
        k: int = 3,
        types: Iterable[str] | None = None,
        item_id: str | None = None,
    ) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        type_list = list(types) if types else None
        rows: list[Any] = []
        match = fts_query(q)
        if self.db.fts_enabled and match:
            sql = (
                "SELECT c.id AS chunk_id,c.text,c.source_id,c.namespace,s.title,s.type,s.origin,s.meta_json,"
                "bm25(kb_fts) AS rank "
                "FROM kb_fts JOIN kb_chunks c ON c.id=kb_fts.chunk_id "
                "JOIN kb_sources s ON s.id=c.source_id "
                "WHERE kb_fts MATCH ? AND c.namespace=? AND c.tombstone=0 AND s.status='live' "
            )
            params: list[Any] = [match, namespace]
            if type_list:
                sql += "AND s.type IN (" + ",".join("?" for _ in type_list) + ") "
                params.extend(type_list)
            sql += "ORDER BY rank LIMIT ?"
            params.append(max(k * 4, 12))
            try:
                rows = await self.db.fetchall(sql, params)
            except Exception:
                rows = []

        if not rows:
            # 降级：LIKE + 关键词命中计数
            terms = [t for t in re.split(r"[\s,，。？?！!]+", q) if len(t) >= 1][:6]
            if not terms:
                return []
            like_sql = (
                "SELECT c.id AS chunk_id,c.text,c.source_id,c.namespace,s.title,s.type,s.origin,s.meta_json,0 AS rank "
                "FROM kb_chunks c JOIN kb_sources s ON s.id=c.source_id "
                "WHERE c.namespace=? AND c.tombstone=0 AND s.status='live' "
            )
            params = [namespace]
            if type_list:
                like_sql += "AND s.type IN (" + ",".join("?" for _ in type_list) + ") "
                params.extend(type_list)
            like_sql += "AND (" + " OR ".join("c.text LIKE ?" for _ in terms) + ") LIMIT ?"
            params.extend(f"%{t}%" for t in terms)
            params.append(max(k * 4, 12))
            rows = await self.db.fetchall(like_sql, params)

        results: list[dict[str, Any]] = []
        for row in rows:
            meta = loads(row["meta_json"], {}) or {}
            if item_id and meta.get("item_id") not in (None, item_id):
                continue
            score = -float(row["rank"] or 0)
            # 商品知识轻微加权，FAQ 命中优先一点点
            if row["type"] == "faq":
                score += 0.15
            results.append(
                {
                    "chunk_id": row["chunk_id"],
                    "source_id": row["source_id"],
                    "title": row["title"],
                    "type": row["type"],
                    "origin": row["origin"],
                    "text": row["text"],
                    "snippet": snippet(row["text"], 140),
                    "score": round(score, 4),
                    "meta": meta,
                }
            )
        results.sort(key=lambda x: x["score"], reverse=True)
        # 同 source 只保留最高分
        dedup: list[dict[str, Any]] = []
        seen: set[str] = set()
        for r in results:
            if r["source_id"] in seen:
                continue
            seen.add(r["source_id"])
            dedup.append(r)
            if len(dedup) >= k:
                break
        return dedup

    async def item_knowledge(self, item_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchone(
            "SELECT * FROM kb_sources WHERE id=? AND status='live'", (f"item:{item_id}",)
        )
        if not row:
            return None
        return {
            "source_id": row["id"], "title": row["title"], "content": row["content"],
            "version": row["version"], "updated_at": row["updated_at"],
        }

    async def context_for_buyer(self, item: dict[str, Any] | None, query: str, k: int = 3) -> dict[str, Any]:
        faq_hits = await self.search(query, namespace="buyer", k=k, types=["faq"])
        item_hits = await self.search(query, namespace="buyer", k=2, types=["item"])
        item_knowledge = await self.item_knowledge(item["id"]) if item else None
        return {
            "faq_hits": faq_hits,
            "item_hits": item_hits,
            "item_knowledge": item_knowledge,
            "degraded": not self.db.fts_enabled,
        }

    async def stats(self) -> dict[str, Any]:
        live = await self.db.count("kb_sources", "status='live'")
        tomb = await self.db.count("kb_sources", "status='tombstone'")
        chunks = await self.db.count("kb_chunks", "tombstone=0")
        return {"sources_live": live, "sources_tombstone": tomb, "chunks": chunks, "fts": self.db.fts_enabled}
