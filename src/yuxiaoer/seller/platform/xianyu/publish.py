"""原生闲鱼发布：图片上传、地址解析、发布载荷、个人版/鱼小铺接口。"""

from __future__ import annotations

import json
import mimetypes
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image

from yuxiaoer.core import config

from .mtop import MtopClient

UPLOAD_URL = (
    "https://stream-upload.goofish.com/api/upload.api"
    "?floderId=0&appkey=fleamarket&_input_charset=utf-8"
)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
SELLER_ORIGIN = "https://seller.goofish.com"
SELLER_REFERER = "https://seller.goofish.com/?site=COMMONPRO"


class PublishError(RuntimeError):
    pass


# 没有高德 Key 时的城市级兜底坐标；平台只要求省市区/坐标/POI 展示信息。
CITY_FALLBACK: dict[str, tuple[str, str, str]] = {
    "北京": ("110100", "39.904030,116.407526", "北京市"),
    "上海": ("310100", "31.230416,121.473701", "上海市"),
    "广州": ("440100", "23.129110,113.264385", "广州市"),
    "深圳": ("440300", "22.543096,114.057865", "深圳市"),
    "杭州": ("330100", "30.274085,120.155070", "杭州市"),
    "南京": ("320100", "32.060255,118.796877", "南京市"),
    "苏州": ("320500", "31.298886,120.585316", "苏州市"),
    "成都": ("510100", "30.572815,104.066801", "成都市"),
    "重庆": ("500100", "29.562028,106.551643", "重庆市"),
    "武汉": ("420100", "30.592760,114.305392", "武汉市"),
    "西安": ("610100", "34.341568,108.940174", "西安市"),
    "天津": ("120100", "39.084158,117.200983", "天津市"),
    "长沙": ("430100", "28.228209,112.938814", "长沙市"),
    "郑州": ("410100", "34.746611,113.625367", "郑州市"),
    "青岛": ("370200", "36.067082,120.382639", "青岛市"),
    "宁波": ("330200", "29.868336,121.543990", "宁波市"),
    "厦门": ("350200", "24.479834,118.089425", "厦门市"),
    "福州": ("350100", "26.074508,119.296494", "福州市"),
    "合肥": ("340100", "31.820591,117.227206", "合肥市"),
    "济南": ("370100", "36.651216,117.120105", "济南市"),
    "昆明": ("530100", "25.038891,102.718333", "昆明市"),
    "大连": ("210200", "38.914003,121.614682", "大连市"),
    "沈阳": ("210100", "41.805698,123.431474", "沈阳市"),
    "无锡": ("320200", "31.491169,120.311910", "无锡市"),
    "佛山": ("440600", "23.021478,113.121435", "佛山市"),
    "东莞": ("441900", "23.020673,113.751799", "东莞市"),
}


def _fallback_address(keyword: str) -> dict[str, str] | None:
    for city, (adcode, gps, name) in CITY_FALLBACK.items():
        if city in keyword:
            return {
                "divisionId": adcode,
                "gps": gps,
                "poiId": adcode,
                "poiName": name,
            }
    return None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _read_local(value: str) -> bytes:
    path = Path(value)
    if not path.is_file():
        raise PublishError(f"图片文件不存在：{value}")
    return path.read_bytes()


async def _download(value: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(value, headers={
            "Accept": "image/jpeg,image/png,image/*;q=0.8,*/*;q=0.5",
            "Referer": "https://www.goofish.com/",
            "User-Agent": config.XY_USER_AGENT,
        })
    if response.status_code != 200 or not response.content:
        raise PublishError(f"图片下载失败：HTTP {response.status_code}")
    return response.content, (response.headers.get("content-type") or "image/jpeg").split(";", 1)[0]


async def upload_image(source: str, cookie: str) -> dict[str, Any]:
    source = _text(source)
    if not source:
        raise PublishError("图片地址为空")
    if source.lower().startswith(("http://", "https://")):
        content, content_type = await _download(source)
        name = Path(urlparse(source).path).name or "publish.jpg"
    else:
        content = _read_local(source)
        name = Path(source).name
        content_type = mimetypes.guess_type(name)[0] or "image/jpeg"
    if not content:
        raise PublishError("图片文件为空")
    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.width, image.height
    except Exception as exc:
        raise PublishError(f"图片无法解析：{exc}") from exc
    suffix = Path(name).suffix.lower()
    if suffix not in IMAGE_EXTS:
        suffix = ".jpg"
    filename = f"publish_api_{uuid.uuid4().hex}{suffix}"
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            UPLOAD_URL,
            headers={
                "Accept": "*/*",
                "Cookie": cookie,
                "Origin": SELLER_ORIGIN,
                "Referer": SELLER_REFERER,
                "User-Agent": config.XY_USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
            },
            files={"file": (filename, content, content_type)},
        )
    if response.status_code != 200:
        raise PublishError(f"图片上传失败：HTTP {response.status_code}")
    try:
        body = response.json()
    except Exception:
        raise PublishError("图片上传返回不是 JSON")
    obj = body.get("object") if isinstance(body, dict) else None
    if body.get("success") is not True or not isinstance(obj, dict) or not obj.get("url"):
        raise PublishError("图片上传失败：未返回图片地址")
    pix = str(obj.get("pix") or f"{width}x{height}")
    try:
        pix_w, pix_h = (int(x) for x in pix.lower().split("x", 1))
    except Exception:
        pix_w, pix_h = width, height
    return {
        "extraInfo": {"isH": "false", "isT": "false", "raw": "false"},
        "isQrCode": False,
        "url": str(obj["url"]),
        "heightSize": pix_h,
        "widthSize": pix_w,
        "major": False,
        "type": 0,
        "status": "done",
    }


