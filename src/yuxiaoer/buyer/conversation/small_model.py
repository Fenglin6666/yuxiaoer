"""轻量意图模型：字符 n-gram 最近质心分类器。

不是生成模型，也不下载权重；用少量标注短语构建每个意图的质心，做余弦相似度。
它只在规则返回 unknown 时兜底，低置信度直接放弃，交给 LLM/谨慎模式。
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .normalize import match_text

LABELS = ("pre_sale", "bargain", "after_sale", "order", "chitchat", "human", "risk", "off_platform")

EXEMPLARS: dict[str, list[str]] = {
    "pre_sale": [
        "这个还有吗", "多少钱", "什么价格", "怎么卖", "有货吗", "库存还有没有",
        "什么成色", "几成新", "包邮吗", "发什么快递", "什么时候发货", "能便宜吗",
        "这个怎么样", "适合我吗", "有什么颜色", "尺码怎么选", "还有别的款吗",
        "这个和那个有什么区别", "能看看细节图吗", "是正品吗", "质量怎么样",
    ],
    "bargain": [
        "便宜点", "少点", "能少一点吗", "打个折", "刀一下", "最低多少",
        "再便宜点", "能包邮吗", "包个邮", "这个价行不行", "贵了", "预算不够",
        "八块卖不卖", "五十可以吗", "再让一点", "给我个优惠",
    ],
    "after_sale": [
        "我要退款", "怎么退款", "退货", "不想要了", "发错货了", "少发了",
        "坏了", "破损", "有瑕疵", "链接失效", "打不开", "没收到", "物流到哪了",
        "快递单号", "改地址", "确认收货", "怎么售后", "换货",
    ],
    "order": [
        "我的订单", "订单号", "查订单", "付款了吗", "买过了", "下单了",
        "订单状态", "什么时候到", "发货了吗", "订单在哪看",
    ],
    "chitchat": [
        "在吗", "在么", "你好", "您好", "hello", "hi", "谢谢", "感谢",
        "哈哈", "好的", "嗯嗯", "你是谁", "老板在吗", "有人吗", "在不在",
        "说话", "呵呵", "收到", "ok",
    ],
    "human": [
        "转人工", "找人工", "要人工", "人工客服", "找店主", "真人",
        "客服在吗", "让老板来", "我要投诉", "叫你们老板",
    ],
    "risk": [
        "骗子", "诈骗", "举报你", "投诉你", "起诉", "报警", "封号",
        "黑店", "骗钱", "垃圾店", "威胁你",
    ],
    "off_platform": [
        "加微信", "加v", "vx", "加qq", "支付宝转账", "私下交易",
        "扫码", "手机号多少", "加个好友", "站外聊",
    ],
}

ACTION = {
    "pre_sale": "agent",
    "bargain": "agent",
    "after_sale": "agent",
    "order": "agent",
    "chitchat": "template",
    "human": "agent",
    "risk": "silent",
    "off_platform": "silent",
}


@dataclass
class Prediction:
    label: str
    confidence: float
    margin: float


def _features(text: str) -> Counter[str]:
    value = match_text(text)
    features: Counter[str] = Counter()
    for char in value:
        features[char] += 1
    for i in range(len(value) - 1):
        features[value[i:i + 2]] += 1
    return features


def _centroid(examples: list[str]) -> list[Counter[str]]:
    return [_features(example) for example in examples]


_EXEMPLAR_FEATURES = {label: _centroid(examples) for label, examples in EXEMPLARS.items()}


def _cosine(features: Counter[str], example: Counter[str]) -> float:
    norm = math.sqrt(sum(v * v for v in features.values())) or 1.0
    example_norm = math.sqrt(sum(v * v for v in example.values())) or 1.0
    dot = sum(v * example.get(k, 0) for k, v in features.items())
    return dot / (norm * example_norm)


class SmallIntentModel:
    def predict(self, text: str, *, min_confidence: float = 0.5, min_margin: float = 0.05) -> Prediction | None:
        features = _features(text)
        if not features:
            return None
        scores = {
            label: max(_cosine(features, example) for example in examples)
            for label, examples in _EXEMPLAR_FEATURES.items()
        }
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_label, top_score = ordered[0]
        second_score = ordered[1][1] if len(ordered) > 1 else 0.0
        margin = top_score - second_score
        if top_score < min_confidence or margin < min_margin:
            return None
        return Prediction(top_label, round(top_score, 4), round(margin, 4))


small_model = SmallIntentModel()
