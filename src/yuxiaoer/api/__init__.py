"""控制台 API：按领域拆分的路由包。"""

from fastapi import APIRouter

from . import accounts, catalog, conversations, notify, ops, orders, seller_chat, settings, system

router = APIRouter(prefix="/api")

for _module in (system, conversations, seller_chat, catalog, orders, accounts, notify, ops, settings):
    router.include_router(_module.router)
