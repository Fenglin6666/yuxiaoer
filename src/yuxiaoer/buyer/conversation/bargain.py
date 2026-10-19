"""议价引擎：价格计算是确定性的，LLM 只负责措辞。

规则：
- 买家出价 >= 商品价：按商品价成交；
- 卖家底价 <= 出价 < 商品价：接受（底价是硬约束）；
- 出价 < 底价：拒绝并报底价；
- 没出价：第一轮让到 95%，第二轮让到底价；
- "买两件"：给 95 折（不低于底价）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from yuxiaoer.core.util import yuan

_NUM = r"(\d+(?:\.\d{1,2})?)"


@dataclass
class BargainDecision:
    kind: str  # accept | counter | decline | bundle
    target_cents: int
    offer_cents: int | None
    message: str
    floor_cents: int


def parse_offer(text: str, price_cents: int) -> int | None:
    """从买家话里解析出价（分）。支持 '8块'、'7.5'、'便宜10块'、'¥80'。"""
    t = (text or "").replace("￥", "¥").replace("，", "")
    m = re.search(r"便宜\s*" + _NUM + r"\s*(?:元|块|块钱)?", t)
    if m:
        off = int(round(float(m.group(1)) * 100))
        return max(0, price_cents - off)
    m = re.search(r"(?:少|降)\s*" + _NUM + r"\s*(?:元|块|块钱)?", t)
    if m:
        off = int(round(float(m.group(1)) * 100))
        return max(0, price_cents - off)
    m = re.search(_NUM + r"\s*(?:元|块|块钱|¥)", t)
    if m:
        return int(round(float(m.group(1)) * 100))
    m = re.search(r"¥\s*" + _NUM, t)
    if m:
        return int(round(float(m.group(1)) * 100))
    # 纯数字短句（如 "7.5 行不行"）
    m = re.search(_NUM, t)
    if m:
        return int(round(float(m.group(1)) * 100))
    return None


def decide(item: dict, text: str, round_no: int = 0, max_rounds: int = 3) -> BargainDecision:
    price = int(item["price_cents"])
    floor = int(item["floor_price_cents"])
    offer = parse_offer(text, price)
    delivery = item.get("delivery_mode") or "physical"
    is_bundle = bool(re.search(r"(两件|两个|2件|2个|一起买|打包)", text or ""))
    max_rounds = max(1, int(max_rounds or 3))

    if is_bundle:
        target = max(floor, int(round(price * 0.95)))
        if offer is not None and offer >= target:
            target = offer
        return BargainDecision(
            "bundle", target, offer,
            f"两件一起可以再优惠一点，给你算 {yuan(target)} 元一件，拍下备注一下就行～",
            floor,
        )

    if offer is not None:
        if offer >= price:
            return BargainDecision(
                "accept", price, offer,
                f"就按 {yuan(price)} 元，直接拍下就行，我这边马上安排～", floor,
            )
        if offer >= floor:
            return BargainDecision(
                "accept", offer, offer,
                f"{yuan(offer)} 元可以～ 这个价给你留着，今天拍下就行。", floor,
            )
        if round_no >= max_rounds - 1:
            return BargainDecision(
                "decline", floor, offer,
                f"真的到底啦，最低就是 {yuan(floor)} 元，再低出不了，你考虑一下～", floor,
            )
        return BargainDecision(
            "decline", floor, offer,
            f"最低 {yuan(floor)} 元哦，再低就真的出不了啦，东西你放心～", floor,
        )

    # 没出价：按轮数阶梯让步，到上限后守住底价
    if round_no <= 0:
        target = max(floor, int(round(price * 0.95)))
        if delivery == "physical":
            msg = f"可以小刀～ 已经包邮啦，价格上最低给你 {yuan(target)} 元，拍下就发。"
        else:
            msg = f"可以小刀～ 虚拟资料不涉及包邮和邮费，价格上最低给你 {yuan(target)} 元，拍下自动发。"
        return BargainDecision("counter", target, None, msg, floor)
    if round_no < max_rounds - 1:
        target = max(floor, int(round(price * 0.92)))
        return BargainDecision(
            "counter", target, None,
            f"再让一点，给你 {yuan(target)} 元，这个价格真的很实在啦～", floor,
        )
    target = floor
    return BargainDecision(
        "counter", target, None,
        f"最低 {yuan(floor)} 元啦，已经聊到底价，不能再让了～", floor,
    )
