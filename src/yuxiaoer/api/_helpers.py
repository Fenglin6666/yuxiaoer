"""控制台路由共享助手：实体读取、审计写入、商品视图。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..core.util import dumps, iso
from ..runtime import runtime
from ._views import _full_item


async def item_or_404(item_id: str, *, select: str = "*", detail: str = "商品不存在") -> dict[str, Any]:
    row = await runtime.db.fetchone(f"SELECT {select} FROM items WHERE id=?", (item_id,))
    if not row:
        raise HTTPException(404, detail)
    return dict(row)


async def order_or_404(order_id: str) -> dict[str, Any]:
    row = await runtime.db.fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
    if not row:
        raise HTTPException(404, "订单不存在")
    return dict(row)


async def full_item(item_id: str) -> dict[str, Any]:
    return _full_item(await item_or_404(item_id))


async def audit(
    action: str,
    target: str,
    detail: Any = None,
    *,
    result: str = "success",
    actor: str = "owner",
) -> None:
    payload = detail if isinstance(detail, str) else dumps(detail if detail is not None else {})
    await runtime.db.execute(
        "INSERT INTO audit_logs(ts,actor,action,target,detail_json,result) VALUES(?,?,?,?,?,?)",
        (iso(), actor, action, target, payload, result),
    )
