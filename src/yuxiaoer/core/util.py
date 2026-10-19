"""小工具：时间、ID、金额、中文检索分词。"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, time, timedelta, timezone
from typing import Any

from yuxiaoer.core import config

# ---------------- 时间 ----------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime:
    if not value:
        return now_utc()
    try:
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return now_utc()


def local_now() -> datetime:
    return now_utc().astimezone(config.TZ)


def local_hhmm(dt: datetime | None = None) -> str:
    return (dt or local_now()).astimezone(config.TZ).strftime("%H:%M")


def local_date(dt: datetime | None = None) -> str:
    return (dt or local_now()).astimezone(config.TZ).strftime("%Y-%m-%d")


def human_time(value: str | datetime | None) -> str:
    """给前端用的本地时间 HH:MM / 昨天 / MM-DD."""
    if not value:
        return ""
    dt = parse_iso(value) if isinstance(value, str) else value
    loc = dt.astimezone(config.TZ)
    today = local_now().date()
    if loc.date() == today:
        return loc.strftime("%H:%M")
    if loc.date() == today - timedelta(days=1):
        return "昨天 " + loc.strftime("%H:%M")
    return loc.strftime("%m-%d %H:%M")


def start_of_local_day(offset_days: int = 0) -> datetime:
    d = local_now().date() + timedelta(days=offset_days)
    return datetime.combine(d, time.min, tzinfo=config.TZ).astimezone(timezone.utc)


def next_local_time(hhmm: str, *, after: datetime | None = None) -> datetime:
    h, m = [int(x) for x in hhmm.split(":")]
    base = (after or local_now()).astimezone(config.TZ)
    target = base.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= base:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


# ---------------- ID / JSON ----------------

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def new_id(prefix: str = "", length: int = 14) -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(length))
    return f"{prefix}_{body}" if prefix else body


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


# ---------------- 金额 ----------------

def parse_price_cents(text: str) -> int | None:
    """把 '9.9' / '¥9.90' / '9块9' 解析为分。只做本机级解析。"""
    if not text:
        return None
    t = text.replace("，", ".").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    if not m:
        return None
    try:
        return int(round(float(m.group(1)) * 100))
    except ValueError:
        return None


def yuan(cents: int | None) -> str:
    if cents is None:
        return "-"
    value = cents / 100
    return f"{value:.2f}".rstrip("0").rstrip(".")


def money(cents: int | None) -> str:
    return f"¥{yuan(cents)}"


# ---------------- 中文检索 ----------------

_CJK = re.compile(r"[\u3400-\u9fff]")
_ASCII = re.compile(r"[A-Za-z0-9]+")
_SPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[\u3000\s]+", " ", text)
    return text.strip()


def cjk_tokens(text: str) -> list[str]:
    """中文二元组 + 英文/数字词。

    SQLite FTS5 的 unicode61 分词对连续中文按整段处理，命中率差；
    写入/查询两侧都转成空格分隔的 bigram，即可得到可用的中文 BM25。
    """
    text = normalize_text(text)
    tokens: list[str] = []
    for m in _ASCII.finditer(text):
        tokens.append(m.group(0))
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", text)
    for run in cjk_runs:
        if len(run) == 1:
            tokens.append(run)
            continue
        for i in range(len(run) - 1):
            tokens.append(run[i : i + 2])
    # 去重并保序
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if len(t) > 32:
            t = t[:32]
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def fts_text(text: str) -> str:
    return " ".join(cjk_tokens(text))


def fts_query(text: str, max_terms: int = 24) -> str:
    tokens = cjk_tokens(text)[:max_terms]
    # 用 OR 提高召回；FTS5 的 OR 语法大写
    return " OR ".join(tokens)


def snippet(text: str, n: int = 90) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t if len(t) <= n else t[: n - 1] + "…"


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    k = max(0, min(len(vals) - 1, int(round((pct / 100) * (len(vals) - 1)))))
    return float(vals[k])
