"""文本归一化：只用于规则/检索，不修改入库原文。

三个视图：
- normalize_text：NFKC、小写、去零宽、压空白；
- match_text：再去标点，给关键词/正则；
- contact_text：再去分隔符，给站外引流检测；
- price_text：统一货币符号与中文数字，给议价解析。
"""

from __future__ import annotations

import re
import unicodedata

_ZERO = re.compile(r"[\u200b-\u200d\ufeff]")
_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[\s，。！？!?,.、~～…:：;；\"'“”‘’（）()\[\]【】]+")
_CONTACT_SEP = re.compile(r"[\s\-_.,，。·|/\\]+")

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}
_CN_PRICE = re.compile(r"([零一二两三四五六七八九十百千]+)\s*(?=(?:元|块))")


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").lower()
    value = _ZERO.sub("", value)
    return _SPACE.sub(" ", value).strip()


def match_text(text: str) -> str:
    return _PUNCT.sub("", normalize_text(text))


def contact_text(text: str) -> str:
    """去掉空格/标点，专门对付“微 信”“加 V”这类拆字。"""
    return _CONTACT_SEP.sub("", normalize_text(text))


def chinese_to_int(value: str) -> int | None:
    if not value:
        return None
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in _CN_DIGITS:
            number = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
        else:
            return None
    return total + section + number


def price_text(text: str) -> str:
    value = normalize_text(text).replace("￥", "¥").replace("块钱", "块")

    def repl(match: re.Match[str]) -> str:
        number = chinese_to_int(match.group(1))
        return str(number) if number is not None else match.group(1)

    return _CN_PRICE.sub(repl, value)
