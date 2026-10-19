"""上架：发布参数补全、预览卡生成、批量发布。"""

from __future__ import annotations

import json
import re
from typing import Any

from yuxiaoer.core.util import dumps, iso, new_id, yuan
from yuxiaoer.shared.toolbox import ToolBox

from ..constants import VIRTUAL_HINTS


class ListingMixin:
    async def _publish_options(self) -> tuple[dict[str, Any] | None, str]:
        """读取店主通过「发布设置」配置的默认发布参数。"""
        raw_images = (await self.settings.get("publish_images")).strip()
        images: list[str] = []
        if raw_images:
            if raw_images.startswith("["):
                try:
                    images = [str(x).strip() for x in json.loads(raw_images) if str(x).strip()]
                except Exception:
                    images = []
            else:
                images = [x.strip() for x in re.split(r"[\n,，]", raw_images) if x.strip()]
        category = {
            "cat_id": (await self.settings.get("publish_cat_id")).strip(),
            "cat_name": (await self.settings.get("publish_cat_name")).strip(),
            "channel_cat_id": (await self.settings.get("publish_channel_cat_id")).strip(),
            "tb_cat_id": (await self.settings.get("publish_tb_cat_id")).strip(),
        }
        address = (await self.settings.get("publish_address")).strip()
        geo_raw = (await self.settings.get("publish_address_geo")).strip()
        geo = None
        if geo_raw:
            try:
                geo = json.loads(geo_raw)
            except Exception:
                geo = None
        options = {
            "images": images,
            "category": category,
            "address": address,
            "shipping_method": (await self.settings.get("publish_shipping_method")).strip() or "free",
            "mode": (await self.settings.get("publish_mode")).strip() or "personal",
            "quantity": 1,
        }
        if isinstance(geo, dict):
            options["address_geo"] = geo
        missing = []
        if not images:
            missing.append("图片")
        if not (category["cat_id"] or category["channel_cat_id"]) or not category["cat_name"]:
            missing.append("分类ID/分类名")
        if not address and not geo:
            missing.append("所在地")
        if missing:
            return None, (
                "发布参数还不全：缺 " + "、".join(missing) + "。\n"
                "先发一条配置，例如：\n"
                "发布设置 图片=https://xx/1.jpg,https://xx/2.jpg 分类ID=123 分类名=虚拟资料 地址=杭州市西湖区\n"
                "可选：频道分类ID=... 淘宝分类ID=... 模式=personal|shop 运费=free|none|fixed"
            )
        return options, ""

    async def _auto_publish_options(
        self, title: str, description: str, raw: str, images: list[str] | None, virtual: bool,
    ) -> tuple[dict[str, Any] | None, str]:
        """根据图片 + 描述自动补全发布参数；分类优先调平台推荐。"""
        image_list = [str(x).strip() for x in (images or []) if str(x).strip()]
        if not image_list:
            raw_images = (await self.settings.get("publish_images")).strip()
            image_list = [x.strip() for x in re.split(r"[\n,，]", raw_images) if x.strip()]
        if not image_list:
            return None, "把商品图片一起发给我（点输入框左侧的图片按钮），我就能按描述自动补参数。"
        category = {
            "cat_id": (await self.settings.get("publish_cat_id")).strip(),
            "cat_name": (await self.settings.get("publish_cat_name")).strip(),
            "channel_cat_id": (await self.settings.get("publish_channel_cat_id")).strip(),
            "tb_cat_id": (await self.settings.get("publish_tb_cat_id")).strip(),
        }
        if not (category["cat_id"] or category["channel_cat_id"]) or not category["cat_name"]:
            recommend = getattr(self.channel, "recommend_category", None)
            if recommend is None:
                return None, "当前通道不支持分类推荐，请先发「发布设置 分类ID=… 分类名=…」。"
            try:
                rows = await recommend(title, description)
            except Exception as exc:
                return None, f"分类自动推荐失败：{str(exc)[:180]}。可以发「发布设置 分类ID=… 分类名=…」手动指定。"
            if not rows:
                return None, "平台没有返回可用分类；请发「发布设置 分类ID=… 分类名=…」。"
            best = rows[0]
            category = {
                "cat_id": str(best.get("cat_id") or ""),
                "cat_name": str(best.get("cat_name") or best.get("channel_cat_name") or ""),
                "channel_cat_id": str(best.get("channel_cat_id") or ""),
                "channel_cat_name": str(best.get("channel_cat_name") or ""),
                "tb_cat_id": str(best.get("tb_cat_id") or ""),
                "leaf_id": str(best.get("leaf_id") or ""),
            }
        address = (await self.settings.get("publish_address")).strip()
        if not address:
            city = re.search(
                r"(北京|上海|广州|深圳|杭州|南京|苏州|成都|重庆|武汉|西安|天津|长沙|郑州|青岛|宁波|厦门|福州|合肥|济南|昆明|大连|沈阳|无锡|佛山|东莞)(?:市)?",
                raw,
            )
            address = city.group(1) + "市" if city else (await self.settings.get("publish_default_address")).strip()
        options = {
            "images": image_list,
            "category": category,
            "address": address or "杭州市",
            "shipping_method": (await self.settings.get("publish_shipping_method")).strip()
            or ("none" if virtual else "free"),
            "mode": (await self.settings.get("publish_mode")).strip() or "personal",
            "quantity": 1,
        }
        geo_raw = (await self.settings.get("publish_address_geo")).strip()
        if geo_raw:
            try:
                geo = json.loads(geo_raw)
                if isinstance(geo, dict):
                    options["address_geo"] = geo
            except Exception:
                pass
        return options, ""

    async def _publish_settings(self, text: str) -> dict[str, Any]:
        raw = re.sub(r"^(发布设置|上架配置|发布参数|设置发布|发布配置)[:：]?\s*", "", text).strip()
        pairs = re.findall(
            r"(频道分类ID|淘宝分类ID|分类ID|分类名|图片|地址|模式|运费)\s*[=:：]\s*(\S+)",
            raw, re.I,
        )
        mapping = {
            "图片": "publish_images",
            "分类ID": "publish_cat_id",
            "分类名": "publish_cat_name",
            "频道分类ID": "publish_channel_cat_id",
            "淘宝分类ID": "publish_tb_cat_id",
            "地址": "publish_address",
            "模式": "publish_mode",
            "运费": "publish_shipping_method",
        }
        if pairs:
            for key, value in pairs:
                await self.settings.set(mapping[key], value.strip())
        options, missing = await self._publish_options()
        if not options:
            if pairs:
                return {"ok": True, "text": "已保存这次设置。\n" + missing + "\n其余参数可以在上架时用图片+描述自动补。"}
            return {"ok": False, "text": missing}
        return {
            "ok": True,
            "text": (
                "发布参数已保存。\n"
                f"图片：{len(options['images'])} 张\n"
                f"分类：{options['category'].get('cat_name') or '—'}（{options['category'].get('cat_id') or options['category'].get('channel_cat_id') or '—'}）\n"
                f"所在地：{options.get('address') or '使用坐标'}\n"
                f"模式：{options.get('mode')} · 运费：{options.get('shipping_method')}\n"
                "现在可以直接说：上架：标题 价格 描述"
            ),
        }

    async def _listing(self, text: str, toolbox: ToolBox, images: list[str] | None = None) -> dict[str, Any]:
        raw = re.sub(r"^(上架|发布|发品|新品|新增商品)[:：]?\s*", "", text).strip()
        if not raw:
            return {"ok": False, "text": "把商品描述一起发我，例如：上架：小学奥数全套资料 9.9元 电子资料，拍下自动发。"}
        card_content = None
        card_match = re.search(r"(?:卡券|卡密|发货内容)[:：]\s*(.+)$", raw, re.S | re.I)
        if card_match:
            card_content = card_match.group(1).strip()[:4000]
            raw = raw[: card_match.start()].strip()
        price, raw_no_price = self._extract_price(raw)
        virtual = any(h in raw for h in VIRTUAL_HINTS) and not any(h in raw for h in ["实物", "包邮"])
        if not price:
            price = await self.settings.get_int("publish_default_price", 990)
        floor_pct = await self.settings.get_int("floor_discount_pct", 85)
        floor = max(1, int(round(price * max(0, min(100, floor_pct)) / 100)))
        lines = [line.strip() for line in raw_no_price.splitlines() if line.strip()]
        first_line = lines[0] if lines else raw_no_price
        title = re.sub(r"^(商品|标题)[:：]", "", first_line).strip(" -—:：")
        rest = ""
        if len(lines) > 1:
            rest = "\n".join(lines[1:]).strip()
        else:
            parts = re.split(r"[，,。；;]", title, maxsplit=1)
            if len(parts) > 1:
                title, rest = parts[0], parts[1].strip()
        # 标题里去掉明显的发货/类型修饰，保留成色等卖点；被去掉的词仍留在描述里
        match = re.search(
            r"\s*(电子资料|虚拟商品|虚拟资料|实物商品|拍下自动发\w*|拍下后自动发\w*|包邮|48小时内发\w*)\s*$",
            title,
        )
        if match:
            title = title[: match.start()]
        title = re.sub(r"\s+", " ", title).strip()
        title = title[:30]
        if len(title) < 2:
            title = self._fallback_title(raw_no_price, virtual)
        # 用"原句去掉标题"得到描述，避免只剩半句
        remainder = first_line.replace(title, "", 1).strip(" ，,。")
        if len(lines) > 1:
            desc_parts = [p for p in (remainder, rest) if p]
            desc = "，".join(dict.fromkeys(desc_parts)).strip()
        else:
            desc = remainder
        if not desc:
            desc = raw_no_price
        policy = (
            "虚拟资料，拍下后自动发网盘链接，链接失效免费补发。"
            if virtual else
            "实物拍摄，包邮，48 小时内发出；二手物品非质量问题不退换。"
        )
        if policy not in desc:
            desc = f"{desc}\n{policy}"
        desc = re.sub(r"([，,。；;])\1+", r"\1", desc).strip()[:1000]
        condition = "电子资料" if virtual else self._extract_condition(raw)
        category = self._category(raw, virtual)
        delivery_mode = "virtual" if virtual else "physical"
        if self.llm.available():
            polished = await self._llm_listing(title, desc, price, delivery_mode)
            if polished:
                title = polished.get("title") or title
                desc = polished.get("description") or desc
        publish_options, missing = await self._auto_publish_options(
            title, desc, raw, images, virtual,
        )
        if not publish_options:
            return {"ok": False, "text": missing}
        item_id = await self._create_pending_item(
            title=title, description=desc, price=price, floor=floor, virtual=virtual,
            condition=condition, category=category, floor_pct=floor_pct, card_content=card_content,
            publish_options=publish_options,
        )
        preview = {
            "kind": "publish_listing", "item_id": item_id, "title": title,
            "description": desc, "price_cents": price, "floor_price_cents": floor,
            "delivery_mode": delivery_mode, "condition": condition, "category": category,
            "price_text": f"¥{yuan(price)}", "has_card": bool(card_content),
            "images": publish_options.get("images") or [],
            "publish_category": (publish_options.get("category") or {}).get("cat_name"),
            "publish_category_id": (publish_options.get("category") or {}).get("cat_id"),
            "publish_channel_cat_id": (publish_options.get("category") or {}).get("channel_cat_id"),
            "publish_tb_cat_id": (publish_options.get("category") or {}).get("tb_cat_id"),
            "publish_leaf_id": (publish_options.get("category") or {}).get("leaf_id"),
            "publish_address": publish_options.get("address"),
            "publish_shipping_method": publish_options.get("shipping_method"),
            "publish_mode": publish_options.get("mode"),
            "stock": publish_options.get("quantity"),
        }
        cfm = await self.confirmations.create(
            "publish_listing", f"发布商品：{title}", preview, {"item_id": item_id}, source="seller_agent"
        )
        card = {"type": "confirmation", "confirmation_id": cfm["id"], "preview": preview}
        await toolbox.call(
            "draft_listing", {"item_id": item_id, "title": title, "price_cents": price},
            lambda: {"item_id": item_id, "status": "pending_confirm"},
        )
        text_out = (
            f"拟好了一版，确认后我再发布 👇\n"
            f"标题：{title}\n价格：¥{yuan(price)}（底价 ¥{yuan(floor)}）\n"
            f"类型：{'虚拟自动发货' if virtual else '实物待发货'}\n"
            "回复「确认」或点卡片按钮发布；回复「取消」放弃。"
        )
        return {"ok": True, "text": text_out, "card": card, "item_id": item_id}

    async def _create_pending_item(
        self, *, title: str, description: str, price: int, floor: int, virtual: bool,
        condition: str, category: str, floor_pct: int, card_content: str | None = None,
        publish_options: dict[str, Any] | None = None,
    ) -> str:
        item_id = new_id("item")
        now = iso()
        await self.db.execute(
            """INSERT INTO items(id,title,description,price_cents,floor_price_cents,max_discount_pct,category,
               condition,delivery_mode,stock,status,card_content,link_url,image_hint,knowledge_version,
               relist_count,relist_limit,sold_count,created_at,updated_at,meta_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id, title, description, price, floor, max(0, 100 - floor_pct), category,
                condition, "virtual" if virtual else "physical", 1 if not virtual else 999,
                "pending_confirm", card_content, None, "📦", 0, 0, 3, 0, now, now,
                dumps({"created_by": "seller_agent", "publish": publish_options or {}}),
            ),
        )
        return item_id

    async def _batch_listing(self, text: str, toolbox: ToolBox) -> dict[str, Any]:
        raw = re.sub(r"^(批量上架|批量发布|批量发品)[:：]?\s*", "", text).strip()
        if not raw:
            return {"ok": False, "text": "批量格式：每行「标题 | 价格 | 虚拟/实物 | 描述」，例如：\n小学奥数资料 | 9.9 | 虚拟 | 拍下自动发"}
        floor_pct = await self.settings.get_int("floor_discount_pct", 85)
        lines = [line.strip() for line in raw.splitlines() if line.strip() and line.strip() != "---"]
        prepared: list[dict[str, Any]] = []
        for line in lines:
            parts = [p.strip() for p in re.split(r"\s*[|｜]\s*", line)]
            if len(parts) < 2:
                continue
            title = parts[0]
            price = self._parse_price_token(parts[1])
            type_token = parts[2].lower() if len(parts) >= 3 else ""
            virtual = "虚" in type_token or any(h in line for h in VIRTUAL_HINTS)
            if "实物" in type_token:
                virtual = False
            desc = " | ".join(parts[3:]).strip() if len(parts) >= 4 else ""
            if not desc:
                desc = "，".join(parts[2:]).strip() if len(parts) >= 3 else ""
            if not price:
                price = 990 if virtual else 4900
            if not title:
                continue
            title = re.sub(r"\s+", " ", title).strip()[:30]
            policy = (
                "虚拟资料，拍下后自动发网盘链接，链接失效免费补发。"
                if virtual else "实物拍摄，包邮，48 小时内发出；二手物品非质量问题不退换。"
            )
            if policy not in desc:
                desc = f"{desc}\n{policy}" if desc else policy
            prepared.append({
                "title": title, "description": desc[:1000], "price_cents": price,
                "floor_price_cents": max(1, int(round(price * floor_pct / 100))),
                "delivery_mode": "virtual" if virtual else "physical",
                "condition": "电子资料" if virtual else self._extract_condition(line),
                "category": self._category(line, virtual),
            })
        if not prepared:
            return {"ok": False, "text": "没有解析到商品。每行请用 | 分隔：标题 | 价格 | 虚拟/实物 | 描述"}
        if len(prepared) == 1:
            # 只有一条时退回单条上架流程
            return await self._listing("上架：" + raw, toolbox)
        items_payload = []
        preview_items = []
        for data in prepared:
            item_id = await self._create_pending_item(
                title=data["title"], description=data["description"],
                price=data["price_cents"], floor=data["floor_price_cents"],
                virtual=data["delivery_mode"] == "virtual",
                condition=data["condition"], category=data["category"], floor_pct=floor_pct,
            )
            preview = {
                "kind": "publish_batch_item", "item_id": item_id, "title": data["title"],
                "price_cents": data["price_cents"], "price_text": f"¥{yuan(data['price_cents'])}",
                "floor_price_cents": data["floor_price_cents"],
                "delivery_mode": data["delivery_mode"], "condition": data["condition"],
                "category": data["category"], "description": data["description"],
            }
            preview_items.append(preview)
            items_payload.append({"item_id": item_id})
        preview = {"kind": "publish_batch", "items": preview_items, "count": len(preview_items)}
        cfm = await self.confirmations.create(
            "publish_batch", f"批量发布 {len(preview_items)} 件商品", preview,
            {"items": items_payload}, source="seller_agent",
        )
        card = {"type": "confirmation", "confirmation_id": cfm["id"], "preview": preview}
        await toolbox.call(
            "draft_batch_listing", {"count": len(preview_items)},
            lambda: {"count": len(preview_items)},
        )
        text_out = (
            f"批量预览好了：{len(preview_items)} 件商品。\n"
            + "\n".join(f"· {p['title']} {p['price_text']}（{'虚拟' if p['delivery_mode'] == 'virtual' else '实物'}）" for p in preview_items)
            + "\n确认后我会按顺序发布（仍走单写队列），确认前不动平台。"
        )
        return {"ok": True, "text": text_out, "card": card, "count": len(preview_items)}

    async def _llm_listing(self, title: str, desc: str, price: int, delivery: str) -> dict[str, str] | None:
        prompt = (
            "把下面的闲置商品信息润色成闲鱼文案。只输出 JSON："
            '{"title":"30字内标题","description":"80-220字描述"}。'
            "标题禁止感叹号堆砌，描述要真实、具体、亲切，不能出现微信/QQ/外链/网盘链接，不能编造参数。\n"
            f"原标题：{title}\n原描述：{desc}\n价格：{yuan(price)} 元\n类型：{'虚拟' if delivery == 'virtual' else '实物'}"
        )
        raw = await self.llm.chat(
            [{"role": "user", "content": prompt}], purpose="seller_listing", temperature=0.7,
            max_tokens=500, json_mode=True,
        )
        if not raw:
            return None
        try:
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            t = str(data.get("title") or "")[:30].strip()
            d = str(data.get("description") or "").strip()
            if not t or len(d) < 20 or re.search(r"微信|qq|http|https|转账", d, re.I):
                return None
            return {"title": t, "description": d[:800]}
        except Exception:
            return None
