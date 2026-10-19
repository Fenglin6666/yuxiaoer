"""文本解析：商品匹配、价格/成色提取、分类与标题兜底。"""

from __future__ import annotations

import re
from typing import Any


class ParsingMixin:
    def _parse_price_token(token: str) -> int | None:
        token = (token or "").replace("¥", "").replace("￥", "").replace("元", "").replace("块", "").strip()
        m = re.search(r"(\d+(?:\.\d{1,2})?)", token)
        if not m:
            return None
        try:
            return int(round(float(m.group(1)) * 100))
        except ValueError:
            return None

    async def _find_items(self, query: str) -> list[dict[str, Any]]:
        query = re.sub(r"(那个|这件|商品|一下|麻烦|帮我|请|的)", "", query or "").strip()
        rows = await self.db.fetchall(
            "SELECT * FROM items WHERE status IN ('live','sold_out','pending_confirm','offline') ORDER BY updated_at DESC"
        )
        if not query:
            return []
        q = query.lower()
        tokens = [t for t in re.split(r"[\s，,。]+", q) if len(t) >= 2]
        scored: list[tuple[int, dict]] = []
        for row in rows:
            title = row["title"].lower()
            score = 0
            if q == title:
                score = 100
            elif q in title:
                score = 70 + len(q)
            elif title in q:
                score = 60 + len(title)
            else:
                for token in tokens:
                    if token in title:
                        score += 20 + len(token)
            if score:
                scored.append((score, dict(row)))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return []
        top = scored[0][0]
        return [row for score, row in scored if top - score < 15][:5]

    @staticmethod
    def _extract_price(text: str) -> tuple[int | None, str]:
        patterns = [
            r"(?:改价|改价格|调价|价格改)\s*(?:到|为|成|至)?\s*(\d+(?:\.\d{1,2})?)\s*(?:元|块)?",
            r"(?:价格|卖|售价|¥|￥)\s*(\d+(?:\.\d{1,2})?)\s*(?:元|块)?",
            r"(\d+(?:\.\d{1,2})?)\s*(?:元|块)",
            r"(?:到|改成|改为)\s*(\d+(?:\.\d{1,2})?)\s*(?:元|块)?",
        ]
        match = None
        for pat in patterns:
            matches = list(re.finditer(pat, text))
            if matches:
                match = matches[-1]
                break
        if not match:
            return None, text
        try:
            cents = int(round(float(match.group(1)) * 100))
        except ValueError:
            return None, text
        cleaned = text[: match.start()] + " " + text[match.end():]
        cleaned = re.sub(r"(价格|卖|售价)[:：]?\s*$", "", cleaned).strip()
        return cents, cleaned

    @staticmethod
    def _extract_condition(text: str) -> str:
        m = re.search(r"(全新|99新|98新|95新|9成新|8成新|7成新)", text)
        return m.group(1) if m else "自用闲置"

    @staticmethod
    def _fallback_title(text: str, virtual: bool) -> str:
        """描述里只有类型/价格时，从后半句提取一个可用的短标题。"""
        cleaned = re.sub(r"\d+(?:\.\d{1,2})?\s*(?:元|块)?", " ", text or "")
        parts = [p.strip(" -—:：，,。；;") for p in re.split(r"[，,。；;\n]", cleaned)]
        blocked = {"虚拟资料", "虚拟商品", "电子资料", "实物商品", "拍下自动发", "拍下后自动发", "包邮", "全新", "二手"}
        for part in parts:
            part = re.sub(r"^(虚拟资料|虚拟商品|电子资料|实物商品|商品|标题)[:：]?\s*", "", part).strip()
            if len(part) >= 4 and part not in blocked and not re.fullmatch(r"[虚拟实物资料商品自动发货包邮全新二手\s]+", part):
                return part[:30]
        return "闲置好物" if not virtual else "虚拟资料"

    @staticmethod
    def _category(text: str, virtual: bool) -> str:
        if virtual:
            if re.search(r"考研|英语|数学|小学|初中|高中|学习|真题|题库|课程", text):
                return "教育培训 > 学习资料"
            return "虚拟资源 > 数字素材"
        if re.search(r"手机|iPad|ipad|相机|耳机|Kindle|kindle|数码|电脑", text):
            return "数码 > 闲置数码"
        if re.search(r"挂件|玩偶|手办|潮玩", text):
            return "潮玩 > 毛绒挂件"
        return "闲置 > 其他"
