"""值守任务、告警、事件、工具调用、回放与评测。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..core.util import human_time, loads
from ..runtime import runtime
from ._models import EvalRunIn, JobUpdateIn

router = APIRouter()

@router.get("/patrol/jobs")
async def patrol_jobs() -> list[dict[str, Any]]:
    return await runtime.patrol.jobs()


@router.patch("/patrol/jobs/{name}")
async def patrol_update(name: str, payload: JobUpdateIn) -> dict[str, Any]:
    try:
        job = await runtime.patrol.update_job(
            name, enabled=payload.enabled, local_time=payload.local_time,
            interval_seconds=payload.interval_seconds,
        )
    except KeyError:
        raise HTTPException(404, "任务不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"ok": True, "job": job}


# ---------------- 值守执行 / 告警 ----------------

@router.post("/patrol/jobs/{name}/run")
async def patrol_run(name: str) -> dict[str, Any]:
    result = await runtime.patrol.run_job(name, manual=True)
    runtime._health_cache = None
    return result


@router.get("/alerts")
async def alerts(status: str = Query("open"), limit: int = 50) -> list[dict[str, Any]]:
    return await runtime.alerts.list(status, limit)


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str) -> dict[str, Any]:
    ok = await runtime.alerts.ack(alert_id)
    if not ok:
        raise HTTPException(404, "告警不存在或已处理")
    return {"ok": True}


# ---------------- 观测 / 回放 ----------------

@router.get("/events")
async def events(limit: int = 100, topic: str | None = None) -> list[dict[str, Any]]:
    if topic:
        rows = await runtime.db.fetchall(
            "SELECT * FROM events WHERE topic=? ORDER BY id DESC LIMIT ?", (topic, limit)
        )
    else:
        rows = await runtime.db.fetchall("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
    return [
        dict(r) | {"payload": loads(r["payload_json"], {}), "created_human": human_time(r["created_at"])}
        for r in rows
    ]


@router.get("/tools")
async def tool_calls(limit: int = 100) -> list[dict[str, Any]]:
    rows = await runtime.db.fetchall(
        "SELECT * FROM tool_calls ORDER BY id DESC LIMIT ?", (limit,)
    )
    return [
        dict(r) | {"args": loads(r["args_json"], {}), "result": loads(r["result_json"], {}),
                   "created_human": human_time(r["created_at"])}
        for r in rows
    ]


@router.get("/replay/sessions")
async def replay_sessions(limit: int = 30) -> list[dict[str, Any]]:
    return await runtime.replay.sessions(limit)


@router.get("/replay/{conversation_id}")
async def replay_trace(conversation_id: str) -> dict[str, Any]:
    trace = await runtime.replay.trace(conversation_id)
    if not trace:
        raise HTTPException(404, "会话不存在")
    return trace


# ---------------- 评测 ----------------

@router.get("/eval/cases")
async def eval_cases() -> list[dict[str, Any]]:
    return await runtime.eval.cases()


@router.get("/eval/runs")
async def eval_runs(limit: int = 10) -> list[dict[str, Any]]:
    return await runtime.eval.runs(limit)


@router.post("/eval/run")
async def eval_run(payload: EvalRunIn) -> dict[str, Any]:
    mode = "llm" if payload.judge_mode == "llm" and runtime.llm.available() else "rules"
    return await runtime.eval.run(judge_mode=mode)
