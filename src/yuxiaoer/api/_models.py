"""控制台请求模型（Pydantic）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SellerMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    images: list[str] = Field(default_factory=list, max_length=9)


class ManualReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class ShipIn(BaseModel):
    company: str = "快递"
    tracking_no: str = Field(min_length=3, max_length=60)


class RefundResolveIn(BaseModel):
    approve: bool = True
    note: str = ""


class ConfirmIn(BaseModel):
    approve: bool = True


class SettingsIn(BaseModel):
    values: dict[str, Any]


class EvalRunIn(BaseModel):
    judge_mode: str = "rules"


class FloorIn(BaseModel):
    floor_price_cents: int = Field(ge=1)


class AccountCreateIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)
    platform: str = "xianyu"


class NotifyChannelIn(BaseModel):
    kind: str
    name: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    min_level: str = "P1"


class CardIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    note: str = ""


class PlatformItemIn(BaseModel):
    platform_item_id: str = Field(min_length=1, max_length=64)


class ItemUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    price_cents: int | None = Field(default=None, ge=1)
    floor_price_cents: int | None = Field(default=None, ge=1)
    delivery_mode: str | None = Field(default=None, pattern="^(physical|virtual)$")
    stock: int | None = Field(default=None, ge=0, le=999999)
    category: str | None = Field(default=None, max_length=120)
    condition: str | None = Field(default=None, max_length=40)


class ItemCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    price_cents: int = Field(ge=1)
    floor_price_cents: int | None = Field(default=None, ge=1)
    delivery_mode: str = Field(default="physical", pattern="^(physical|virtual)$")
    stock: int = Field(default=1, ge=0, le=999999)
    category: str = "闲置好物"
    condition: str = "全新"


class PublishOptionsIn(BaseModel):
    images: list[str] = Field(default_factory=list, max_length=9)
    category: dict[str, Any] = Field(default_factory=dict)
    address: str = ""
    address_geo: dict[str, Any] | None = None
    shipping_method: str = "free"
    postage: float = 0
    quantity: int = Field(default=1, ge=0, le=999999)
    original_price_cents: int | None = None
    mode: str = Field(default="personal", pattern="^(personal|shop)$")


class PriceIn(BaseModel):
    price_cents: int = Field(ge=1)
    stock: int = Field(default=1, ge=0, le=999999)


class PublishConfirmEditIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    price_cents: int | None = Field(default=None, ge=1)
    floor_price_cents: int | None = Field(default=None, ge=1)
    delivery_mode: str | None = Field(default=None, pattern="^(physical|virtual)$")
    stock: int | None = Field(default=None, ge=0, le=999999)
    images: list[str] | None = Field(default=None, max_length=9)
    category_id: str | None = Field(default=None, max_length=64)
    category_name: str | None = Field(default=None, max_length=120)
    channel_cat_id: str | None = Field(default=None, max_length=64)
    tb_cat_id: str | None = Field(default=None, max_length=64)
    leaf_id: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=200)
    shipping_method: str | None = Field(default=None, max_length=20)
    mode: str | None = Field(default=None, pattern="^(personal|shop)$")


class OrderReviewIn(BaseModel):
    text: str = "交易愉快，感谢信任～"


class JobUpdateIn(BaseModel):
    enabled: bool | None = None
    local_time: str | None = None
    interval_seconds: int | None = None


class TestAlertIn(BaseModel):
    level: str = "P1"
    title: str = "通知联调测试"
    body: str = "如果你收到这条消息，说明鱼小二通知渠道已打通。"
