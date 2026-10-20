"""规则实体抽取：尺码、颜色、预算、订单号、出价、检索关键词。

只做“候选参数”，调用方负责校验；绝不把原文直接当 SQL/ID 使用。
"""

from __future__ import annotations

import re
from typing import Any

from .bargain import parse_offer
from .normalize import normalize_text

COLOR_ALIASES = {
    "白": "白", "白色": "白", "米白": "米白", "黑": "黑", "黑色": "黑",
    "红": "红", "红色": "红", "蓝": "蓝", "蓝色": "蓝", "灰": "灰",
    "灰色": "灰", "绿": "绿", "绿色": "绿", "黄": "黄", "黄色": "黄",
    "粉": "粉", "粉色": "粉", "棕": "棕", "棕色": "棕", "咖": "咖",
}

USE_HINTS = ("跑步", "篮球", "通勤", "休闲", "正式", "运动", "训练", "登山", "健身")

_STOP = re.compile(
    r"有没有|还有|别的|其他|这个|那个|什么|多少|怎么|可以|适合|推荐|找一|找|"
    r"预算|以内|不超过|吗|呢|呀|啊|吧|的|了|我|想|要|有|和|与|请|帮|一"
)


def _keywords(text: str) -> list[str]:
    cleaned = _STOP.sub(" ", normalize_text(text))
    return [
        part for part in re.findall(r"[\u4e00-\u9fff]{1,}|[a-zA-Z0-9]{2,}", cleaned)
        if part.strip()
    ][:6]


def extract_slots(text: str, item: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = normalize_text(text)
    slots: dict[str, Any] = {}

    if item:
        slots["item_id"] = item["id"]
        offer = parse_offer(raw, int(item["price_cents"]))
        if offer is not None:
            slots["offer_cents"] = offer

    match = re.search(r"(\d{2}(?:\.5)?)\s*码", raw)
    if not match:
        match = re.search(r"us\s*(\d+(?:\.5)?)", raw)
    if not match:
        match = re.search(r"(\d{3})\s*mm", raw)
    if match:
        slots["size"] = match.group(1)

    for alias, canonical in COLOR_ALIASES.items():
        if alias in raw:
            slots["color"] = canonical
            break

    budget = re.search(r"预算\s*(\d+(?:\.\d{1,2})?)", raw)
    if not budget:
        budget = re.search(r"(\d+(?:\.\d{1,2})?)\s*(?:元|块)?\s*以内", raw)
    if not budget:
        budget = re.search(r"不超过\s*(\d+(?:\.\d{1,2})?)", raw)
    if budget:
        slots["budget_cents"] = int(round(float(budget.group(1)) * 100))

    order = re.search(r"\b(ord_[a-z0-9]+)\b", raw)
    if order:
        slots["order_no"] = order.group(1)

    for use in USE_HINTS:
        if use in raw:
            slots.setdefault("use", []).append(use)

    keywords = [
        part for part in _keywords(raw)
        if not part.isdigit()
    ]
    if keywords:
        slots["keywords"] = keywords
    return slots