async def resolve_address(keyword: str) -> dict[str, str]:
    keyword = _text(keyword)
    if not keyword:
        raise PublishError("宝贝所在地不能为空")
    # 没有配置高德 Key 时，用内置城市坐标兜底，避免“只发图片+描述”卡在地址。
    fallback = _fallback_address(keyword)
    if not config.AMAP_KEY:
        if fallback:
            return fallback
        raise PublishError(
            "未配置 AMAP_KEY，且无法从描述识别城市；可在发布设置里写 地址=杭州市/北京市/上海市 等。"
        )
    try:
        return await _resolve_amap(keyword)
    except PublishError:
        if fallback:
            return fallback
        raise


async def _resolve_amap(keyword: str) -> dict[str, str]:
    params = {
        "s": "rsv3", "key": config.AMAP_KEY, "platform": "JS",
        "logversion": "2.0", "sdkversion": "2.0",
        "appname": "https://seller.goofish.com", "keywords": keyword,
        "city": "全国", "citylimit": "false", "datatype": "all",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://restapi.amap.com/v3/assistant/inputtips",
            params=params,
            headers={"Referer": "https://seller.goofish.com/", "User-Agent": config.XY_USER_AGENT},
        )
    try:
        body = response.json()
    except Exception:
        raise PublishError("地址解析返回不是 JSON")
    if str(body.get("status")) != "1":
        raise PublishError(f"地址解析失败：{body.get('info') or '高德接口异常'}")
    for tip in body.get("tips") or []:
        if not isinstance(tip, dict):
            continue
        location = _text(tip.get("location"))
        adcode = _text(tip.get("adcode"))
        poi_id = _text(tip.get("id"))
        name = _text(tip.get("name"))
        if not location or not adcode or not poi_id or not name:
            continue
        try:
            lon, lat = (float(x) for x in location.split(",", 1))
        except Exception:
            continue
        return {
            "divisionId": adcode,
            "gps": f"{lat:.6f},{lon:.6f}",
            "poiId": poi_id,
            "poiName": name,
        }
    raise PublishError("地址解析没有找到可用 POI")


def _category_label(category: dict[str, Any]) -> dict[str, Any]:
    cat_id = _text(category.get("cat_id") or category.get("catId"))
    cat_name = _text(category.get("cat_name") or category.get("catName"))
    channel_id = _text(category.get("channel_cat_id") or category.get("channelCatId"))
    channel_name = _text(category.get("channel_cat_name") or category.get("channelCatName")) or cat_name
    tb_id = _text(category.get("tb_cat_id") or category.get("tbCatId"))
    if not (cat_id or channel_id) or not (cat_name or channel_name):
        raise PublishError("发布分类缺少 cat_id/channel_cat_id 或分类名称")
    return {
        "channelCateName": channel_name,
        "valueId": None,
        "channelCateId": channel_id,
        "valueName": None,
        "tbCatId": tb_id,
        "subPropertyId": None,
        "labelType": "common",
        "subValueId": None,
        "labelId": None,
        "propertyName": "分类",
        "isUserClick": "1",
        "isUserCancel": None,
        "from": "newPublishChoice",
        "propertyId": "-10000",
        "labelFrom": "newPublish",
        "text": cat_name or channel_name,
        "properties": f"-10000##分类:{channel_id or cat_id}##{cat_name or channel_name}",
    }


def _post_fee(publish: dict[str, Any]) -> dict[str, Any]:
    method = _text(publish.get("shipping_method")) or "free"
    pickup = bool(publish.get("support_pickup", False))
    if method == "free":
        return {"canFreeShipping": True, "supportFreight": True, "onlyTakeSelf": pickup}
    if method == "none":
        return {"canFreeShipping": False, "supportFreight": False, "onlyTakeSelf": pickup}
    if method == "fixed":
        postage = float(publish.get("postage") or 0)
        if postage < 0 or postage > 1000:
            raise PublishError("运费必须在 0–1000 元之间")
        return {
            "canFreeShipping": False, "supportFreight": True, "onlyTakeSelf": pickup,
            "postPriceInCent": str(round(postage * 100)), "templateId": "0",
        }
    if method in ("distance", "template"):
        return {"canFreeShipping": False, "supportFreight": True, "onlyTakeSelf": pickup, "templateId": "-100"}
    raise PublishError("发货方式无效")


