"""登录后同步账号现状：在售商品、订单、账号标识与本地统计。"""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import unquote

from yuxiaoer.core.util import dumps, iso, loads, new_id
from .mtop import MtopClient, parse_cookies
from .orders import OrderSyncService


def _cents(value: Any) -> int:
    text = str(value or "").replace("¥", "").replace("￥", "").replace(",", "").strip()
    if not text:
        return 0
    try:
        return max(0, int((Decimal(text) * 100).quantize(Decimal("1"))))
    except (InvalidOperation, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _nested(data: Any, key: str) -> dict[str, Any]:
    """在 mtop 多层 data 包装中定位包含 key 的那一层。"""
    current = data
    for _ in range(4):
        if isinstance(current, dict) and key in current:
            return current
        if isinstance(current, dict):
            current = current.get("data")
        else:
            break
    return {}


def _item_status(raw_status: Any, desc: str = "") -> str:
    text = _text(desc)
    if "已售" in text or "卖出" in text:
        return "sold_out"
    if "下架" in text:
        return "offline"
    if _text(raw_status) in {"0", "1", "on_sale", "ON_SALE"}:
        return "live"
    return "live"


def _normalize_shop(raw: dict[str, Any]) -> dict[str, Any] | None:
    item_id = _text(raw.get("itemId"))
    if not item_id:
        return None
    price = _cents(raw.get("reservePrice"))
    image = _text(raw.get("itemImageUrl"))
    return {
        "platform_item_id": item_id,
        "title": _text(raw.get("title")) or f"闲鱼商品 {item_id}",
        "price_cents": price,
        "stock": int(raw.get("quantity") or 1),
        "status": _item_status(raw.get("itemStatus"), _text(raw.get("itemStatusDesc"))),
        "category": _text(raw.get("categoryName")) or "闲鱼在售",
        "condition": _text(raw.get("condition")) or "自用闲置",
        "image": image,
        "source": "shop",
        "raw": raw,
    }


def _normalize_personal(card: dict[str, Any]) -> dict[str, Any] | None:
    data = card.get("cardData") if isinstance(card.get("cardData"), dict) else card
    if not isinstance(data, dict):
        return None
    item_id = _text(data.get("id") or data.get("itemId"))
    if not item_id:
        return None
    price_info = data.get("priceInfo") if isinstance(data.get("priceInfo"), dict) else {}
    pic = data.get("picInfo") if isinstance(data.get("picInfo"), dict) else {}
    return {
        "platform_item_id": item_id,
        "title": _text(data.get("title")) or f"闲鱼商品 {item_id}",
        "price_cents": _cents(price_info.get("price") or data.get("price")),
        "stock": int(data.get("quantity") or 1),
        "status": _item_status(data.get("itemStatus"), _text(data.get("itemStatusDesc"))),
        "category": _text(data.get("categoryName")) or "闲鱼在售",
        "condition": _text(data.get("condition")) or "自用闲置",
        "image": _text(pic.get("url") or data.get("itemImageUrl")),
        "source": "personal",
        "raw": data,
    }


class AccountSyncService:
    _account_locks: dict[str, asyncio.Lock] = {}

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.db = runtime.db

    def _lock(self, account_id: str) -> asyncio.Lock:
        return self._account_locks.setdefault(account_id, asyncio.Lock())

    async def sync_account(self, account: dict[str, Any], *, max_pages: int = 10) -> dict[str, Any]:
        account_id = str(account.get("id") or "")
        if not account_id:
            return {"ok": False, "error": "账号不存在"}
        async with self._lock(account_id):
            cookies = str(account.get("cookies") or "")
            if not cookies:
                return {"ok": False, "error": "账号没有 Cookie，请先扫码登录"}
            client = MtopClient(cookies, device_id=str(account.get("device_id") or ""))
            items: list[dict[str, Any]] = []
            source = ""
            errors: list[str] = []
            # 先试鱼小铺卖家后台；普通账号会返回无权限，再回落个人版在售列表。
            try:
                page = 1
                while page <= max_pages:
                    data = await client.list_shop_items(page, 20)
                    biz = _nested(data, "itemSearchResponseList")
                    rows = biz.get("itemSearchResponseList") or []
                    for raw in rows:
                        if isinstance(raw, dict):
                            normalized = _normalize_shop(raw)
                            if normalized:
                                items.append(normalized)
                    if not rows or not biz.get("hasNextPage"):
                        break
                    page += 1
                if items:
                    source = "shop"
            except Exception as exc:  # 普通卖家无权限时走个人版
                errors.append(f"鱼小铺列表：{str(exc)[:120]}")
            if not items:
                try:
                    page = 1
                    user_id = str(account.get("platform_user_id") or parse_cookies(cookies).get("unb") or "")
                    while page <= max_pages:
                        data = await client.list_personal_items(page, 20, user_id)
                        cards = _nested(data, "cardList").get("cardList") or []
                        if isinstance(cards, str):
                            cards = loads(cards, []) or []
                        rows = [c for c in (cards or []) if isinstance(c, dict)]
                        for card in rows:
                            normalized = _normalize_personal(card)
                            if normalized:
                                items.append(normalized)
                        if len(rows) < 20:
                            break
                        page += 1
                    if items:
                        source = "personal"
                except Exception as exc:
                    errors.append(f"个人在售列表：{str(exc)[:120]}")
            if client.cookies != cookies:
                await self.db.execute(
                    "UPDATE accounts SET cookies=?,updated_at=? WHERE id=?", (client.cookies, iso(), account_id)
                )
                account["cookies"] = client.cookies
            created = updated = 0
            for normalized in items:
                try:
                    result = await self._upsert_item(normalized, account)
                    if result == "created":
                        created += 1
                    elif result == "updated":
                        updated += 1
                except Exception as exc:
                    errors.append(f"写入商品 {normalized.get('platform_item_id')}：{str(exc)[:100]}")
            profile = await self._update_profile(account, cookies)
            order_result = await OrderSyncService(self.runtime).sync_account(account)
            counts = await self._counts()
            summary = f"已同步：在售 {counts.get('live_items', 0)} · 订单 {sum(counts.get('orders', {}).values())}"
            await self.db.execute(
                "UPDATE accounts SET detail=?,updated_at=? WHERE id=?", (summary, iso(), account_id)
            )
            if not items and errors:
                return {
                    "ok": False, "error": "；".join(errors[:2]), "items": {"seen": 0, "created": 0, "updated": 0},
                    "orders": order_result, "profile": profile, "counts": counts, "source": source,
                }
            return {
                "ok": True,
                "source": source or "none",
                "items": {"seen": len(items), "created": created, "updated": updated},
                "orders": order_result,
                "profile": profile,
                "counts": counts,
                "summary": summary,
                "errors": errors[:5],
                "at": iso(),
            }

    async def _upsert_item(self, data: dict[str, Any], account: dict[str, Any]) -> str:
        platform_id = data["platform_item_id"]
        existing = await self.db.fetchone("SELECT * FROM items WHERE platform_item_id=?", (platform_id,))
        now = iso()
        price = int(data.get("price_cents") or 0)
        meta = {
            "source": f"xianyu_{data.get('source')}",
            "image_url": data.get("image") or "",
            "platform_status": data.get("status"),
            "raw": data.get("raw") or {},
        }
        if existing:
            floor = min(int(existing["floor_price_cents"]), price) if price else int(existing["floor_price_cents"])
            old_meta = loads(existing["meta_json"], {}) or {}
            old_meta.update(meta)
            await self.db.execute(
                """UPDATE items SET title=?,price_cents=?,floor_price_cents=?,category=COALESCE(NULLIF(?,''),category),
                   stock=CASE WHEN ?>0 THEN ? ELSE stock END,status=?,platform_item_id=?,updated_at=?,meta_json=?
                   WHERE id=?""",
                (
                    data["title"], price or existing["price_cents"], floor or 1,
                    data.get("category") or "", int(data.get("stock") or 0), int(data.get("stock") or 0),
                    data["status"], platform_id, now, dumps(old_meta), existing["id"],
                ),
            )
            await self.runtime.knowledge.sync_item(existing["id"])
            return "updated"
        item_id = new_id("item")
        floor = max(1, int(round((price or 1) * 0.85)))
        await self.db.execute(
            """INSERT INTO items(id,platform_item_id,title,description,price_cents,floor_price_cents,
               max_discount_pct,category,condition,delivery_mode,stock,status,card_content,link_url,
               image_hint,knowledge_version,relist_count,relist_limit,sold_count,created_at,updated_at,meta_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id, platform_id, data["title"], data["title"], price or 1, floor, 15,
                data.get("category") or "闲鱼在售", data.get("condition") or "自用闲置", "physical",
                int(data.get("stock") or 1), data["status"], None, None,
                "🖼️", 0, 0, 3, 0, now, now, dumps(meta),
            ),
        )
        await self.runtime.knowledge.sync_item(item_id)
        return "created"

    async def _update_profile(self, account: dict[str, Any], cookies: str) -> dict[str, Any]:
        parsed = parse_cookies(cookies)
        unb = _text(parsed.get("unb") or account.get("platform_user_id"))
        nick = _text(parsed.get("tracknick") or parsed.get("lgc") or parsed.get("_nk_"))
        nick = unquote(nick) if nick else ""
        current = _text(account.get("nickname"))
        changes: dict[str, Any] = {}
        if unb and unb != account.get("platform_user_id"):
            changes["platform_user_id"] = unb
        if nick and (not current or current.startswith("闲鱼账号") or current == unb):
            changes["nickname"] = nick
        if changes:
            assignments = ",".join(f"{k}=?" for k in changes)
            await self.db.execute(
                f"UPDATE accounts SET {assignments},updated_at=? WHERE id=?",
                tuple(changes.values()) + (iso(), account["id"]),
            )
        return {"platform_user_id": changes.get("platform_user_id") or unb,
                "nickname": changes.get("nickname") or current}

    async def _counts(self) -> dict[str, Any]:
        item_rows = await self.db.fetchall("SELECT status,COUNT(*) AS n FROM items GROUP BY status")
        order_rows = await self.db.fetchall("SELECT status,COUNT(*) AS n FROM orders GROUP BY status")
        return {
            "items": {str(r["status"]): int(r["n"]) for r in item_rows},
            "orders": {str(r["status"]): int(r["n"]) for r in order_rows},
            "live_items": await self.db.count("items", "status='live'"),
            "conversations": await self.db.count("conversations", "id!='conv_seller'"),
        }
