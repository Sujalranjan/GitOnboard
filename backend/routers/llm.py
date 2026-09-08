"""LLM settings and model management endpoints."""
import os
import logging
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.models.user import User
from backend.models.repository import Repository
from backend.config import settings
from backend.ai.service import get_llm_service
from backend.ai.schemas import LLMRequest, Message, MessageRole, Tool
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.models.fact_store import FactSymbol, FactFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["llm"])


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


# ===== Tool Implementations =====

async def execute_search_symbols(query: str, db: Session, analysis_id: Optional[int] = None) -> str:
    """Search for code symbols matching the query."""
    try:
        logger.debug(f"[SEARCH] execute_search_symbols called with query='{query}', analysis_id={analysis_id}")

        # Try to use workspace tool handler first
        try:
            from backend.agent.tools.repository import handle_search_symbols
            from backend.agent.tools.contracts import AgentToolContext

            context = AgentToolContext(
                analysis_id=analysis_id,
                repository_id=None,
                db=db
            )

            result = handle_search_symbols(
                args={"pattern": query, "limit": 10},
                context=context
            )

            logger.debug(f"[SEARCH] handle_search_symbols returned: {result}")

            if result and result.get('symbols_found'):
                output = f"Found {len(result.get('symbols_found', []))} matching symbols:\n"
                for sym in result.get('symbols_found', [])[:5]:
                    output += f"- {sym.get('name', 'Unknown')} ({sym.get('type', 'unknown')})\n"
                    if sym.get('file'):
                        output += f"  File: {sym.get('file')}\n"
                logger.debug(f"[SEARCH] Returning from handle_search_symbols")
                return output
            else:
                logger.debug(f"[SEARCH] handle_search_symbols returned but no 'symbols_found' key, falling through to HybridRetriever")
        except Exception as e:
            logger.debug(f"[SEARCH] handle_search_symbols exception: {e}, falling back to HybridRetriever")
            pass  # Fallback to retriever if handler fails

        # Fallback: Use HybridRetriever
        logger.debug(f"[SEARCH] Calling HybridRetriever with analysis_id={analysis_id}")
        retriever = HybridRetriever(db, analysis_id=analysis_id)
        results = retriever.retrieve(query, top_k=5)

        logger.debug(f"[SEARCH] HybridRetriever returned {len(results) if results else 0} results: {results}")

        if not results:
            # Empty result - guide LLM to try alternatives
            logger.debug(f"[SEARCH] No results found")
            return f"No symbols found matching '{query}'. TRY ALTERNATIVE SEARCH TERMS: Try searching for related terms like synonyms, abbreviations, or more specific/general versions of the query."

        output = f"Found {len(results)} matching symbols:\n"
        for i, result in enumerate(results, 1):
            output += f"{i}. {result.entity_name} ({result.entity_type.value})\n"
            if result.file_path:
                output += f"   File: {result.file_path}\n"

        logger.debug(f"[SEARCH] Returning formatted results")
        return output
    except Exception as e:
        logger.error(f"Error searching symbols: {e}", exc_info=True)
        return f"Error searching symbols: {str(e)}"


async def execute_read_file(file_path: str, db: Session, analysis_id: Optional[int] = None) -> str:
    """Read the contents of a file from the repository."""
    try:
        # Query the FactFile model for the file
        fact_file = db.query(FactFile).filter(
            FactFile.path == file_path,
            FactFile.analysis_id == analysis_id
        ).first()

        if not fact_file:
            return f"File not found: {file_path}"

        # Try to get content from the file object
        if hasattr(fact_file, 'content') and fact_file.content:
            content = fact_file.content
        elif hasattr(fact_file, 'blob_name') and fact_file.blob_name:
            # File content is in blob storage - for now return a placeholder
            return f"File: {file_path}\n[Content stored in blob storage - {fact_file.blob_name}]\n(Full content retrieval would require blob client)"
        else:
            return f"File exists but content not available: {file_path}"

        # Truncate if too long
        if len(content) > 2000:
            content = content[:2000] + "\n... (truncated)"

        return f"File: {file_path}\n```\n{content}\n```"
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return f"Error reading file: {str(e)}"