async def build_payload(item: dict[str, Any], publish: dict[str, Any]) -> dict[str, Any]:
    title = _text(item.get("title"))
    description = _text(item.get("description"))
    if not title or not description:
        raise PublishError("商品标题和描述不能为空")
    price = int(item.get("price_cents") or 0)
    if price <= 0:
        raise PublishError("商品售价必须大于 0")
    images = [str(x).strip() for x in (publish.get("images") or []) if str(x).strip()]
    if not images:
        raise PublishError("请至少提供一张商品图片 URL/本地路径")
    image_items = []
    for idx, image in enumerate(images[:9], 1):
        uploaded = await upload_image(image, publish["_cookie"])
        uploaded["major"] = idx == 1
        image_items.append(uploaded)
    category = publish.get("category") or {}
    label = _category_label(category)
    address = publish.get("address_geo")
    if not isinstance(address, dict) or not address.get("poiId"):
        address = await resolve_address(_text(publish.get("address")))
    payload = {
        "freebies": False,
        "itemTypeStr": "b",
        "quantity": int(publish.get("quantity") or item.get("stock") or 1),
        "simpleItem": "true",
        "imageInfoDOList": image_items,
        "itemTextDTO": {"desc": description, "title": title, "titleDescSeparate": True},
        "itemLabelExtList": [label],
        "itemPriceDTO": {
            "origPriceInCent": str(int(publish.get("original_price_cents") or price)),
            "priceInCent": str(price),
        },
        "userRightsProtocols": [],
        "itemPostFeeDTO": _post_fee(publish),
        "itemAddrDTO": address,
        "defaultPrice": False,
        "itemCatDTO": {
            "catId": _text(category.get("cat_id") or category.get("catId")),
            "catName": _text(category.get("cat_name") or category.get("catName")),
            "channelCatId": _text(category.get("channel_cat_id") or category.get("channelCatId")),
            "leafId": _text(category.get("leaf_id") or category.get("leafId")),
            "tbCatId": _text(category.get("tb_cat_id") or category.get("tbCatId")),
        },
        "uniqueCode": f"{int(time.time() * 1000)}{str(item.get('id') or '')[-4:]}",
        "sourceId": "pcMainPublish",
        "bizcode": "pcMainPublish",
        "publishScene": "pcMainPublish",
    }
    return payload


def _find_ref(value: Any) -> tuple[str | None, str | None]:
    item_id = None
    item_url = None
    if isinstance(value, dict):
        for key, current in value.items():
            normalized = str(key).lower()
            if normalized in {"itemid", "item_id", "idleitemid"} and current is not None:
                item_id = _text(current) or item_id
            elif normalized in {"itemurl", "item_url", "url"} and isinstance(current, str):
                if "goofish.com" in current:
                    item_url = current
        for current in value.values():
            nested_id, nested_url = _find_ref(current)
            item_id = item_id or nested_id
            item_url = item_url or nested_url
    elif isinstance(value, list):
        for current in value:
            nested_id, nested_url = _find_ref(current)
            item_id = item_id or nested_id
            item_url = item_url or nested_url
    if item_id and not item_url:
        item_url = f"https://www.goofish.com/item?id={item_id}"
    return item_id, item_url


async def publish(client: MtopClient, item: dict[str, Any], publish_opts: dict[str, Any]) -> dict[str, Any]:
    publish_opts = {**publish_opts, "_cookie": client.cookies}
    payload = await build_payload(item, publish_opts)
    mode = _text(publish_opts.get("mode")) or "personal"
    payload_for_api = dict(payload)
    if mode == "shop":
        payload_for_api.update({
            "sourceId": "pcBackendPublish", "bizcode": "pcMainPublish",
            "publishScene": "pcBackendPublish",
        })
        result = await client.call(
            "mtop.idle.pc.backend.idleitem.publish", "1.0",
            {"inputJson": json.dumps(payload_for_api, ensure_ascii=False, separators=(",", ":"))},
            origin=SELLER_ORIGIN,
            extra_params={"spm_cnt": "a21107h.42826273.0.0", "idle_site_biz_code": "COMMONPRO"},
            extra_headers={"idle_site_biz_code": "COMMONPRO"},
        )
    else:
        result = await client.call(
            "mtop.idle.pc.idleitem.publish", "1.0", payload,
            origin="https://www.goofish.com",
            extra_params={"spm_cnt": "a21ybx.publish.0.0"},
        )
    item_id, item_url = _find_ref(result.data)
    if not item_id:
        raise PublishError("发布接口未返回商品 ID")
    return {"platform_item_id": item_id, "url": item_url or f"https://www.goofish.com/item?id={item_id}"}
