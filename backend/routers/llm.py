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


# ===== Tool Implementations =====

async def execute_search_symbols(query: str, db: Session, analysis_id: Optional[int] = None) -> str:
    """
    Search for code symbols matching the query.
    Supports multiple queries: "auth,login,verify" → searches all at once, returns grouped results.
    """
    try:
        # Split comma-separated queries and clean them
        queries = [q.strip() for q in query.split(",") if q.strip()]
        logger.debug(f"[SEARCH] execute_search_symbols called with {len(queries)} query(ies): {queries}, analysis_id={analysis_id}")

        if not queries:
            return "No search query provided"

        # Use HybridRetriever for all queries
        retriever = HybridRetriever(db, analysis_id=analysis_id)

        # Collect results grouped by query
        all_results = {}
        total_files = set()  # Track unique files across all queries

        for q in queries:
            logger.debug(f"[SEARCH] Searching for: '{q}'")
            results = retriever.retrieve(q, top_k=5)
            all_results[q] = results

            # Track unique files
            for result in (results or []):
                if result.file_path:
                    total_files.add(result.file_path)

        # Format output: grouped by query with file references
        if not total_files:
            return (
                f"No symbols found matching any of: {', '.join(queries)}\n\n"
                f"TRY: Use synonyms like 'auth' vs 'authenticate', 'login' vs 'signin', etc."
            )

        output = f"Symbol Search Results ({len(queries)} query(ies) across {len(total_files)} file(s)):\n\n"

        for q in queries:
            results = all_results[q]
            if not results:
                output += f"❌ Query '{q}': No matches\n"
                continue

            output += f"✓ Query '{q}': Found {len(results)} matching symbols\n"
            for result in results[:3]:  # Limit to 3 per query for brevity
                output += f"  - {result.entity_name} ({result.entity_type.value})\n"
                if result.file_path:
                    output += f"    📄 {result.file_path}\n"
            if len(results) > 3:
                output += f"  ... and {len(results) - 3} more\n"

        output += f"\nFiles to investigate: {', '.join(sorted(total_files))}\n"
        output += f"Use: list_file_symbols(file_path) to see available symbols in each file"

        logger.debug(f"[SEARCH] Returning grouped results for {len(queries)} queries")
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
            # File content is in blob storage - fetch it
            try:
                from backend.storage import get_storage
                storage = get_storage()
                content = storage.get_object_text(fact_file.blob_name)
                logger.debug(f"[READ_FILE_BLOB] Fetched {len(content)} bytes from blob: {fact_file.blob_name}")
            except FileNotFoundError:
                return f"File exists in index but blob not found: {file_path} (blob: {fact_file.blob_name})"
            except Exception as e:
                logger.warning(f"[READ_FILE_BLOB] Failed to fetch blob {fact_file.blob_name}: {e}")
                return f"File exists but could not retrieve content from blob storage: {file_path}"
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