async def execute_analyze_relationships(query: str, db: Session, analysis_id: Optional[int] = None) -> str:
    """Analyze relationships between code components."""
    try:
        # Query for related symbols based on the query
        related_symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.name.ilike(f"%{query}%")
        ).limit(10).all()

        if not related_symbols:
            return f"No relationship data found for '{query}'"

        output = f"Found {len(related_symbols)} related components:\n"
        for sym in related_symbols:
            # Use symbol_type if available, otherwise use kind
            sym_type = getattr(sym, 'symbol_type', getattr(sym, 'kind', 'unknown'))
            output += f"- {sym.name} ({sym_type})\n"
            if hasattr(sym, 'relationships') and sym.relationships:
                output += f"  Related to: {', '.join([str(r) for r in sym.relationships[:3]])}\n"

        return output
    except Exception as e:
        logger.error(f"Error analyzing relationships: {e}")
        return f"Error analyzing relationships: {str(e)}"

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
    repo_name: str
    model: str = None
    show_tool_details: bool = True


class FlowStep(BaseModel):
    type: str  # "user-query", "llm-thinking", "tool-call", "tool-response", "final-answer"
    content: str
    tool_name: str = None
    timestamp: float = None


class AnalyzeResponse(BaseModel):
    flow: List[FlowStep]
    model_used: str
    total_tokens: int = 0
    tool_calls_count: int = 0
    elapsed_seconds: float = 0


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


@router.get("/current-model", response_model=ModelResponse)
def get_current_model(current_user: User = Depends(get_current_user)):
    """Get the currently active LLM model."""
    model = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")

    if model not in VALID_MODELS:
        model = "qwen3:4b-instruct"

    return ModelResponse(
        current_model=model,
        model_name=VALID_MODELS.get(model, "Unknown"),
        status="success",
    )


@router.get("/available-models")
def get_available_models(current_user: User = Depends(get_current_user)):
    """Get list of available models and their capabilities."""
    return {
        "models": [
            {
                "id": "qwen3:4b-instruct",
                "name": "Qwen 3 4B (Fast)",
                "description": "Quick responses, limited reasoning",
                "category": "fast",
                "parameters": "4B",
                "status": "available",
            },
            {
                "id": "qwen2.5-coder:7b",
                "name": "Qwen 2.5 Coder 7B (Quality)",
                "description": "Better reasoning, slower",
                "category": "quality",
                "parameters": "7B",
                "status": "available" if settings.deployment_type.upper() == "LOCAL" else "available",
            },
            {
                "id": "cloud-gemini",
                "name": "Gemini (Cloud)",
                "description": "Best quality, requires API key",
                "category": "cloud",
                "parameters": "Large",
                "status": "available" if os.environ.get("GEMINI_API_KEY") else "not_configured",
            },
            {
                "id": "cloud-openrouter",
                "name": "OpenRouter (Cloud)",
                "description": "Multiple models (Claude, GPT-4), requires API key",
                "category": "cloud",
                "parameters": "Large",
                "status": "available" if os.environ.get("OPENROUTER_API_KEY") else "not_configured",
            },
        ]
    }


