"""
FastAPI Router for Intent Classification & Streaming (/api/v1/agent/intent, /classify, /classify/stream).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.models.user import User
from backend.routers.agent_schemas import (
    ClassifyIntentRequest,
    ClassifyIntentResponse,
    QuickIntentResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Engineering Agent Intent"])


@router.post("/intent", response_model=QuickIntentResponse)
def quick_intent_endpoint(
    req: ClassifyIntentRequest,
    current_user: User = Depends(get_current_user),
) -> QuickIntentResponse:
    """
    Lightweight, instant (<10ms) intent classification endpoint without executing deep mode engines.
    """
    from backend.agent.intent import IntentRouter
    router_inst = IntentRouter()
    result = router_inst.classify(req.requirement)
    return QuickIntentResponse(
        intent=result.intent.value,
        confidence=result.confidence,
        reason=result.reason,
        method=result.classification_method,
    )


@router.post("/classify", response_model=ClassifyIntentResponse)
def classify_intent_endpoint(
    req: ClassifyIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClassifyIntentResponse:
    """
    Direct endpoint for fast, synchronous intent classification and response synthesis.
    """
    from backend.agent.intent import IntentRouter, Intent
    from backend.agent.modes import execute_chat, execute_explore, execute_explain, execute_plan, execute_implement

    router_inst = IntentRouter()
    result = router_inst.classify(req.requirement)

    entities_list = []
    plan_dict = None
    evidence_list = []
    rim_trace = None
    mode_res = {}
    if result.intent == Intent.CHAT:
        mode_res = execute_chat(req.requirement)
        response_text = mode_res.get("response", "Hello! How can I help you today?")
        evidence_list = mode_res.get("evidence", [])
    elif result.intent == Intent.EXPLORE:
        mode_res = execute_explore(req.requirement, repository_id=req.repository_id, user_id=current_user.id, db=db)
        response_text = mode_res.get("response", "Exploration complete.")
        entities_list = mode_res.get("entities", [])
        evidence_list = mode_res.get("evidence", [])
    elif result.intent == Intent.EXPLAIN:
        mode_res = execute_explain(req.requirement, repository_id=req.repository_id, user_id=current_user.id, db=db)
        response_text = mode_res.get("response", "Explanation complete.")
        evidence_list = mode_res.get("evidence", [])
        rim_trace = mode_res.get("rim_trace")
    elif result.intent == Intent.PLAN:
        mode_res = execute_plan(req.requirement, repository_id=req.repository_id, user_id=current_user.id, db=db)
        response_text = mode_res.get("response", "Plan generation complete.")
        plan_dict = mode_res.get("plan")
        evidence_list = mode_res.get("evidence", [])
    elif result.intent == Intent.IMPLEMENT:
        mode_res = execute_implement(req.requirement, repository_id=req.repository_id, user_id=current_user.id, db=db)
        response_text = mode_res.get("response", "Implementation plan synthesized. Ready for human approval.")
        plan_dict = mode_res.get("plan")
        evidence_list = mode_res.get("evidence", [])
    else:  # CLARIFY
        response_text = f"Your request '{req.requirement}' is ambiguous or underspecified. Please specify which files, functions, or features you want to modify or inspect."

    return ClassifyIntentResponse(
        intent=result.intent.value,
        confidence=result.confidence,
        reason=result.reason,
        method=result.classification_method,
        response=response_text,
        entities=entities_list,
        plan=plan_dict,
        evidence=evidence_list,
        rim_trace=rim_trace,
    )


@router.post("/classify/stream")
async def stream_classify_intent_endpoint(
    req: ClassifyIntentRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Streaming SSE endpoint for real-time repository activity and response generation.
    Emits live activity items (file reads, symbol inspections, search queries) as they happen.
    """
    from backend.agent.intent import IntentRouter, Intent
    from backend.agent.modes import execute_chat, execute_explore, execute_explain, execute_plan, execute_implement

    async def event_generator():
        event_queue = asyncio.Queue()

        def sync_on_event(evt: Dict[str, Any]):
            event_queue.put_nowait(evt)

        async def run_execution():
            loop = asyncio.get_running_loop()
            try:
                router_inst = IntentRouter()
                result = router_inst.classify(req.requirement)

                entities_list = []
                plan_dict = None
                evidence_list = []
                rim_trace = None

                if result.intent == Intent.CHAT:
                    mode_res = await loop.run_in_executor(None, lambda: execute_chat(req.requirement))
                    response_text = mode_res.get("response", "Hello! How can I help you today?")
                    evidence_list = mode_res.get("evidence", [])
                elif result.intent == Intent.EXPLORE:
                    mode_res = await loop.run_in_executor(
                        None,
                        lambda: execute_explore(req.requirement, repository_id=req.repository_id, user_id=current_user.id, db=None, on_event=sync_on_event)
                    )
                    response_text = mode_res.get("response", "Exploration complete.")
                    entities_list = mode_res.get("entities", [])
                    evidence_list = mode_res.get("evidence", [])
                elif result.intent == Intent.EXPLAIN:
                    mode_res = await loop.run_in_executor(
                        None,
                        lambda: execute_explain(req.requirement, repository_id=req.repository_id, user_id=current_user.id, db=None, on_event=sync_on_event)
                    )
                    response_text = mode_res.get("response", "Explanation complete.")
                    evidence_list = mode_res.get("evidence", [])
                    rim_trace = mode_res.get("rim_trace")
                elif result.intent == Intent.PLAN:
                    mode_res = await loop.run_in_executor(
                        None,
                        lambda: execute_plan(req.requirement, repository_id=req.repository_id, user_id=current_user.id, db=None, on_event=sync_on_event)
                    )
                    response_text = mode_res.get("response", "Plan generation complete.")
                    plan_dict = mode_res.get("plan")
                    evidence_list = mode_res.get("evidence", [])
                elif result.intent == Intent.IMPLEMENT:
                    mode_res = await loop.run_in_executor(
                        None,
                        lambda: execute_implement(req.requirement, repository_id=req.repository_id, user_id=current_user.id, db=None, on_event=sync_on_event)
                    )
                    response_text = mode_res.get("response", "Implementation plan synthesized. Ready for human approval.")
                    plan_dict = mode_res.get("plan")
                    evidence_list = mode_res.get("evidence", [])
                else:
                    response_text = f"Your request '{req.requirement}' is ambiguous or underspecified. Please specify which files, functions, or features you want to modify or inspect."

                # Put final result
                sync_on_event({
                    "type": "result",
                    "data": {
                        "intent": result.intent.value,
                        "confidence": result.confidence,
                        "reason": result.reason,
                        "method": result.classification_method,
                        "response": response_text,
                        "entities": entities_list,
                        "plan": plan_dict,
                        "evidence": evidence_list,
                        "rim_trace": rim_trace,
                    }
                })
            except Exception as err:
                logger.error(f"Error during stream classification: {err}", exc_info=True)
                sync_on_event({
                    "type": "error",
                    "data": {
                        "message": str(err),
                    }
                })
            finally:
                sync_on_event({"type": "done"})

        task = asyncio.create_task(run_execution())

        try:
            while True:
                if await request.is_disconnected():
                    task.cancel()
                    break
                try:
                    evt = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    if evt.get("type") == "done":
                        break
                    yield {
                        "event": evt.get("type", "message"),
                        "data": json.dumps(evt.get("item") or evt.get("data") or evt),
                    }
                except asyncio.TimeoutError:
                    if task.done():
                        while not event_queue.empty():
                            evt = event_queue.get_nowait()
                            if evt.get("type") == "done":
                                break
                            yield {
                                "event": evt.get("type", "message"),
                                "data": json.dumps(evt.get("item") or evt.get("data") or evt),
                            }
                        break
                    yield {"comment": "keepalive"}
        finally:
            if not task.done():
                task.cancel()

    return EventSourceResponse(event_generator())
