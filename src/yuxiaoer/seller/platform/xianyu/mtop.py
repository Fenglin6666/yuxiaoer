"""原生闲鱼 mtop 协议的最小实现。

行为参考社区公开实现与抓包事实，代码为本项目 clean-room 实现：
- `_m_h5_tk` 前缀 + 时间戳 + appKey + 紧凑 JSON 的 MD5 签名
- form-urlencoded `data={"data": <json>}`
- Set-Cookie 增量合并
- token 过期时用响应新 Cookie 重签重试
"""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from yuxiaoer.core import config

APP_KEY = "34839810"
API_BASE = "https://h5api.m.goofish.com/h5"
TOKEN_EXPIRED_HINTS = (
    "TOKEN_EXOIRED", "TOKEN_EXPIRED", "FAIL_SYS_TOKEN_EMPTY",
    "SESSION_EXPIRED", "TOKEN_EMPTY", "令牌为空", "已掉线", "请重新登录",
)
SESSION_EXPIRED_HINTS = ("SESSION_EXPIRED", "请重新登录", "已掉线")


class MtopError(RuntimeError):
    def __init__(self, message: str, *, ret: str = "", api: str = "", token_expired: bool = False,
                 session_expired: bool = False, response: dict[str, Any] | None = None):
        super().__init__(message)
        self.ret = ret
        self.api = api
        self.token_expired = token_expired
        self.session_expired = session_expired
        self.response = response or {}