@router.post("/analyze/stream")
async def analyze_repository_stream(
    request: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Analyze repository with LLM using selected model.
    Streams the conversation flow in real-time using Server-Sent Events.
    """
    async def stream_generator():
        start_time = datetime.now()

        try:
            # Verify repository exists (allow access to any repository for analysis)
            repo = db.query(Repository).filter(
                (Repository.repository_hash == request.repo_name) | (Repository.url.contains(request.repo_name))
            ).first()

            if not repo:
                logger.warning(f"Repository {request.repo_name} not found, will proceed without context")

            # Use selected model or current model
            model = request.model or os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")

            # Validate model
            if model not in VALID_MODELS:
                yield f"data: {json.dumps({'type': 'error', 'content': f'Invalid model: {model}'})}\n\n"
                return

            # Set model for this request
            if request.model:
                os.environ["OLLAMA_MODEL"] = model

            # 1. Stream user query
            yield f"data: {json.dumps({'type': 'user-query', 'content': request.query, 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

            # 2. Stream LLM thinking
            yield f"data: {json.dumps({'type': 'llm-thinking', 'content': 'Analyzing your question and determining what tools to use...', 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

            # 3. Build rich repository context
            repo_context = ""
            analysis_id = None
            if repo:
                # Get the latest analysis for this repository
                from backend.models.repository import Analysis
                analysis = db.query(Analysis).filter(
                    Analysis.repository_id == repo.id
                ).order_by(Analysis.created_at.desc()).first()

                if analysis:
                    analysis_id = analysis.id
                    repo_context = await build_repository_context(db, repo, analysis_id)
                    yield f"data: {json.dumps({'type': 'llm-thinking', 'content': f'Loaded repository context ({len(repo_context)} bytes)...', 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

            # 4. Call LLM with repository context using JSON tool protocol
            llm_service = get_llm_service()

            system_prompt = f"""You are an expert code analyst helping understand the {request.repo_name} repository.

## Repository Information
{repo_context if repo_context else f"Repository: {request.repo_name}"}

## Your Task
Answer questions about this codebase by using tools to gather real information:
1. Use search_symbols to find relevant code components
2. Use read_file to examine actual implementations
3. Use analyze_relationships to understand connections
4. Synthesize findings into clear explanations

## Response Protocol (CRITICAL)
You MUST respond with ONLY a JSON object in ONE of two formats:

**Format 1: Use a Tool**
```json
{{
  "action": "tool_call",
  "tool_name": "search_symbols",
  "arguments": {{
    "query": "search term"
  }}
}}
```

**Format 2: Complete and Answer**
```json
{{
  "action": "complete",
  "content": "Your final answer here"
}}
```

## Rules
1. Respond with ONLY JSON - no markdown, no explanations
2. Use tools to gather real data before answering
3. Stream of work: Tool → Tool → Tool → Complete
4. When you have enough information, use "complete" action
5. Never guess - if you can't find something, try alternative searches
6. If a search returns no results, try related terms before giving up

## Smart Fallback Strategy
CRITICAL: If search_symbols returns "No symbols found", DO NOT GIVE UP!

When a search returns zero results, intelligently try alternative keywords:
- Think of SYNONYMS (e.g., if "login" fails, try "auth", "authenticate", "signin")
- Think of ABBREVIATIONS (e.g., if "database" fails, try "db")
- Think of RELATED CONCEPTS (e.g., if "cache" fails, try "storage", "persistence")
- Think of BROADER TERMS (e.g., if "token" fails, try "security", "auth")
- Think of NARROWER TERMS (e.g., if "data" fails, try specific types like "user", "config")
- Think of TECHNICAL VARIANTS (e.g., if "json" fails, try "parse", "serialize", "format")

YOUR RESPONSIBILITY: Use your code knowledge to decide what alternative keywords make sense.
Continue searching with different terms until you either:
1. Find relevant symbols
2. Reach iteration limit

Do NOT complete prematurely - try at least 3-5 different search terms before giving up!

## Available Tools
- search_symbols: Find code symbols (name or pattern) - use varied search terms!
- read_file: Read file contents
- analyze_relationships: Understand component connections"""

            # Build conversation with tool loop
            messages = [
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=request.query),
            ]

            max_iterations = 10  # Increased for more thorough exploration
            iteration = 0
            final_answer = None

            # 5. Tool-calling loop
            while iteration < max_iterations:
                iteration += 1

                # If approaching limit, tell LLM to wrap up
                if iteration >= max_iterations - 1:
                    messages.append(
                        Message(role=MessageRole.USER, content="You've completed your investigation. Now provide a final comprehensive answer based on what you've learned. Use the complete action to summarize your findings.")
                    )

                # Call LLM
                llm_request = LLMRequest(
                    messages=messages,
                    model=model,
                    temperature=0.2,
                    max_tokens=2048,  # Lower for each iteration
                    tools=None,  # Don't use OpenAI tool schema
                    tool_choice=None
                )

                response = await llm_service.generate(llm_request)
                response_text = response.content.strip()

                # Parse JSON response
                try:
                    # Try to extract JSON from markdown code fences if present
                    if "```json" in response_text:
                        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
                        if json_match:
                            response_text = json_match.group(1).strip()

                    action_data = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse LLM JSON response: {response_text[:100]}")
                    yield f"data: {json.dumps({'type': 'tool-response', 'content': 'Error: Invalid JSON response from LLM', 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"
                    break

                # Handle actions
                if action_data.get("action") == "complete":
                    # LLM is done
                    final_answer = action_data.get("content", "No answer provided")
                    break

                elif action_data.get("action") == "tool_call":
                    # Execute tool
                    tool_name = action_data.get("tool_name", "")
                    arguments = action_data.get("arguments", {})

                    # Stream the tool call
                    yield f"data: {json.dumps({'type': 'tool-call', 'content': f'Calling {tool_name} with: {json.dumps(arguments)}', 'tool_name': tool_name, 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

                    # Execute the tool
                    tool_result = ""
                    try:
                        if tool_name == "search_symbols":
                            tool_result = await execute_search_symbols(
                                arguments.get("query", ""),
                                db,
                                analysis_id
                            )
                        elif tool_name == "read_file":
                            tool_result = await execute_read_file(
                                arguments.get("file_path", ""),
                                db,
                                analysis_id
                            )
                        elif tool_name == "analyze_relationships":
                            tool_result = await execute_analyze_relationships(
                                arguments.get("query", ""),
                                db,
                                analysis_id
                            )
                        else:
                            tool_result = f"Unknown tool: {tool_name}"
                    except Exception as e:
                        logger.error(f"Error executing tool {tool_name}: {e}")
                        tool_result = f"Error: {str(e)}"

                    # Stream tool response
                    yield f"data: {json.dumps({'type': 'tool-response', 'content': tool_result, 'tool_name': tool_name, 'timestamp': (datetime.now() - start_time).total_seconds()})}\n\n"

                    # Add tool result to conversation
                    messages.append(Message(role=MessageRole.ASSISTANT, content=response_text))
                    messages.append(
                        Message(
                            role=MessageRole.USER,
                            content=f"Tool '{tool_name}' returned:\n{tool_result}"
                        )
                    )
                else:
                    logger.warning(f"Unknown action: {action_data.get('action')}")
                    break

            # Use final answer from LLM or synthesize from findings
            if not final_answer:
                # Synthesize answer from the collected tool results
                synthesis_prompt = f"Based on all the information gathered through {iteration - 1} tool searches, provide a final comprehensive answer to the original question: {request.query}"
                messages.append(Message(role=MessageRole.USER, content=synthesis_prompt))

                # Final synthesis call
                final_llm_request = LLMRequest(
                    messages=messages,
                    model=model,
                    temperature=0.2,
                    max_tokens=2048,
                    tools=None,
                    tool_choice=None
                )

                try:
                    final_response = await llm_service.generate(final_llm_request)
                    final_answer = final_response.content.strip()
                except Exception as e:
                    logger.warning(f"Failed to generate synthesis: {e}")
                    final_answer = "Analysis complete. See tool results above for findings."

            # 6. Stream final answer
            elapsed = (datetime.now() - start_time).total_seconds()
            yield f"data: {json.dumps({'type': 'final-answer', 'content': final_answer, 'timestamp': elapsed})}\n\n"

            # 7. Stream completion metadata
            yield f"data: {json.dumps({'type': 'completed', 'model_used': model, 'total_tokens': 0, 'tool_calls_count': iteration - 1, 'elapsed_seconds': elapsed})}\n\n"

        except Exception as e:
            logger.error(f"Error analyzing repository: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': f'Analysis failed: {str(e)}'})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
