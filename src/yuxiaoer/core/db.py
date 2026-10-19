"""SQLite 存储层：WAL、单写连接、全量 schema。

设计要点：
- 读走同一条 aiosqlite 连接（WAL 快照读，本机量级足够）；
- 写操作经 `lock` 串行（应用层单写队列的最后一层兜底）；
- 业务状态迁移由 state.py 的条件 UPDATE 完成，不依赖读后写。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  nickname TEXT NOT NULL,
  platform TEXT NOT NULL DEFAULT 'xianyu',
  status TEXT NOT NULL DEFAULT 'online',
  last_heartbeat_at TEXT,
  cookie_expires_at TEXT,
  detail TEXT,
  updated_at TEXT NOT NULL,
  session_state TEXT NOT NULL DEFAULT 'authenticated',
  access_token_masked TEXT,
  access_expires_at TEXT,
  refresh_expires_at TEXT,
  ws_token_expires_at TEXT,
  h5_token_expires_at TEXT,
  last_refresh_at TEXT,
  qr_session_id TEXT,
  qr_expires_at TEXT,
  is_active INTEGER NOT NULL DEFAULT 0,
  refresh_policy_json TEXT,
  meta_json TEXT,
  platform_user_id TEXT,
  cookies TEXT,
  cookie_updated_at TEXT,
  disable_reason TEXT,
  ws_state TEXT DEFAULT 'disconnected',
  last_ws_at TEXT,
  access_token TEXT,
  device_id TEXT
);

CREATE TABLE IF NOT EXISTS account_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id TEXT NOT NULL,
  event TEXT NOT NULL,
  detail_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_events ON account_events(account_id, id);

CREATE TABLE IF NOT EXISTS delivery_cards (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'available',
  use_count INTEGER NOT NULL DEFAULT 0,
  max_use INTEGER NOT NULL DEFAULT 1,
  order_id TEXT,
  note TEXT,
  expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_item ON delivery_cards(item_id, status);

CREATE TABLE IF NOT EXISTS delivery_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  card_id TEXT,
  status TEXT NOT NULL,
  error TEXT,
  content_snippet TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_delivery_order ON delivery_attempts(order_id, id);

CREATE TABLE IF NOT EXISTS notify_channels (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  config_json TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  min_level TEXT NOT NULL DEFAULT 'P1',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id TEXT,
  alert_id TEXT,
  level TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  response TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notify_logs ON notification_logs(id);

CREATE TABLE IF NOT EXISTS external_api_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint TEXT NOT NULL,
  client_ip TEXT,
  secret_masked TEXT,
  account_id TEXT,
  status TEXT NOT NULL,
  detail_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_external_api_logs ON external_api_logs(id);

CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  platform_item_id TEXT,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  price_cents INTEGER NOT NULL,
  floor_price_cents INTEGER NOT NULL,
  max_discount_pct INTEGER NOT NULL DEFAULT 15,
  category TEXT,
  condition TEXT,
  delivery_mode TEXT NOT NULL DEFAULT 'physical',
  stock INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft',
  card_content TEXT,
  link_url TEXT,
  image_hint TEXT,
  knowledge_version INTEGER NOT NULL DEFAULT 0,
  relist_count INTEGER NOT NULL DEFAULT 0,
  relist_limit INTEGER NOT NULL DEFAULT 3,
  sold_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  listed_at TEXT,
  offline_reason TEXT,
  meta_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);

CREATE TABLE IF NOT EXISTS buyers (
  id TEXT PRIMARY KEY,
  nick TEXT NOT NULL,
  note TEXT,
  deal_count INTEGER NOT NULL DEFAULT 0,
  blacklist INTEGER NOT NULL DEFAULT 0,
  source TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  buyer_id TEXT NOT NULL,
  item_id TEXT,
  session_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  handoff INTEGER NOT NULL DEFAULT 0,
  handoff_until TEXT,
  handoff_reason TEXT,
  unread_for_owner INTEGER NOT NULL DEFAULT 0,
  bargain_round INTEGER NOT NULL DEFAULT 0,
  last_message_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  meta_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_conv_buyer ON conversations(buyer_id, item_id);
CREATE INDEX IF NOT EXISTS idx_conv_last ON conversations(last_message_at);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  direction TEXT NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  external_id TEXT,
  session_id TEXT,
  turn_id TEXT,
  status TEXT NOT NULL DEFAULT 'received',
  meta_json TEXT,
  created_at TEXT NOT NULL,
  processed INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_external ON messages(external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  platform_order_id TEXT,
  item_id TEXT NOT NULL,
  buyer_id TEXT NOT NULL,
  quantity INTEGER NOT NULL DEFAULT 1,
  amount_cents INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  address TEXT,
  buyer_note TEXT,
  tracking_company TEXT,
  tracking_no TEXT,
  refund_reason TEXT,
  refund_note TEXT,
  idempotency_key TEXT UNIQUE,
  delivery_card_id TEXT,
  reviewed_at TEXT,
  reviewed_text TEXT,
  platform_status TEXT,
  account_id TEXT,
  created_at TEXT NOT NULL,
  paid_at TEXT,
  shipped_at TEXT,
  delivered_at TEXT,
  done_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_id, item_id);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  topic TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  session_id TEXT,
  created_at TEXT NOT NULL,
  consumed_at TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic, status);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);

CREATE TABLE IF NOT EXISTS turns (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'processing',
  gateway_json TEXT,
  intent TEXT,
  action TEXT,
  reply_text TEXT,
  handoff INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  steps INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_turns_conv ON turns(conversation_id, started_at);

CREATE TABLE IF NOT EXISTS tool_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  turn_id TEXT,
  session_id TEXT,
  agent TEXT NOT NULL,
  tool TEXT NOT NULL,
  args_json TEXT,
  result_json TEXT,
  ok INTEGER NOT NULL DEFAULT 1,
  error TEXT,
  latency_ms INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tools_session ON tool_calls(session_id);

CREATE TABLE IF NOT EXISTS confirmations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  preview_json TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  source TEXT,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_confirm_status ON confirmations(status, created_at);

CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY,
  level TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  conversation_id TEXT,
  order_id TEXT,
  meta_json TEXT,
  created_at TEXT NOT NULL,
  ack_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, created_at);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  detail_json TEXT,
  result TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts);

CREATE TABLE IF NOT EXISTS outbox (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  buyer_id TEXT,
  item_id TEXT,
  text TEXT NOT NULL,
  session_id TEXT,
  send_after TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  meta_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox(status, send_after);

CREATE TABLE IF NOT EXISTS kb_sources (
  id TEXT PRIMARY KEY,
  namespace TEXT NOT NULL,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  origin TEXT,
  content TEXT NOT NULL,
  meta_json TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'live',
  content_hash TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_source_ns ON kb_sources(namespace, status);

CREATE TABLE IF NOT EXISTS kb_chunks (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  namespace TEXT NOT NULL,
  ord INTEGER NOT NULL DEFAULT 0,
  text TEXT NOT NULL,
  meta_json TEXT,
  tombstone INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_chunk_source ON kb_chunks(source_id);

CREATE TABLE IF NOT EXISTS patrol_jobs (
  name TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  interval_seconds INTEGER,
  schedule_json TEXT,
  next_run_at TEXT,
  last_run_at TEXT,
  last_status TEXT,
  last_detail TEXT,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS eval_cases (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  input TEXT NOT NULL,
  expected_category TEXT NOT NULL,
  expected_action TEXT NOT NULL,
  must_include TEXT,
  must_not TEXT,
  item_id TEXT,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS eval_runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  total INTEGER NOT NULL DEFAULT 0,
  passed INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  score REAL NOT NULL DEFAULT 0,
  judge_mode TEXT NOT NULL DEFAULT 'rules',
  detail_json TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purpose TEXT,
  ok INTEGER NOT NULL DEFAULT 1,
  latency_ms INTEGER,
  error TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
  key TEXT PRIMARY KEY,
  result_json TEXT,
  created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.conn: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()
        self.fts_enabled = False

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        waits = (
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA foreign_keys=ON",
            "PRAGMA busy_timeout=5000",
        )
        for pragma in waits:
            await self.conn.execute(pragma)
        await self.conn.executescript(SCHEMA)
        await self._migrate()
        try:
            await self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5("
                "chunk_id UNINDEXED, namespace UNINDEXED, search_text)"
            )
            self.fts_enabled = True
        except Exception:
            self.fts_enabled = False
        await self.conn.commit()

    async def _migrate(self) -> None:
        """给上一版数据库补列；新库由 SCHEMA 直接建全。"""
        assert self.conn is not None
        additions = {
            "accounts": {
                "session_state": "TEXT NOT NULL DEFAULT 'authenticated'",
                "access_token_masked": "TEXT",
                "access_expires_at": "TEXT",
                "refresh_expires_at": "TEXT",
                "ws_token_expires_at": "TEXT",
                "h5_token_expires_at": "TEXT",
                "last_refresh_at": "TEXT",
                "qr_session_id": "TEXT",
                "qr_expires_at": "TEXT",
                "is_active": "INTEGER NOT NULL DEFAULT 0",
                "refresh_policy_json": "TEXT",
                "meta_json": "TEXT",
                "platform_user_id": "TEXT",
                "cookies": "TEXT",
                "cookie_updated_at": "TEXT",
                "disable_reason": "TEXT",
                "ws_state": "TEXT DEFAULT 'disconnected'",
                "last_ws_at": "TEXT",
                "access_token": "TEXT",
                "device_id": "TEXT",
            },
            "orders": {
                "delivery_card_id": "TEXT",
                "reviewed_at": "TEXT",
                "reviewed_text": "TEXT",
                "platform_status": "TEXT",
                "account_id": "TEXT",
            },
        }
        for table, columns in additions.items():
            cur = await self.conn.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in await cur.fetchall()}
            await cur.close()
            for name, ddl in columns.items():
                if name not in existing:
                    try:
                        await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                    except Exception:
                        pass
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> tuple[int, int | None]:
        assert self.conn is not None, "database not connected"
        async with self.lock:
            cur = await self.conn.execute(sql, tuple(params))
            await self.conn.commit()
            return cur.rowcount, cur.lastrowid

    async def executescript(self, script: str) -> None:
        assert self.conn is not None
        async with self.lock:
            await self.conn.executescript(script)
            await self.conn.commit()

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        assert self.conn is not None
        cur = await self.conn.execute(sql, tuple(params))
        rows = await cur.fetchall()
        await cur.close()
        return list(rows)

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        assert self.conn is not None
        cur = await self.conn.execute(sql, tuple(params))
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetchval(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        row = await self.fetchone(sql, params)
        if row is None:
            return default
        return row[0]

    async def count(self, table: str, where: str = "1=1", params: Iterable[Any] = ()) -> int:
        value = await self.fetchval(f"SELECT COUNT(*) FROM {table} WHERE {where}", params, 0)
        return int(value or 0)
