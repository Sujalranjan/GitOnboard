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
from backend.repository_tools.tools import RepositoryToolLayer, resolve_repo_root
from backend.services.qa_loop import QALoop, QALoopTurn
from backend.services.qa_protocol import QAProtocolAdapter
from backend.services.tool_dispatch import TargetEntityResolver, ToolDispatchTable
from backend.agent.loop.contracts import AgentLoopConfig
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser

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
        context_parts.append(f"Repository: {repo.repository_hash}")
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
            FactSymbol.type.in_(["class", "interface", "function", "enum"])
        ).limit(15).all()

        for sym in top_symbols:
            context_parts.append(f"- {sym.name} ({sym.type})")
            if sym.description:
                context_parts.append(f"  {sym.description}")

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

VALID_MODELS = {
    "qwen3:4b-instruct": "Qwen 3 4B (Fast)",
    "qwen2.5-coder:7b": "Qwen 2.5 Coder 7B (Quality)",
    "cloud-gemini": "Gemini (Cloud)",
    "cloud-openrouter": "OpenRouter (Cloud)",
}


class SetModelRequest(BaseModel):
    model: str


class ModelResponse(BaseModel):
    current_model: str
    model_name: str
    status: str


class AnalyzeRequest(BaseModel):
    query: str
    repo_hash: str
    model: str = None
    show_tool_details: bool = True


@router.post("/set-model", response_model=ModelResponse)
def set_model(
    request: SetModelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change the active LLM model for this session.
    """
    if request.model not in VALID_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model. Valid options: {list(VALID_MODELS.keys())}",
        )

    # Set model in environment (affects new requests)
    os.environ["OLLAMA_MODEL"] = request.model

    # For cloud models, check that API keys are configured
    if request.model == "cloud-gemini" and not os.environ.get("GEMINI_API_KEY"):
        logger.warning("Gemini model selected but GEMINI_API_KEY not configured")
    if request.model == "cloud-openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        logger.warning("OpenRouter model selected but OPENROUTER_API_KEY not configured")

    logger.info(f"User {current_user.username} switched model to {request.model}")

    return ModelResponse(
        current_model=request.model,
        model_name=VALID_MODELS[request.model],
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
                analysis_id = None
                repo_display_name = request.repo_hash[:12]
            else:
                # Get the latest analysis for this repository
                analysis = db.query(Analysis).filter(
                    Analysis.repository_id == repo.id
                ).order_by(Analysis.created_at.desc()).first()

                if analysis:
                    analysis_id = analysis.id
                    repo_context = await build_repository_context(db, repo, analysis_id)
                else:
                    analysis_id = None
                    repo_context = ""

                repo_display_name = repo.url.split('/')[-1].replace('.git', '') if repo.url else request.repo_hash[:12]

            # 2. Stream initial thinking events
            yield f"data: {json.dumps({'type': 'user-query', 'content': request.query, 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"
            yield f"data: {json.dumps({'type': 'llm-thinking', 'content': 'Analyzing your question...', 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

            if repo_context:
                yield f"data: {json.dumps({'type': 'llm-thinking', 'content': f'Loaded repository context ({len(repo_context)} bytes)...', 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

            # 3. Select model
            model = request.model or os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")
            if model not in VALID_MODELS:
                yield f"data: {json.dumps({'type': 'error', 'content': f'Invalid model: {model}'})}\n\n"
                return

            if request.model:
                os.environ["OLLAMA_MODEL"] = model

            # 4. Construct shared tool stack
            llm_service = get_llm_service()
            repo_root = resolve_repo_root(repo_name=repo_display_name, user_id=current_user.id, db=db) if repo else None

            tool_layer = RepositoryToolLayer(
                repo_name=repo_display_name,
                analysis_id=analysis_id,
                db=db,
                repo_root=repo_root,
                user_id=current_user.id,
            )

            graph_traverser = FactStoreGraphTraverser(db, analysis_id) if analysis_id else None
            target_resolver = TargetEntityResolver(db, analysis_id) if analysis_id else None
            tool_dispatch = ToolDispatchTable(tool_layer, graph_traverser, target_resolver)

            protocol = QAProtocolAdapter(model_id=model)
            prompt_parts = protocol.build_system_prompt(
                tool_specs=tool_dispatch.specs(include_rim=True),
                rim_metadata_block=repo_context or None,
            )

            config = AgentLoopConfig(
                max_agent_turns=50,
                max_tool_calls=15,
                max_command_executions=0,
                max_execution_seconds=180,
                max_observation_bytes=8000,
                max_repeated_tool_calls=3,
            )

            # 5. Create event queue for real-time tool visibility
            event_queue: asyncio.Queue = asyncio.Queue()

            async def on_turn_callback(turn: QALoopTurn) -> None:
                """Called when each turn completes; emits structured events to queue."""
                if not request.show_tool_details:
                    return

                if turn.tool_call:
                    event_queue.put_nowait({
                        "type": "tool-call",
                        "tool_name": turn.tool_call.get("tool_name"),
                        "arguments": turn.tool_call.get("arguments", {}),
                        "turn_index": turn.turn_index,
                        "timestamp": (datetime.now() - start_time).total_seconds(),
                    })

                if turn.tool_observation:
                    event_queue.put_nowait({
                        "type": "tool-response",
                        "tool_name": turn.tool_observation.get("tool_name"),
                        "success": turn.tool_observation.get("success", False),
                        "result_summary": turn.tool_observation.get("formatted_message", "")[:1500],
                        "result_count": len(turn.tool_observation.get("data", [])) if isinstance(turn.tool_observation.get("data"), list) else None,
                        "error": turn.tool_observation.get("error"),
                        "duration_ms": turn.duration_ms,
                        "turn_index": turn.turn_index,
                        "timestamp": (datetime.now() - start_time).total_seconds(),
                    })

            # 6. Create and run the QALoop in background
            loop = QALoop(
                llm_service=llm_service,
                tool_dispatch=tool_dispatch,
                config=config,
                system_prompt_parts=prompt_parts,
                model=model,
                on_turn=on_turn_callback,
            )

            # Run loop as background task
            loop_task = asyncio.create_task(loop.run(request.query))

            # 7. Drain event queue in parallel with loop execution
            total_tool_calls = 0
            total_prompt_tokens = 0
            total_completion_tokens = 0

            try:
                while not loop_task.done():
                    try:
                        # Check for queued events (non-blocking)
                        event = event_queue.get_nowait()
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.QueueEmpty:
                        # No events, yield control briefly
                        await asyncio.sleep(0.01)

                # Drain any remaining events after loop completes
                while not event_queue.empty():
                    event = event_queue.get_nowait()
                    yield f"data: {json.dumps(event)}\n\n"

                # Get final result
                result = await loop_task
                total_tool_calls = result.tool_call_count
                for turn in result.turns:
                    total_prompt_tokens += turn.prompt_tokens
                    total_completion_tokens += turn.completion_tokens

            except Exception as e:
                logger.error(f"Error during QALoop execution: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': format_error_message(e)})}\n\n"
                return

            # 8. Emit final answer
            final_event = {
                "type": "final-answer",
                "content": result.answer,
                "stop_reason": result.stop_reason.value,
                "timestamp": (datetime.now() - start_time).total_seconds(),
            }
            yield f"data: {json.dumps(final_event)}\n\n"

            # 9. Emit completion metrics
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
            yield f"data: {json.dumps(completion_event)}\n\n"

        except Exception as e:
            logger.error(f"Error in analyze_repository_stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': format_error_message(e)})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