async def execute_list_file_symbols(file_path: str, db: Session, analysis_id: Optional[int] = None) -> str:
    """List all symbols (functions, classes, etc.) in a specific file with line numbers."""
    try:
        if not analysis_id:
            return f"Cannot list symbols without analysis context"

        # Query all symbols in this file
        symbols = db.query(FactSymbol).filter(
            FactSymbol.file_path == file_path,
            FactSymbol.analysis_id == analysis_id
        ).all()

        if not symbols:
            return f"No symbols found in file: {file_path}"

        output = f"Symbols in {file_path}:\n"
        for sym in sorted(symbols, key=lambda s: s.start_line or 0):
            sym_type = getattr(sym, 'symbol_type', 'unknown').upper()
            start_line = getattr(sym, 'start_line', '?')
            end_line = getattr(sym, 'end_line', '?')
            output += f"- {sym.name} ({sym_type}) [lines {start_line}-{end_line}]\n"

        output += f"\n💡 Use: read_file(file_path=\"{file_path}\", start_line=X, end_line=Y) to fetch specific symbol code"
        return output
    except Exception as e:
        logger.error(f"Error listing file symbols: {e}")
        return f"Error listing file symbols: {str(e)}"

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
                Repository.repository_hash == request.repo_hash
            ).first()

            if not repo:
                logger.warning(f"Repository {request.repo_hash} not found, will proceed without context")

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

            repo_display_name = repo.url.split('/')[-1].replace('.git', '') if repo and repo.url else request.repo_hash[:12]
            system_prompt = f"""You are an expert code analyst helping understand the {repo_display_name} repository.

## Repository Information
{repo_context if repo_context else f"Repository: {repo_display_name}"}

## Your Task
Answer questions about this codebase by using tools to gather real information:
1. Use search_symbols to find relevant code components
2. Use read_file to examine actual implementations
3. Use analyze_relationships to understand connections
4. Synthesize findings into clear explanations

## Response Protocol (CRITICAL - MUST FOLLOW EXACTLY)

You MUST respond with ONLY a valid JSON object. NO other text, NO markdown, NO explanations.

The "action" field determines what happens NEXT. It has ONLY 2 possible values:
- "action": "tool_call" (call a tool)
- "action": "complete" (finish and answer)

**NEVER use a tool name as the action value.** For example, NEVER write "action": "search_symbols". That is WRONG.

---

**FORMAT A: Call a Tool**
```json
{{
  "action": "tool_call",
  "tool_name": "search_symbols",
  "arguments": {{
    "query": "search term"
  }}
}}
```

Examples of CORRECT tool calls:
```json
{{"action": "tool_call", "tool_name": "search_symbols", "arguments": {{"query": "auth,authenticate,login,verify"}}}}
{{"action": "tool_call", "tool_name": "list_file_symbols", "arguments": {{"file_path": "backend/auth.py"}}}}
{{"action": "tool_call", "tool_name": "read_file", "arguments": {{"file_path": "backend/auth.py", "start_line": 10, "end_line": 25}}}}
{{"action": "tool_call", "tool_name": "analyze_relationships", "arguments": {{"query": "authenticate"}}}}
```

⭐ **BEST PRACTICE:** Use comma-separated queries in search_symbols to reduce back-and-forth!

Examples of WRONG format (NEVER do this):
```json
{{"action": "search_symbols", "arguments": {{"query": "..."}}}}  ← WRONG! Don't use tool name as action
{{"action": "read_file", "file_path": "..."}}  ← WRONG! Don't use tool name as action
```

---

**FORMAT B: Finish and Answer**
```json
{{
  "action": "complete",
  "content": "Your final answer based on findings"
}}
```

---

## Critical Rules
1. **ONLY JSON** - Your entire response must be valid JSON. Nothing else.
2. **"action" field is ALWAYS "tool_call" OR "complete"** - Never anything else.
3. **"tool_name" field (when action is tool_call)** - Must be one of: search_symbols, read_file, list_file_symbols, analyze_relationships
4. **DO NOT REPEAT** the same tool call twice (line 379-382 below explain this in detail)
5. Use tools to gather real data before answering
6. Stream of work: Tool → Tool → Tool → Complete

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

### 1. search_symbols(query: string)
**Purpose:** Find code symbols matching your search query(ies).
**SUPPORTS MULTIPLE QUERIES:** Pass comma-separated queries to search all at once!
**Returns:** Symbol names and file locations, grouped by query.
**IMPORTANT:** Returns file paths, NOT line numbers or code content!

**Single query:**
  - Call: search_symbols(query="authentication")
  - Get: [AuthenticationModule, verify_password, login_handler, ...]

**Multiple queries (RECOMMENDED - reduces round-trips!):**
  - Call: search_symbols(query="auth,authenticate,login,verify")
  - Backend searches ALL 4 terms at once
  - Returns results grouped by query showing which files matched which search
  - Example output:
    ```
    ✓ Query 'auth': Found 3 symbols (backend/auth.py, backend/dependencies/auth.py)
    ✓ Query 'authenticate': Found 2 symbols (backend/auth/service.py)
    ✓ Query 'login': Found 5 symbols (backend/routers/auth.py)
    ✗ Query 'verify': No matches
    Files to investigate: backend/auth.py, backend/dependencies/auth.py, backend/routers/auth.py
    ```

**When to use:**
- First step - locate files containing relevant code
- Use multiple queries to explore the search space efficiently in ONE call!

**Optimization:** Instead of LLM making 4 separate search_symbols calls, use ONE call with comma-separated queries!

### 2. read_file(file_path: string, start_line?: int, end_line?: int)
**Purpose:** Read file contents from repository (supports line-range fetching).
**Parameters:**
  - file_path (required): Full path like "backend/auth.py"
  - start_line (optional, default 1): Starting line number (1-based)
  - end_line (optional, default 50): Ending line number
**Returns:** File content (truncated to 2000 chars if too long).
**IMPORTANT:** Use start_line/end_line to fetch ONLY relevant portions!
**When to use:** After search_symbols finds a file, read specific sections.
**Example workflow:**
  1. search_symbols found: "authenticate function in backend/auth.py"
  2. Call: read_file(file_path="backend/auth.py", start_line=1, end_line=50)
  3. Read the code to understand implementation
**❌ DO NOT:** Fetch entire large files - specify line ranges!

### 3. list_file_symbols(file_path: string)
**Purpose:** List all symbols (functions, classes, methods) in a specific file with line numbers.
**Returns:** Symbol name, type (FUNCTION/CLASS/METHOD), and start-end line numbers.
**When to use:** Before read_file - see what's available in a file, pick specific symbols to read.
**Example workflow:**
  1. search_symbols found: "backend/auth.py contains authentication code"
  2. Call: list_file_symbols(file_path="backend/auth.py")
  3. Get: [login (FUNCTION) lines 10-25, verify_password (FUNCTION) lines 27-40, ...]
  4. Call: read_file(file_path="backend/auth.py", start_line=10, end_line=25)  ← Read only login function!
**❌ DO NOT:** Use read_file to fetch entire files blindly
**✓ DO:** Use list_file_symbols first to see what's available, then read specific sections!

### 4. analyze_relationships(query: string)
**Purpose:** Find components related to a symbol or concept.
**Returns:** Functions/classes that call, depend on, or relate to the query.
**When to use:** After understanding one piece, find connected components.
**Example workflow:**
  1. Understood authentication in auth.py
  2. Call: analyze_relationships(query="authenticate")
  3. Get: [verify_password, hash_password, login_handler, ...]
  4. Then: read_file on interesting related components

## RECOMMENDED WORKFLOW (Efficient - Minimal Calls!)

**Step 1: Broad Search with Multiple Related Terms (1 call)**
```json
{"action": "tool_call", "tool_name": "search_symbols", "arguments": {"query": "auth,authenticate,login,token,jwt,verify"}}
```
↓ Gets back: All files matching ANY of these terms (grouped by query)

**Step 2: List Symbols in Top Files (1-2 calls)**
```json
{"action": "tool_call", "tool_name": "list_file_symbols", "arguments": {"file_path": "backend/auth.py"}}
```
↓ Gets back: All functions/classes with line numbers

**Step 3: Read Specific Sections Only (1-2 calls)**
```json
{"action": "tool_call", "tool_name": "read_file", "arguments": {"file_path": "backend/auth.py", "start_line": 10, "end_line": 50}}
```
↓ Gets back: Only the relevant code section

**Step 4: Complete (1 call)**
✓ Synthesize and answer

**Total calls: 4-6 (instead of 20+ with repeated searches!)**

⚠️ ANTI-PATTERN (Inefficient - Many Back-and-Forth Calls):
   search_symbols("auth") → search_symbols("authenticate") → search_symbols("login")
   → read_file(entire file) → search_symbols("token") → ...
   → Eventually hit iteration limit with no complete answer

✓ PATTERN (EFFICIENT - Minimal Calls):
   search_symbols("auth,authenticate,login,token,jwt") → list_file_symbols → read_file(lines X-Y) → complete"""

            # Build conversation with tool loop
            messages = [
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=request.query),
            ]

            max_iterations = 10  # Increased for more thorough exploration
            iteration = 0
            final_answer = None
            attempted_calls = []  # Track what we've already tried
            total_tokens_used = 0  # Track token usage

            # Initialize Qwen tokenizer for accurate token counting
            try:
                from qwen_tokenizer import QwenTokenizer
                tokenizer = QwenTokenizer()
                logger.info("[TOKENS] Using Qwen tokenizer for accurate token counting")
            except Exception as e:
                logger.warning(f"[TOKENS] Failed to load Qwen tokenizer: {e}, falling back to estimation")
                tokenizer = None

            def count_tokens(text):
                """Count tokens using Qwen tokenizer or estimation fallback"""
                if tokenizer:
                    try:
                        return len(tokenizer.encode(text))
                    except:
                        pass
                # Fallback: ~1 token per 4 characters
                return max(1, len(text.encode('utf-8')) // 4)

            # Count system prompt tokens
            system_prompt_tokens = count_tokens(system_prompt)
            total_tokens_used += system_prompt_tokens
            logger.info(f"[TOKENS] System prompt: {system_prompt_tokens} tokens (using {'Qwen tokenizer' if tokenizer else 'estimation'})")

            # 5. Tool-calling loop
            while iteration < max_iterations:
                iteration += 1

                # If we have attempted calls, remind LLM what NOT to repeat
                if attempted_calls:
                    attempted_summary = "\n".join([f"- {call}" for call in attempted_calls[-5:]])  # Last 5 attempts
                    messages.append(
                        Message(
                            role=MessageRole.USER,
                            content=f"IMPORTANT: You've already tried these calls, DO NOT REPEAT them:\n{attempted_summary}\n\nTry a DIFFERENT approach: different search terms, different files, or a different tool."
                        )
                    )

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

                # Count tokens for this request/response
                request_tokens = sum(count_tokens(msg.content) for msg in messages[-3:])  # Last 3 messages
                response_tokens = count_tokens(response_text)

                total_tokens_used += request_tokens + response_tokens
                logger.info(f"[TOKENS] Iteration {iteration}: request={request_tokens}, response={response_tokens}, cumulative={total_tokens_used}")

                # Parse JSON response
                try:
                    # Try to extract JSON from markdown code fences if present
                    if "```json" in response_text:
                        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
                        if json_match:
                            response_text = json_match.group(1).strip()

                    action_data = json.loads(response_text)
                    # Debug: Log what LLM decided to do
                    action = action_data.get("action", "unknown")
                    if action == "tool_call":
                        tool_name = action_data.get("tool_name", "unknown")
                        arguments = action_data.get("arguments", {})
                        logger.info(f"[LLM_DECISION] Iteration {iteration}: tool={tool_name}, args={arguments}")
                    elif action == "complete":
                        logger.info(f"[LLM_DECISION] Iteration {iteration}: action=complete (answer ready)")
                    else:
                        logger.info(f"[LLM_DECISION] Iteration {iteration}: action={action} (malformed)")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse LLM JSON response. Raw: {response_text[:200]}")

                    # If response looks like a final answer (not a tool call), treat it as completion
                    if len(response_text) > 50 and not "tool_name" in response_text.lower():
                        logger.info("LLM provided non-JSON response, treating as final answer")
                        final_answer = response_text
                        break
                    else:
                        # Only break if it's a short response or looks malformed
                        logger.warning(f"Invalid JSON and not a complete answer. Error: {e}")
                        # Try one more time with a clearer instruction
                        messages.append(
                            Message(role=MessageRole.USER, content="Your previous response was not in valid JSON format. Please respond with ONLY a JSON object like this: {\"action\": \"complete\", \"content\": \"your answer here\"}")
                        )
                        continue  # Try again instead of breaking

                # Handle actions
                if action_data.get("action") == "complete":
                    # LLM is done
                    final_answer = action_data.get("content", "No answer provided")
                    break

                elif action_data.get("action") == "tool_call":
                    # Execute tool
                    tool_name = action_data.get("tool_name", "")
                    arguments = action_data.get("arguments", {})

                    # Track this attempt
                    if tool_name == "search_symbols":
                        call_desc = f'search_symbols("{arguments.get("query", "")}")'
                    elif tool_name == "read_file":
                        call_desc = f'read_file("{arguments.get("file_path", "")}")'
                    else:
                        call_desc = f'{tool_name}({arguments})'

                    attempted_calls.append(call_desc)

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
                        elif tool_name == "list_file_symbols":
                            tool_result = await execute_list_file_symbols(
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
                synthesis_prompt = f"""Based on all the information gathered, provide a final comprehensive answer to the user's original question: "{request.query}"

Instructions:
- Synthesize findings from the tool results above
- Format as clear, readable markdown
- Include key findings with bullet points if relevant
- Keep the answer focused and practical"""
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

                    # Clean up the response if it contains JSON formatting
                    if final_answer.startswith('{'):
                        try:
                            data = json.loads(final_answer)
                            final_answer = data.get('content', final_answer)
                        except:
                            pass  # Keep original if not JSON

                except Exception as e:
                    logger.warning(f"Failed to generate synthesis: {e}")
                    final_answer = f"Analysis complete based on {iteration - 1} tool explorations. See tool results above for detailed findings about: {request.query}"

            # 6. Stream final answer
            elapsed = (datetime.now() - start_time).total_seconds()
            yield f"data: {json.dumps({'type': 'final-answer', 'content': final_answer, 'timestamp': elapsed})}\n\n"

            # 7. Stream completion metadata
            # Add synthesis prompt tokens if we did synthesis
            if "Based on all the information gathered" in str(messages):
                synthesis_tokens = len("Based on all the information gathered, provide a final comprehensive answer") // 4
                total_tokens_used += synthesis_tokens

            yield f"data: {json.dumps({'type': 'completed', 'model_used': model, 'total_tokens': total_tokens_used, 'tool_calls_count': iteration - 1, 'elapsed_seconds': elapsed})}\n\n"

        except Exception as e:
            logger.error(f"Error analyzing repository: {e}", exc_info=True)
            error_message = format_error_message(e)
            yield f"data: {json.dumps({'type': 'error', 'content': error_message})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
