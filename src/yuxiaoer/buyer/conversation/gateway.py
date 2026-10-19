"""入口网关：规则黑名单 → 轻量意图分类 → 直通/模板/静默/谨慎。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

RISK_PATTERNS = [
    "骗子", "诈骗", "敲诈", "举报你", "举报", "投诉你", "投诉到", "关店", "封号", "报警", "起诉", "威胁",
    "弄死", "打死", "傻逼", "傻B", "操你", "草你", "滚蛋", "盗版", "盗图",
    "骗钱", "退钱", "黑店",
]

OFF_PLATFORM_PATTERNS = [
    "微信", "加v", "加V", "vx", "VX", "v信", "薇信", "qq", "QQ", "扣扣",
    "支付宝", "私下", "转账", "二维码", "扫码", "手机号", "电话号",
]

AFTER_SALE_PATTERNS = [
    "退款", "退货", "退换", "坏了", "破损", "瑕疵", "没收到", "未收到", "少发",
    "漏发", "少了一", "发错", "不对版", "物流", "快递", "签收", "换货", "售后",
    "确认收货", "改地址", "还没发", "催一下", "多久到", "到哪了", "失效", "打不开",
]

BARGAIN_PATTERNS = [
    "便宜", "少点", "少一点", "刀", "最低", "优惠", "能少", "降价", "砍价",
    "包个邮", "包邮就", "别家", "行不行", "卖不卖", "多少钱卖", "让点",
    "块钱", "块卖", "元卖", "打个折",
]

ORDER_PATTERNS = ["订单", "付款", "买了", "购买", "下单"]
HUMAN_PATTERNS = ["转人工", "找人工", "要人工", "人工客服", "人工", "找店主", "店主在吗", "真人", "客服在吗"]

CHITCHAT_PATTERNS = [
    "在吗", "在么", "在不在", "有人吗", "你好", "您好", "hi", "hello", "哈喽",
    "谢谢", "谢啦", "感谢", "哈哈", "好的", "好哒", "嗯嗯", "你是谁", "老板在",
]

PRODUCT_HINTS = [
    "这个", "这件", "商品", "资料", "货", "还有", "成色", "发", "链接", "pdf",
    "答案", "年级", "打印", "验货", "正品", "发票", "包邮", "邮费", "几新",
    "适合", "库存", "现货", "价格", "多少钱", "全新", "什么时候", "能到", "多久",
]

_PUNCT = re.compile(r"[\s，。！？!?,.、~～…:：;；\"'“”‘’（）()\[\]【】]+")


@dataclass
class Decision:
    category: str
    action: str  # silent | template | agent
    confidence: float
    reason: str
    risk_level: str | None = None
    cautious: bool = False
    template: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _contains_any(text: str, patterns: list[str]) -> str | None:
    low = text.lower()
    for p in patterns:
        if p.lower() in low:
            return p
    return None


def _is_pure_chitchat(text: str) -> bool:
    core = text
    for p in sorted(CHITCHAT_PATTERNS, key=len, reverse=True):
        core = re.sub(re.escape(p), "", core, flags=re.IGNORECASE)
    core = _PUNCT.sub("", core)
    return len(core) <= 2


def classify(text: str, *, item_title: str | None = None) -> Decision:
    """纯规则、可解释、无 LLM 依赖。LLM 只作为 unknown 时的可选兜底。"""
    raw = (text or "").strip()
    if not raw:
        return Decision("unknown", "silent", 1.0, "空消息", cautious=True)

    hit = _contains_any(raw, RISK_PATTERNS)
    if hit:
        return Decision(
            "risk", "silent", 0.98, f"风险词命中：{hit}", risk_level="P1", cautious=False
        )

    hit = _contains_any(raw, OFF_PLATFORM_PATTERNS)
    if hit:
        return Decision(
            "off_platform", "silent", 0.95, f"站外沟通特征：{hit}", risk_level="P1"
        )

    hit = _contains_any(raw, HUMAN_PATTERNS)
    if hit:
        return Decision("human", "agent", 0.95, f"买家要求人工：{hit}")

    hit = _contains_any(raw, AFTER_SALE_PATTERNS)
    if hit:
        return Decision("after_sale", "agent", 0.9, f"售后/履约特征：{hit}")

    hit = _contains_any(raw, BARGAIN_PATTERNS)
    if hit:
        return Decision("bargain", "agent", 0.9, f"议价特征：{hit}")

    hit = _contains_any(raw, ORDER_PATTERNS)
    if hit:
        return Decision("order", "agent", 0.86, f"订单特征：{hit}")

    if any(k in raw for k in ("你会干什么", "能做什么", "可以做什么", "你会什么", "你能干嘛", "有什么功能")):
        return Decision(
            "chitchat", "template", 0.92, "询问客服能力",
            template="我可以帮你看商品信息、库存、发货和售后～ 有具体商品或订单直接发我。",
        )

    if _is_pure_chitchat(raw):
        return Decision(
            "chitchat", "template", 0.92, "纯寒暄",
            template="我是鱼小二客服，在的～ 有喜欢哪件可以直接问我 😊",
        )

    hit = _contains_any(raw, PRODUCT_HINTS)
    if hit:
        return Decision("pre_sale", "agent", 0.82, f"商品咨询特征：{hit}")

    if item_title and any(part and part in raw for part in re.split(r"[\s（）()]+", item_title) if len(part) >= 2):
        return Decision("pre_sale", "agent", 0.75, "包含商品名关键词")

    if "?" in raw or "？" in raw or "吗" in raw or "怎么" in raw:
        return Decision("unknown", "agent", 0.55, "问句但未命中规则，进谨慎模式", cautious=True)

    return Decision("unknown", "agent", 0.4, "未识别，进谨慎模式", cautious=True)