def parse_cookies(raw: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in (raw or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            result[key] = value.strip()
    return result


def cookie_string(values: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in values.items() if k)


def merge_set_cookies(cookie_str: str, headers: list[str]) -> tuple[str, dict[str, str]]:
    values = parse_cookies(cookie_str)
    changed: dict[str, str] = {}
    for header in headers:
        if "=" not in header:
            continue
        first = header.split(";", 1)[0]
        key, value = first.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key:
            continue
        if "max-age=0" in header.lower() or value == "":
            values.pop(key, None)
            changed.pop(key, None)
            continue
        values[key] = value
        changed[key] = value
    return cookie_string(values), changed


def generate_sign(t: str, token: str, data: str, app_key: str = APP_KEY) -> str:
    raw = f"{token}&{t}&{app_key}&{data}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_mid() -> str:
    return f"{int(1000 * random.random())}{int(time.time() * 1000)} 0"


def generate_uuid() -> str:
    return f"-{int(time.time() * 1000)}1"


def new_device_id(user_id: str = "") -> str:
    base = str(uuid.uuid4())
    return f"{base}-{user_id}" if user_id else base


def token_expired(ret: list[Any] | str) -> bool:
    text = " ".join(str(x) for x in (ret if isinstance(ret, list) else [ret]))
    return any(h in text for h in TOKEN_EXPIRED_HINTS)


def session_expired(ret: list[Any] | str) -> bool:
    text = " ".join(str(x) for x in (ret if isinstance(ret, list) else [ret]))
    return any(h in text for h in SESSION_EXPIRED_HINTS)


@dataclass
class MtopResult:
    data: dict[str, Any]
    cookies: str
    ret: list[str] = field(default_factory=list)
    set_cookies: dict[str, str] = field(default_factory=dict)


class MtopClient:
    """一个账号的 mtop 客户端（无状态，可复用 Cookie 字符串）。"""

    def __init__(self, cookies: str, *, device_id: str = "", user_agent: str | None = None,
                 timeout: float = 20.0):
        self.cookies = cookies or ""
        self.device_id = device_id or ""
        self.user_agent = user_agent or config.XY_USER_AGENT
        self.timeout = timeout

    def _cookie_map(self) -> dict[str, str]:
        return parse_cookies(self.cookies)

    def _sign_token(self) -> str:
        token = self._cookie_map().get("_m_h5_tk", "")
        return token.split("_")[0] if token else ""

    def _headers(self, *, origin: str = "https://www.goofish.com") -> dict[str, str]:
        return {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": self.cookies.replace("\n", "").replace("\r", ""),
            "origin": origin,
            "referer": f"{origin}/",
            "user-agent": self.user_agent,
        }

    async def call(
        self,
        api: str,
        version: str = "1.0",
        data: dict[str, Any] | None = None,
        *,
        origin: str = "https://www.goofish.com",
        extra_params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        retry_on_token: bool = True,
        timeout: float | None = None,
    ) -> MtopResult:
        data_value = json.dumps(data or {}, separators=(",", ":"), ensure_ascii=False)
        last_error: MtopError | None = None
        for attempt in range(2 if retry_on_token else 1):
            t = str(int(time.time() * 1000))
            params = {
                "jsv": "2.7.2",
                "appKey": APP_KEY,
                "t": t,
                "sign": generate_sign(t, self._sign_token(), data_value),
                "v": version,
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": api,
                "sessionOption": "AutoLoginOnly",
            }
            if extra_params:
                params.update({k: str(v) for k, v in extra_params.items()})
            try:
                headers = self._headers(origin=origin)
                if extra_headers:
                    headers.update(extra_headers)
                async with httpx.AsyncClient(timeout=timeout or self.timeout, follow_redirects=True) as client:
                    response = await client.post(
                        f"{API_BASE}/{api}/{version}/",
                        params=params,
                        data={"data": data_value},
                        headers=headers,
                    )
                try:
                    payload = response.json()
                except Exception:
                    raise MtopError(
                        f"{api} 返回非 JSON：{response.text[:160]}", api=api,
                        response={"status": response.status_code},
                    )
                set_headers = response.headers.get_list("set-cookie")
                if set_headers:
                    self.cookies, changed = merge_set_cookies(self.cookies, set_headers)
                else:
                    changed = {}
                ret = payload.get("ret", [])
                if isinstance(ret, str):
                    ret = [ret]
                ret_text = " ".join(str(x) for x in ret)
                if "SUCCESS" in ret_text:
                    return MtopResult(
                        data=payload.get("data") or {}, cookies=self.cookies,
                        ret=[str(x) for x in ret], set_cookies=changed,
                    )
                last_error = MtopError(
                    ret_text or f"{api} 调用失败", ret=ret_text, api=api,
                    token_expired=token_expired(ret),
                    session_expired=session_expired(ret),
                    response=payload,
                )
                if attempt == 0 and retry_on_token and last_error.token_expired and changed.get("_m_h5_tk"):
                    continue
                raise last_error
            except MtopError:
                raise
            except httpx.HTTPError as exc:
                raise MtopError(f"{api} 网络请求失败：{exc}", api=api) from exc
        raise last_error or MtopError(f"{api} 调用失败", api=api)

    async def get_im_token(self) -> tuple[str, str]:
        """返回 (accessToken, deviceId)。"""
        device_id = self.device_id or new_device_id(self._cookie_map().get("unb", ""))
        self.device_id = device_id
        data_value = json.dumps(
            {"appKey": "444e9908a51d1cb236a27862abc769c9", "deviceId": device_id},
            separators=(",", ":"),
        )
        result = await self.call(
            "mtop.taobao.idlemessage.pc.login.token", "1.0", json.loads(data_value),
            extra_params={
                "dangerouslySetWindvaneParams": "%5Bobject%20Object%5D",
                "smToken": "token", "queryToken": "sm", "sm": "sm",
                "spm_cnt": "a21ybx.im.0.0",
                "spm_pre": "a21ybx.home.sidebar.1.4c053da6vYwnmf",
                "log_id": "4c053da6vYwnmf",
            },
        )
        token = result.data.get("accessToken") if isinstance(result.data, dict) else None
        if not token:
            raise MtopError("登录成功但未返回 IM accessToken", api="mtop.taobao.idlemessage.pc.login.token")
        returned_device = str(result.data.get("deviceId") or device_id)
        self.device_id = returned_device
        return str(token), returned_device

    async def call_sold_orders(self, page: int = 1, *, rows: int = 30, query_code: str = "ALL") -> dict[str, Any]:
        result = await self.call(
            "mtop.taobao.idle.trade.merchant.sold.get", "1.0",
            {
                "pageNumber": page,
                "rowsPerPage": rows,
                "orderIds": "",
                "queryCode": query_code,
                "orderSearchParam": "{}",
            },
            origin="https://seller.goofish.com",
            extra_params={"valueType": "string", "spm_cnt": "a21107h.42826273.0.0"},
        )
        return result.data

    async def call_refund_orders(self, dispute_status: str = "1") -> dict[str, Any]:
        result = await self.call(
            "mtop.taobao.idle.merchant.refund.list", "1.0",
            {
                "pageNumber": 1,
                "rowsPerPage": 20,
                "queryType": "refund",
                "refundSearchParam": {"disputeStatus": dispute_status, "queryCode": "ALL"},
            },
        )
        return result.data

    async def confirm_shipping(self, order_id: str, trade_text: str = "") -> dict[str, Any]:
        result = await self.call(
            "mtop.taobao.idle.logistic.consign.dummy", "1.0",
            {
                "orderId": order_id,
                "tradeText": trade_text,
                "picList": [],
                "newUnconsign": True,
            },
        )
        return result.data

    async def polish_item(self, item_id: str) -> dict[str, Any]:
        result = await self.call("mtop.taobao.idle.item.polish", "1.0", {"itemId": item_id})
        return result.data

    async def offline_items(self, item_ids: list[str]) -> dict[str, Any]:
        result = await self.call(
            "mtop.alibaba.idle.seller.pc.item.batch.offline", "1.0",
            {"itemIds": ",".join(str(x) for x in item_ids if x)},
            origin="https://seller.goofish.com",
            extra_params={"needLoginPC": "true", "spm_cnt": "a21107h.42826273.0.0"},
            extra_headers={"idle_site_biz_code": "COMMONPRO"},
        )
        return result.data

    async def update_price(self, item_id: str, price_yuan: float, quantity: int) -> dict[str, Any]:
        result = await self.call(
            "mtop.alibaba.idle.seller.pc.item.info.update", "1.0",
            {"itemId": str(item_id), "price": price_yuan, "quantity": int(quantity)},
            origin="https://seller.goofish.com",
            extra_params={"needLoginPC": "true", "accountSite": "xianyu"},
            extra_headers={"idle_site_biz_code": "COMMONPRO"},
        )
        return result.data

    async def publish_personal(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.call(
            "mtop.idle.pc.idleitem.publish", "1.0", payload,
            origin="https://www.goofish.com",
            extra_params={"spm_cnt": "a21ybx.publish.0.0"},
        )
        return result.data

    async def recommend_category(self, title: str, description: str, account_id: str = "") -> list[dict[str, Any]]:
        data = {
            "title": title.strip(),
            "lockCpv": False,
            "multiSKU": False,
            "publishScene": "pcBackendPublish",
            "scene": "shopPcPublish",
            "description": description.strip(),
            "uniqueCode": f"{int(time.time() * 1000)}{account_id[-4:]}",
        }
        result = await self.call(
            "mtop.taobao.idle.kgraph.pc.property.recommend", "2.0", data,
            origin="https://seller.goofish.com",
            extra_params={"spm_cnt": "a21107h.42829679.0.0", "spm_pre": "a21107h.42829791.0.0"},
            extra_headers={"idle_site_biz_code": "COMMONPRO"},
            timeout=20,
        )
        return _parse_category_candidates(result.data)

    async def list_shop_items(self, page_number: int = 1, page_size: int = 20, item_status: str = "0") -> dict[str, Any]:
        result = await self.call(
            "mtop.alibaba.idle.seller.pc.common.item.search", "1.0",
            {
                "pageNo": page_number, "pageSize": page_size, "bizType": "commonPro",
                "searchRequest": "{}", "itemStatus": item_status,
            },
            origin="https://seller.goofish.com",
            extra_params={"spm_cnt": "a21107h.42826273.0.0", "needLoginPC": "true", "accountSite": "xianyu"},
            extra_headers={"idle_site_biz_code": "COMMONPRO"},
        )
        return result.data

    async def list_personal_items(self, page_number: int = 1, page_size: int = 20, user_id: str = "") -> dict[str, Any]:
        result = await self.call(
            "mtop.idle.web.xyh.item.list", "1.0",
            {
                "needGroupInfo": False, "pageNumber": page_number, "pageSize": page_size,
                "groupName": "在售", "groupId": "58877261", "defaultGroup": True,
                "userId": user_id,
            },
            origin="https://www.goofish.com",
            extra_params={"spm_cnt": "a21ybx.im.0.0", "spm_pre": "a21ybx.collection.menu.1.272b5141NafCNK"},
        )
        return result.data


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _parse_category_candidates(response: Any) -> list[dict[str, Any]]:
    """解析分类推荐 cardList；只保留可实际用于发布的候选。"""
    if not isinstance(response, dict):
        return []
    data = response.get("data") if isinstance(response.get("data"), dict) else response
    cards = data.get("cardList") or []
    if isinstance(cards, str):
        try:
            cards = json.loads(cards)
        except Exception:
            cards = []
    predict = data.get("categoryPredictResult")
    if isinstance(predict, str):
        try:
            predict = json.loads(predict)
        except Exception:
            predict = None
    predict = predict if isinstance(predict, dict) else {}
    out: list[dict[str, Any]] = []
    for card in cards if isinstance(cards, list) else []:
        card_data = card.get("cardData") if isinstance(card, dict) else None
        if isinstance(card_data, str):
            try:
                card_data = json.loads(card_data)
            except Exception:
                card_data = None
        if not isinstance(card_data, dict) or _text(card_data.get("propertyId")) != "-10000":
            continue
        for value in card_data.get("valuesList") or []:
            if not isinstance(value, dict):
                continue
            transport = value.get("transportData") if isinstance(value.get("transportData"), dict) else {}
            merged = {**transport, **value}
            cat_id = _text(merged.get("catId") or merged.get("categoryId") or predict.get("catId"))
            cat_name = _text(merged.get("catName") or merged.get("valueName") or predict.get("catName"))
            channel_id = _text(merged.get("channelCatId") or merged.get("channelCateId") or
                               merged.get("channelCategoryId") or predict.get("channelCatId"))
            channel_name = _text(merged.get("channelCatName") or merged.get("channelCateName") or
                                 predict.get("channelCatName")) or cat_name
            leaf_id = _text(merged.get("leafId") or predict.get("leafId"))
            tb_id = _text(merged.get("tbCatId") or merged.get("taobaoCategoryId") or predict.get("tbCatId"))
            if not cat_name and not channel_name:
                continue
            out.append({
                "cat_id": cat_id,
                "cat_name": cat_name or channel_name,
                "channel_cat_id": channel_id,
                "channel_cat_name": channel_name,
                "leaf_id": leaf_id,
                "tb_cat_id": tb_id,
            })
    return out
