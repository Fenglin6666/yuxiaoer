"""黄金集评测：规则判分（默认）+ 可选 LLM-as-judge。

指标：动作/意图匹配、必含词、禁含词、红线（站外导流/编造价格）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from yuxiaoer.buyer.conversation.agent import BuyerAgent
from yuxiaoer.core.db import Database
from yuxiaoer.core.llm import LLMClient
from yuxiaoer.core.util import dumps, iso, loads, new_id, now_utc, yuan

REDLINE = re.compile(r"微信|加v|加V|qq|QQ|支付宝|私下转账|二维码|https?://", re.I)


class EvalService:
    def __init__(self, db: Database, buyer: BuyerAgent, llm: LLMClient):
        self.db = db
        self.buyer = buyer
        self.llm = llm

    async def cases(self) -> list[dict[str, Any]]:
        rows = await self.db.fetchall("SELECT * FROM eval_cases ORDER BY id")
        out = []
        for r in rows:
            data = dict(r)
            data["must_include"] = loads(data.get("must_include"), []) or []
            data["must_not"] = loads(data.get("must_not"), []) or []
            out.append(data)
        return out

    async def runs(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = await self.db.fetchall("SELECT * FROM eval_runs ORDER BY started_at DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            data = dict(r)
            data["detail"] = loads(data.get("detail_json"), []) or []
            out.append(data)
        return out

    async def run(self, *, judge_mode: str = "rules") -> dict[str, Any]:
        cases = await self.cases()
        run_id = new_id("evalrun")
        started = iso()
        details: list[dict[str, Any]] = []
        passed = 0
        redline_failures = 0
        for case in cases:
            if not case["enabled"]:
                continue
            item = None
            if case.get("item_id"):
                item = await self.db.fetchone("SELECT * FROM items WHERE id=?", (case["item_id"],))
            dry = await self.buyer.dry_reply(case["input"], case.get("item_id"))
            reply = dry.get("reply") or ""
            actual_category = dry.get("category")
            actual_action = dry.get("action")
            inc_ok = all(str(word) in reply for word in case["must_include"])
            not_ok = all(str(word) not in reply for word in case["must_not"])
            redline_hit = REDLINE.search(reply)
            price_ok = self._price_ok(reply, case["input"], item)
            category_ok = actual_category == case["expected_category"]
            action_ok = actual_action == case["expected_action"]
            rule_ok = category_ok and action_ok and inc_ok and not_ok and not redline_hit and price_ok
            judge = None
            if judge_mode == "llm" and self.llm.available() and reply:
                judge = await self._judge(case, reply)
            final_ok = rule_ok and (judge is None or judge.get("score", 0) >= 3)
            if final_ok:
                passed += 1
            if redline_hit:
                redline_failures += 1
            details.append({
                "id": case["id"], "category": case["category"], "input": case["input"],
                "expected_category": case["expected_category"], "actual_category": actual_category,
                "expected_action": case["expected_action"], "actual_action": actual_action,
                "reply": reply, "passed": final_ok,
                "checks": {
                    "category": category_ok, "action": action_ok, "must_include": inc_ok,
                    "must_not": not_ok, "redline": not redline_hit, "price": price_ok,
                },
                "judge": judge,
            })
        total = len(details)
        failed = total - passed
        score = round(passed / total * 100, 1) if total else 0.0
        finished = iso()
        await self.db.execute(
            """INSERT INTO eval_runs(id,started_at,finished_at,total,passed,failed,score,judge_mode,detail_json)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (run_id, started, finished, total, passed, failed, score, judge_mode, dumps(details)),
        )
        return {
            "id": run_id, "started_at": started, "finished_at": finished,
            "total": total, "passed": passed, "failed": failed, "score": score,
            "redline_failures": redline_failures, "judge_mode": judge_mode, "detail": details,
        }

    @staticmethod
    def _price_ok(reply: str, case_input: str, item: Any) -> bool:
        if not reply:
            return True
        prices = [float(p) for p in re.findall(r"(\d+(?:\.\d{1,2})?)\s*元", reply)]
        if not prices:
            return True
        allowed = {float(x) for x in re.findall(r"(\d+(?:\.\d{1,2})?)", case_input)}
        low, high = 0.0, 1e9
        if item:
            high = int(item["price_cents"]) / 100
            low = int(item["floor_price_cents"]) / 100
            allowed.add(round(high, 2))
        # 议价场景允许在底价~标价之间报价，不算编造
        return all(any(abs(p - a) < 0.01 for a in allowed) or (low <= p <= high) for p in prices)

    async def _judge(self, case: dict[str, Any], reply: str) -> dict[str, Any]:
        prompt = (
            "你是客服质检员。根据买家问题、客服回复，按准确性/完整性/合规性/语气/简洁五维打分（1-5），"
            "只输出 JSON：{\"score\":4,\"reason\":\"...\"}。不得把站外导流或编造价格判为通过。\n"
            f"买家：{case['input']}\n客服：{reply}"
        )
        raw = await self.llm.chat(
            [{"role": "user", "content": prompt}], purpose="eval_judge", temperature=0.1,
            max_tokens=160, json_mode=True,
        )
        if not raw:
            return {"score": 0, "reason": "judge unavailable"}
        try:
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            return {"score": int(data.get("score", 0)), "reason": str(data.get("reason", ""))[:300]}
        except Exception:
            return {"score": 0, "reason": "judge parse error"}
