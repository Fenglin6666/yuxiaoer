"""运行时装配：数据库、服务、事件订阅、后台循环。"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from yuxiaoer.buyer.conversation.agent import BuyerAgent
from yuxiaoer.buyer.conversation.ingest import IngestService
from yuxiaoer.core import config
from yuxiaoer.core.db import Database
from yuxiaoer.core.events import EventBus
from yuxiaoer.core.llm import LLMClient
from yuxiaoer.core.seed import seed_once
from yuxiaoer.core.settings_service import SettingsService
from yuxiaoer.core.util import human_time, iso, local_now, now_utc
from yuxiaoer.seller.account.accounts import AccountService, SessionKeeper
from yuxiaoer.seller.agent import SellerAgent
from yuxiaoer.seller.commerce.delivery import DeliveryService
from yuxiaoer.seller.commerce.orders import FulfillmentService, OrderService
from yuxiaoer.seller.confirmations import ConfirmationService
from yuxiaoer.seller.conversation.messaging import MessagingService
from yuxiaoer.seller.notifications.alerts import AlertService
from yuxiaoer.seller.notifications.email_gateway import EmailGateway
from yuxiaoer.seller.notifications.notifications import NotificationService
from yuxiaoer.seller.operations.eval import EvalService
from yuxiaoer.seller.operations.metrics import MetricsService
from yuxiaoer.seller.operations.patrol import PatrolService
from yuxiaoer.seller.operations.replay import ReplayService
from yuxiaoer.seller.operations.risk import RiskGuard
from yuxiaoer.seller.platform.channels import BaseChannel, build_channel
from yuxiaoer.seller.platform.xianyu.qrlogin import QRLoginManager
from yuxiaoer.seller.write_queue import WriteQueue
from yuxiaoer.shared.knowledge import KnowledgeService

log = logging.getLogger("yuxiaoer.runtime")


class Runtime:
    def __init__(self):
        self.initialized = False
        self.started_at: str | None = None
        self.db: Database
        self.bus: EventBus
        self.queue: WriteQueue
        self.channel: BaseChannel
        self.settings: SettingsService
        self.alerts: AlertService
        self.notifications: NotificationService
        self.risk: RiskGuard
        self.accounts: AccountService
        self.session_keeper: SessionKeeper
        self.knowledge: KnowledgeService
        self.delivery: DeliveryService
        self.confirmations: ConfirmationService
        self.messaging: MessagingService
        self.buyer: BuyerAgent
        self.seller: SellerAgent
        self.orders: OrderService
        self.fulfillment: FulfillmentService
        self.ingest: IngestService
        self.patrol: PatrolService
        self.metrics: MetricsService
        self.replay: ReplayService
        self.eval: EvalService
        self.llm: LLMClient
        self.db_path: Path | None = None
        self._health_cache: tuple[float, dict[str, Any]] | None = None

    async def initialize(
        self,
        *,
        db_path: Path | str | None = None,
        start_background: bool = True,
    ) -> None:
        if self.initialized:
            return
        self.db_path = Path(db_path) if db_path else config.DB_PATH
        self.db = Database(self.db_path)
        await self.db.connect()
        await seed_once(self.db)
        self.started_at = iso()
        self.bus = EventBus(self.db)
        self.settings = SettingsService(self.db)
        self.queue = WriteQueue(min_interval=2.0, jitter=1.5)
        self.channel = build_channel(self.db)
        self.notifications = NotificationService(self.db)
        self.alerts = AlertService(self.db, self.bus, self.notifications)
        self.risk = RiskGuard(self.db, self.bus)
        self.risk.alerts = self.alerts
        await self.risk.load()
        self.queue.risk_guard = self.risk
        self.llm = LLMClient(self.db)
        await self._apply_llm_setting()
        self.knowledge = KnowledgeService(self.db)
        self.confirmations = ConfirmationService(self.db)
        self.messaging = MessagingService(self.db, self.channel, self.queue, self.alerts, self.settings)
        self.delivery = DeliveryService(self.db, self.bus, self.messaging, self.alerts)
        self.accounts = AccountService(self.db, self.bus, self.alerts, self.settings)
        self.qr_login = QRLoginManager()
        self.accounts.native = True
        self.accounts.qr_manager = self.qr_login
        if hasattr(self.channel, "bind"):
            self.channel.bind(self)
        if hasattr(self.channel, "restart"):
            self.accounts.on_session_refreshed = self.channel.restart
        self.session_keeper = SessionKeeper(self.accounts, self.alerts)
        self.buyer = BuyerAgent(
            self.db, self.bus, self.knowledge, self.messaging, self.alerts,
            self.settings, self.llm, self.confirmations,
        )
        self.seller = SellerAgent(
            self.db, self.bus, self.messaging, self.alerts, self.knowledge,
            self.confirmations, None, self.channel, self.queue, self.settings, self.llm,
        )
        self.orders = OrderService(
            self.db, self.bus, self.messaging, self.alerts, self.knowledge,
            self.channel, self.queue, self.settings,
        )
        self.seller.orders = self.orders
        self.seller.delivery = self.delivery
        self.fulfillment = FulfillmentService(
            self.db, self.bus, self.messaging, self.alerts, self.knowledge,
            self.channel, self.queue, self.settings, self.delivery,
        )
        self.ingest = IngestService(self.db, self.messaging, self.buyer, self.settings)
        self.patrol = PatrolService(
            self.db, self.bus, self.channel, self.queue, self.alerts,
            self.knowledge, self.messaging, self.settings,
        )
        self.seller.set_patrol(self.patrol)
        self.metrics = MetricsService(self.db)
        self.replay = ReplayService(self.db)
        self.eval = EvalService(self.db, self.buyer, self.llm)
        self.email_gateway = EmailGateway(self)

        self.bus.on("order.paid", self.fulfillment.handle_order_paid)

        await self.ensure_defaults()
        await self.knowledge.bootstrap()
        await self.delivery.ensure_all()
        await self.messaging.seller_conversation()
        await self.seller.ensure_welcome()
        await self.bus.replay_pending()

        if start_background:
            self.queue.start()
            self.messaging.start()
            await self.ingest.recover_pending()
            if hasattr(self.channel, "start"):
                await self.channel.start()
            await self.patrol.start()
            await self.session_keeper.start()
            await self.email_gateway.start()
        self.initialized = True
        log.info("鱼小二 runtime ready: %s", self.db_path)

    async def _apply_llm_setting(self) -> None:
        setting = (await self.settings.get("llm_enabled")).lower()
        if setting in ("1", "true", "on") and self.llm.has_key() and config.LLM_ENABLED != "off":
            self.llm.enabled_pref = "on"
        else:
            self.llm.enabled_pref = "off"

    async def ensure_defaults(self) -> None:
        """只保证已有真实账号中有一个当前账号；不再创建演示账号。"""
        rows = await self.db.fetchall("SELECT * FROM accounts ORDER BY updated_at")
        if not rows:
            return
        active = [r for r in rows if r["is_active"]]
        if active:
            return
        target = next((r for r in rows if r["session_state"] in ("authenticated", "expiring")), None)
        if target:
            await self.db.execute("UPDATE accounts SET is_active=1 WHERE id=?", (target["id"],))


    async def apply_settings(self) -> None:
        self.llm.enabled_pref = "auto"
        await self._apply_llm_setting()

    async def shutdown(self) -> None:
        if not getattr(self, "initialized", False):
            return
        self.ingest.stop()
        await self.session_keeper.stop()
        if hasattr(self.channel, "stop"):
            await self.channel.stop()
        await self.messaging.stop()
        await self.patrol.stop()
        await self.email_gateway.stop()
        await self.queue.stop()
        await self.notifications.flush()
        if hasattr(self, "qr_login"):
            await self.qr_login.close()
        await self.db.close()
        self.initialized = False

    # ---------------- 状态 ----------------

    async def channel_health(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force and self._health_cache and now - self._health_cache[0] < 3:
            return self._health_cache[1]
        try:
            health = await self.channel.health()
        except Exception as exc:  # noqa: BLE001
            health = {"online": False, "detail": str(exc), "mode": self.channel.name, "label": self.channel.label}
        self._health_cache = (now, health)
        return health

    async def system_status(self) -> dict[str, Any]:
        account = await self.db.fetchone(
            "SELECT * FROM accounts ORDER BY is_active DESC, updated_at DESC LIMIT 1"
        )
        health = await self.channel_health()
        jobs = await self.patrol.jobs()
        outbox = await self.messaging.outbox_stats()
        account_view = None
        if account:
            account_view = dict(account)
            for key in ("cookies", "access_token", "refresh_policy_json", "meta_json"):
                account_view.pop(key, None)
        secret = config.EXTERNAL_SECRET_KEY or ""
        secret_masked = (secret[:2] + "*" * max(0, len(secret) - 4) + secret[-2:]) if len(secret) > 4 else "*" * len(secret)
        return {
            "app": config.APP_NAME,
            "version": config.VERSION,
            "mode": config.PLATFORM_MODE,
            "channel": {"label": self.channel.label, "name": self.channel.name, **health},
            "account": account_view,
            "accounts_count": await self.db.count("accounts"),
            "active_accounts": await self.db.count("accounts", "is_active=1"),
            "session": self.session_keeper.status(),
            "risk": await self.risk.status(),
            "notify": await self.notifications.stats(),
            "email": {"last_poll_at": self.email_gateway.last_poll_at, **self.email_gateway.last_result},
            "external": {
                "base": "/api/v1/external",
                "secret_masked": secret_masked,
                "docs": "/docs",
                "native": bool(getattr(self.accounts, "native", False)),
            },
            "llm": self.llm.status(),
            "queue": self.queue.stats(),
            "outbox": outbox,
            "events": {"backlog": await self.bus.backlog(), **self.bus.stats()},
            "ingest": self.ingest.stats(),
            "knowledge": await self.knowledge.stats(),
            "jobs": jobs,
            "started_at": self.started_at,
            "started_human": human_time(self.started_at),
            "local_now": local_now().strftime("%Y-%m-%d %H:%M:%S"),
            "db_path": str(self.db_path),
            "settings": await self.settings.public(),
            "uptime_seconds": int((now_utc() - (self._started_dt())).total_seconds()),
        }

    def _started_dt(self):
        from yuxiaoer.core.util import parse_iso
        return parse_iso(self.started_at)

    async def overview(self) -> dict[str, Any]:
        metrics = await self.metrics.overview()
        status = await self.system_status()
        alerts = await self.alerts.list("open", 20)
        return {
            **metrics,
            "system": status,
            "alerts": alerts,
            "recent_conversations": await self.metrics.recent_conversations(8),
            "recent_orders": await self.metrics.recent_orders(8),
        }


runtime = Runtime()
