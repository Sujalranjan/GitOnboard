"""LLM settings and model management endpoints."""
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.ai.schemas import LLMRequest, Message, MessageRole
from backend.ai.service import get_llm_service
from backend.config import settings
from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.models.fact_store import FactFile, FactSymbol
from backend.models.repository import Analysis, Repository
from backend.models.user import User
from backend.repository_tools.tools import resolve_repo_root
from backend.services.qa_loop import QALoopTurn
from backend.services.llm_analysis_service import build_analysis_service
from backend.logging import StructuredLogger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["llm"])


# ===== Error Message Formatting =====

def format_error_message(error: Exception) -> str:
    """
    Format error messages to clearly tell developers what failed.
    Detects resource exhaustion, timeouts, and connection issues.
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Memory/OOM errors
    if any(x in error_str for x in ["oom", "out of memory", "memory", "cuda out of memory", "no space"]):
        return (
            "❌ LOCAL MODEL MEMORY LIMIT EXCEEDED\n\n"
            "The local model server (Ollama) ran out of memory while processing your request.\n\n"
            "**What failed:** Model inference requires more GPU/CPU memory than available.\n"
            "**Default model:** Qwen 3 4B Instruct (recommended for 8GB+ RAM)\n\n"
            "**Solutions:**\n"
            "1. Reduce repository size or query complexity\n"
            "2. Restart Ollama: `ollama serve`\n"
            "3. Pull Qwen 3 4B: `ollama pull qwen:3-4b-instruct`\n"
            "4. Check available GPU/CPU memory: `nvidia-smi` or `free -h`\n"
        )

    # Connection/timeout errors
    if any(x in error_str for x in ["disconnected", "connection refused", "timeout", "connection"]):
        return (
            "❌ LOCAL MODEL SERVER CONNECTION FAILED\n\n"
            "Cannot connect to Ollama server. The model service may have crashed or is not running.\n\n"
            "**What failed:** Network connection to local model inference server.\n"
            "**Default model:** Qwen 3 4B Instruct (should run on `localhost:11434`)\n\n"
            "**Solutions:**\n"
            "1. Start Ollama server: `ollama serve`\n"
            "2. Verify Ollama is running: `curl http://localhost:11434/api/tags`\n"
            "3. Check logs: `ollama logs` or system logs\n"
            "4. Restart Docker/system if needed\n"
        )

    # JSON parsing errors
    if "json" in error_str or "jsondecodeerror" in error_type.lower():
        return (
            "❌ INVALID MODEL RESPONSE\n\n"
            "The model returned malformed data that could not be parsed.\n\n"
            "**What failed:** JSON parsing of model output (model sent invalid JSON).\n"
            "**Default model:** Qwen 3 4B Instruct (instruction-tuned for structured output)\n\n"
            "**Solutions:**\n"
            "1. Ensure Qwen 3 4B Instruct is running (not Code variant)\n"
            "2. Restart the model: `ollama pull qwen:3-4b-instruct && ollama serve`\n"
            "3. Check model prompt compatibility with system prompt\n"
        )

    # Generic fallback
    return (
        f"❌ ANALYSIS FAILED: {error_type}\n\n"
        f"**Error details:** {str(error)}\n\n"
        "**Default model:** Qwen 3 4B Instruct\n\n"
        "**Contact:** Check application logs for full stack trace.\n"
    )


# ===== Repository Context Building =====

async def build_repository_context(db: Session, repo: Repository, analysis_id: Optional[int] = None) -> str:
    """Extract repository metadata and build rich context for LLM."""
    try:
        from backend.models.repository import Analysis
        from backend.models.fact_store import FactSymbol, FactFile

        context_parts = []

        # 1. Repository basic info
        from backend.routers.repo.services.analysis import get_repo_display_name
        friendly_name = get_repo_display_name(repo)
        context_parts.append(f"Repository: {friendly_name}")
        if repo.url:
            context_parts.append(f"URL: {repo.url}")
        if repo.default_branch:
            context_parts.append(f"Default Branch: {repo.default_branch}")
        context_parts.append("")

        # 2. Analysis metadata
        if analysis_id:
            analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
            if analysis:
                context_parts.append(f"Analysis Status: {analysis.status}")
                context_parts.append(f"Last Indexed: {analysis.indexed_at}")
                context_parts.append("")

        # 3. File statistics
        file_count = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).count()
        context_parts.append(f"Total Files: {file_count}")

        # 4. Top-level symbols and structure
        context_parts.append("\nKey Components:")
        top_symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.symbol_type.in_(["class", "interface", "function", "enum"])
        ).limit(15).all()

        for sym in top_symbols:
            context_parts.append(f"- {sym.name} ({sym.symbol_type})")

        # 5. Sample files/directories
        context_parts.append("\nSample Files:")
        sample_files = db.query(FactFile).filter(
            FactFile.analysis_id == analysis_id
        ).limit(10).all()

        for file in sample_files:
            context_parts.append(f"- {file.path}")

        return "\n".join(context_parts)

    except Exception as e:
        logger.error(f"Error building repository context: {e}")
        return f"Repository: {repo.repository_hash if repo else 'unknown'}"


# ===== Model Configuration =====

def get_valid_models() -> Dict[str, str]:
    """
    Return available models based on deployment mode and configured API keys.

    Cloud models (Gemini, Groq, OpenRouter) are optional. If their API keys
    are not set or empty, they are omitted from the available models list
    so users won't see them as options and the system won't crash trying to use them.

    LOCAL mode: Local Qwen & Nemotron models + any available Cloud models.
    PROD mode: Cloud providers with active API keys ONLY (falls back to local models if no cloud keys are configured).
    """
    cloud_models: Dict[str, str] = {}

    gemini_key = os.environ.get("GEMINI_API_KEY", "") or getattr(settings, "gemini_api_key", "")
    if gemini_key and gemini_key.strip():
        cloud_models[settings.gemini_model] = f"Gemini ({settings.gemini_model})"

    groq_key = os.environ.get("GROQ_API_KEY", "") or getattr(settings, "groq_api_key", "")
    if groq_key and groq_key.strip():
        cloud_models[settings.groq_model] = f"Groq ({settings.groq_model})"

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "") or getattr(settings, "openrouter_api_key", "")
    if openrouter_key and openrouter_key.strip():
        cloud_models[settings.openrouter_model] = f"OpenRouter ({settings.openrouter_model})"

    local_models = {
        settings.model_local_fast: f"Qwen 3.5 2B (Local - Default)",
        settings.model_local_quality: f"Qwen 2.5 Coder 3B (Local - Quality)",
        settings.model_local_nemotron: "Nemotron Mini (Local - Ollama)",
    }

    # Combine all local and configured cloud models so users can pick any model for planner and worker
    models = dict(local_models)
    models.update(cloud_models)
    return models


class SetModelRequest(BaseModel):
    model: str


class ModelResponse(BaseModel):
    current_model: str
    model_name: str
    status: str


class ModelsListResponse(BaseModel):
    """Response with list of available models."""
    deployment_type: str
    models: Dict[str, str]  # model_id -> display_name


class AnalyzeRequest(BaseModel):
    query: str
    repo_hash: str
    model: str = None  # Planner model (or single-agent model)
    worker_model: Optional[str] = None  # Explicit worker model (e.g. qwen2.5-coder:3b, gemini-3.8-flash, etc.)
    show_tool_details: bool = True
    investigation_mode: Optional[str] = "single_agent"  # "single_agent" or "multi_agent"
    worker_type: Optional[str] = None  # "local" | "cloud" (if worker_model is not given)


@router.get("/models", response_model=ModelsListResponse)
def get_models():
    """
    Get list of available models for the current deployment mode.

    LOCAL mode returns Qwen/Ollama models.
    PROD mode returns cloud models (Gemini, OpenRouter).
    """
    return ModelsListResponse(
        deployment_type=settings.deployment_type,
        models=get_valid_models(),
    )


@router.post("/set-model", response_model=ModelResponse)
def set_model(
    request: SetModelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change the active LLM model for this session.

    Available models depend on deployment mode:
    - LOCAL: Qwen/Ollama models (fast, local inference)
    - PROD: Cloud models (Gemini, OpenRouter)
    """
    # Refresh valid models for current deployment
    valid_models = get_valid_models()

    if request.model not in valid_models:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model for {settings.deployment_type} mode. Valid options: {list(valid_models.keys())}",
        )

    # Set model in environment (affects new requests)
    os.environ["OLLAMA_MODEL"] = request.model

    # For cloud models, check that API keys are configured
    if request.model == settings.gemini_model and not os.environ.get("GEMINI_API_KEY"):
        logger.warning(f"Gemini model '{request.model}' selected but GEMINI_API_KEY not configured")
    if request.model == settings.groq_model and not os.environ.get("GROQ_API_KEY"):
        logger.warning(f"Groq model '{request.model}' selected but GROQ_API_KEY not configured")
    if request.model == settings.openrouter_model and not os.environ.get("OPENROUTER_API_KEY"):
        logger.warning(f"OpenRouter model '{request.model}' selected but OPENROUTER_API_KEY not configured")

    logger.info(f"User {current_user.username} switched model to {request.model} ({settings.deployment_type} mode)")

    return ModelResponse(
        current_model=request.model,
        model_name=valid_models[request.model],
        status="Model switched successfully. New requests will use the selected model.",
    )


# ===== Main Streaming Analysis Endpoint =====

@router.post("/analyze/stream")
async def analyze_repository_stream(
    request: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Analyze repository with LLM using shared tool stack (unified frontend + RIM).
    Streams the conversation flow in real-time using Server-Sent Events.
    """
    async def stream_generator():
        start_time = datetime.now()

        try:
            # 1. Resolve repository
            repo = db.query(Repository).filter(
                Repository.repository_hash == request.repo_hash
            ).first()

            if not repo:
                logger.warning(f"Repository {request.repo_hash} not found, will proceed without context")
                repo_context = ""
                # When repo not found, use any available analysis for tool compatibility
                fallback_analysis = db.query(Analysis).filter(
                    Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                ).order_by(Analysis.created_at.desc()).first()
                analysis_id = fallback_analysis.id if fallback_analysis else None
                repo_display_name = request.repo_hash[:12]
                if analysis_id:
                    logger.error(f"[router:analysis_resolution:DIAGNOSTIC] repo=NOT_FOUND analysis_id={analysis_id} (USING FALLBACK)")
                else:
                    logger.error(f"[router:analysis_resolution:DIAGNOSTIC] repo=NOT_FOUND analysis_id=None")
            else:
                # Get the latest analysis for this repository
                analysis = db.query(Analysis).filter(
                    Analysis.repository_id == repo.id
                ).order_by(Analysis.created_at.desc()).first()

                if analysis:
                    analysis_id = analysis.id
                    repo_context = await build_repository_context(db, repo, analysis_id)
                    logger.error(f"[router:analysis_resolution:DIAGNOSTIC] repo='{repo.url}' analysis_id={analysis_id} (FOUND)")
                else:
                    # If no analysis for this repo, try to find any available analysis
                    # (fallback for repositories without dedicated analysis)
                    fallback_analysis = db.query(Analysis).filter(
                        Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                    ).order_by(Analysis.created_at.desc()).first()

                    if fallback_analysis:
                        analysis_id = fallback_analysis.id
                        repo_context = await build_repository_context(db, repo, analysis_id)
                        logger.error(f"[router:analysis_resolution:DIAGNOSTIC] repo='{repo.url}' analysis_id={analysis_id} (USING FALLBACK)")
                    else:
                        analysis_id = None
                        repo_context = ""
                        logger.error(f"[router:analysis_resolution:DIAGNOSTIC] repo='{repo.url}' analysis_id=None (NOT FOUND - no analysis)")

                repo_display_name = repo.url.split('/')[-1].replace('.git', '') if repo.url else request.repo_hash[:12]

            # 2. Stream initial thinking events
            yield f"data: {json.dumps({'type': 'user-query', 'content': request.query, 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"
            yield f"data: {json.dumps({'type': 'llm-thinking', 'content': 'Analyzing your question...', 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

            if repo_context:
                yield f"data: {json.dumps({'type': 'llm-thinking', 'content': f'Loaded repository context ({len(repo_context)} bytes)...', 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

            # 3. Select model
            valid_models = get_valid_models()
            configured_default = settings.model_prod_default if settings.deployment_type == "PROD" else settings.model_local_default
            default_model = configured_default if configured_default in valid_models else (next(iter(valid_models.keys())) if valid_models else configured_default)
            model = request.model or os.environ.get("OLLAMA_MODEL") or default_model
            if model not in valid_models:
                yield f"data: {json.dumps({'type': 'error', 'content': f'Invalid model: {model}. Available options: {list(valid_models.keys())}'})}\n\n"
                return

            if request.model:
                os.environ["OLLAMA_MODEL"] = model

            # Pass explicit model name so downstream QALoop and token counters know the active model
            model_for_llm = model

            # 4. Initialize structured logging
            structured_log = StructuredLogger(session_id=current_user.id, repository=repo_display_name)
            request_id = structured_log.log_query(request.query, current_user.email)

            # 5. Construct LLM service based on selected model
            # Route to provider based on model selection - NO FALLBACK FOR EXPLICIT MODEL SELECTION
            from backend.ai.service import LLMService

            if model == settings.gemini_model:
                # Gemini-only service - NO FALLBACK
                from backend.ai.providers.gemini import GeminiProvider
                gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
                gemini_provider = GeminiProvider(api_key=gemini_api_key, model=model)
                llm_service = LLMService(providers=[gemini_provider])
                selected_provider = "gemini"
                logger.info(f"[router] Using Gemini provider for model {model}")

            elif model == settings.groq_model:
                # Groq-only service - NO FALLBACK
                from backend.ai.providers.groq import GroqProvider
                groq_api_key = os.environ.get("GROQ_API_KEY", "")
                groq_provider = GroqProvider(api_key=groq_api_key, model=model)
                llm_service = LLMService(providers=[groq_provider])
                selected_provider = "groq"
                logger.info(f"[router] Using Groq provider for model {model}")

            elif model == settings.openrouter_model:
                # OpenRouter-only service - NO FALLBACK
                from backend.ai.providers.openrouter import OpenRouterProvider
                openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
                openrouter_provider = OpenRouterProvider(api_key=openrouter_api_key, model=model)
                llm_service = LLMService(providers=[openrouter_provider])
                selected_provider = "openrouter"
                logger.info(f"[router] Using OpenRouter provider for model {model}")

            elif model.startswith("qwen") or ("nemotron" in model.lower() and "nvidia" not in model.lower()):
                # Local Qwen or Nemotron model - Ollama-only service
                from backend.ai.providers.ollama import OllamaProvider
                ollama_url = settings.effective_ollama_base_url
                ollama_timeout = float(os.environ.get("OLLAMA_TIMEOUT", "600.0"))
                planner_ctx = int(os.environ.get("INVESTIGATION_PLANNER_CONTEXT", str(settings.investigation_planner_context)))
                primary_provider = OllamaProvider(base_url=ollama_url, model=model, timeout=ollama_timeout, num_ctx=planner_ctx)

                # Add fallback provider if different model configured
                fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", settings.model_local_quality)
                if fallback_model and fallback_model != model:
                    fallback_provider = OllamaProvider(base_url=ollama_url, model=fallback_model, timeout=ollama_timeout, num_ctx=planner_ctx)
                    llm_service = LLMService(providers=[primary_provider, fallback_provider])
                else:
                    llm_service = LLMService(providers=[primary_provider])
                selected_provider = "ollama"
                logger.info(f"[router] Using Ollama provider for model {model} (context={planner_ctx})")

            else:
                # Unknown model - use default service chain (should not reach here due to validation)
                llm_service = get_llm_service()
                selected_provider = llm_service.providers[0].provider_name if getattr(llm_service, "providers", None) else None
                logger.info(f"[router] Using default cloud provider chain for model {model}")

            repo_root = resolve_repo_root(repo_name=repo_display_name, user_id=current_user.id, db=db) if repo else None

            # 6. Create event queue for real-time tool visibility
            event_queue: asyncio.Queue = asyncio.Queue()

            async def on_turn_callback(turn_or_event: Any) -> None:
                """Called when each turn completes or orchestrator emits lifecycle events."""
                nonlocal total_prompt_tokens, total_completion_tokens

                if not request.show_tool_details:
                    return

                # If orchestrator emitted structured event dictionary directly
                if isinstance(turn_or_event, dict):
                    event = dict(turn_or_event)
                    if "timestamp" not in event:
                        event["timestamp"] = (datetime.now() - start_time).total_seconds()

                    # Update token totals if token event emitted
                    if event.get("type") == "token-update":
                        if "prompt_tokens" in event:
                            total_prompt_tokens = event["prompt_tokens"]
                        if "completion_tokens" in event:
                            total_completion_tokens = event["completion_tokens"]

                    try:
                        event_queue.put_nowait(event)
                    except Exception as e:
                        print(f"[on_turn] ERROR queueing orchestrator event: {e}")
                    return


                # Otherwise standard QALoopTurn object
                turn = turn_or_event
                tc_obj = getattr(turn, "tool_call", None) or {}
                obs_obj = getattr(turn, "tool_observation", None) or {}
                single_turn_call_id = tc_obj.get("tool_call_id") or obs_obj.get("tool_call_id") or f"turn_{turn.turn_index}"

                if getattr(turn, "tool_call", None):
                    event = {
                        "type": "tool-call",
                        "tool_call_id": single_turn_call_id,
                        "tool_name": turn.tool_call.get("tool_name"),
                        "arguments": turn.tool_call.get("arguments", {}),
                        "turn_index": turn.turn_index,
                        "timestamp": (datetime.now() - start_time).total_seconds(),
                    }
                    try:
                        event_queue.put_nowait(event)
                    except Exception as e:
                        print(f"[on_turn] ERROR queueing tool-call: {e}")

                if getattr(turn, "tool_observation", None):
                    event = {
                        "type": "tool-response",
                        "tool_call_id": single_turn_call_id,
                        "tool_name": turn.tool_observation.get("tool_name"),
                        "success": turn.tool_observation.get("success", False),
                        "result_summary": turn.tool_observation.get("formatted_message") or turn.tool_observation.get("data", ""),
                        "result_count": len(turn.tool_observation.get("data", [])) if isinstance(turn.tool_observation.get("data"), list) else None,
                        "error": turn.tool_observation.get("error"),
                        "duration_ms": turn.duration_ms,
                        "turn_index": turn.turn_index,
                        "timestamp": (datetime.now() - start_time).total_seconds(),
                    }
                    try:
                        event_queue.put_nowait(event)
                    except Exception as e:
                        print(f"[on_turn] ERROR queueing tool-response: {e}")

                # Emit token update after every turn
                total_prompt_tokens += getattr(turn, "prompt_tokens", 0)
                total_completion_tokens += getattr(turn, "completion_tokens", 0)
                token_event = {
                    "type": "token-update",
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": total_prompt_tokens + total_completion_tokens,
                    "turn_index": getattr(turn, "turn_index", 0),
                    "timestamp": (datetime.now() - start_time).total_seconds(),
                }
                try:
                    event_queue.put_nowait(token_event)
                except Exception as e:
                    print(f"[on_turn] ERROR queueing token-update: {e}")

            # 7. Build analysis service using shared factory
            service_mode = "multi_agent" if request.investigation_mode == "multi_agent" else "rim"
            analysis_service = build_analysis_service(
                llm_service=llm_service,
                db=db,
                repo_name=repo_display_name,
                analysis_id=analysis_id,
                user_id=current_user.id,
                model=model_for_llm,
                provider=selected_provider,
                repo_root=repo_root,
                rim_metadata_block=repo_context or None,
                on_turn_callback=on_turn_callback,
                structured_logger=structured_log,
                request_id=request_id,
                repository=repo_display_name,
                mode=service_mode,
                worker_type=request.worker_type or "local",
                worker_model=request.worker_model,
            )

            # Run analysis as background task
            loop_task = asyncio.create_task(analysis_service.run(request.query))

            # 8. Drain event queue in parallel with analysis execution
            total_tool_calls = 0
            total_prompt_tokens = 0
            total_completion_tokens = 0
            events_yielded = 0

            print(f"[stream_generator] Starting event drain loop, analysis_task.done()={loop_task.done()}")

            try:
                last_keepalive = time.time()
                while not loop_task.done():
                    try:
                        # Check for queued events with short timeout
                        try:
                            event = event_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            now = time.time()
                            # Emit SSE keepalive comment every 15s to keep proxy/Undici socket and body alive
                            if now - last_keepalive >= 15.0:
                                last_keepalive = now
                                yield ": keepalive\n\n"
                            await asyncio.sleep(0.05)
                            continue

                        last_keepalive = time.time()
                        try:
                            json_str = json.dumps(event)
                            events_yielded += 1
                            print(f"[stream_generator] Yielding event {events_yielded}: type={event.get('type')}")
                        except Exception as json_err:
                            logger.error(f"[stream_generator] JSON serialization failed: {json_err}", exc_info=True)
                            continue
                        yield f"data: {json_str}\n\n"
                    except Exception as e:
                        logger.error(f"[stream_generator] Error in event loop: {e}", exc_info=True)
                        break

                print(f"[stream_generator] Main loop exited, events_yielded so far={events_yielded}")

                # Drain any remaining events after analysis completes
                while not event_queue.empty():
                    try:
                        event = event_queue.get_nowait()
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.QueueEmpty:
                        break
                    except Exception as e:
                        logger.error(f"[router:sse] Error draining queue: {e}", exc_info=True)
                        break

                # Get final result
                result = await loop_task
                total_tool_calls = result.tool_call_count
                # Note: tokens already accumulated in on_turn_callback, no need to re-add

            except Exception as e:
                logger.error(f"Error during QALoop execution: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': format_error_message(e)})}\n\n"
                return

            # 9. Emit final answer
            final_event = {
                "type": "final-answer",
                "content": result.answer,
                "stop_reason": result.stop_reason.value,
                "timestamp": (datetime.now() - start_time).total_seconds(),
            }
            logger.error(f"[router:sse:DIAGNOSTIC:final-answer] stop_reason={result.stop_reason.value} answer_len={len(result.answer)}")
            yield f"data: {json.dumps(final_event)}\n\n"

            # 10. Emit completion metrics
            elapsed_seconds = (datetime.now() - start_time).total_seconds()
            completion_event = {
                "type": "completed",
                "tool_calls_count": total_tool_calls,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "elapsed_seconds": elapsed_seconds,
                "model_used": model,
                "timestamp": elapsed_seconds,
            }
            logger.error(f"[router:sse:DIAGNOSTIC:completed] tool_calls={total_tool_calls} elapsed_s={elapsed_seconds:.1f}")
            yield f"data: {json.dumps(completion_event)}\n\n"

        except Exception as e:
            logger.error(f"Error in analyze_repository_stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': format_error_message(e)})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
