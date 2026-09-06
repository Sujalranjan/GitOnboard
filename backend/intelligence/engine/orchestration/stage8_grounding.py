"""
Stage 8: LLM Integration & Grounding Validation

Phase 2M implementation: Interactive research with Phase 2L tools.
- Creates compact initial context (no source code)
- LLM requests what to inspect via Phase 2L tools
- ContextManager tracks dynamic context additions
- Research events emitted for observability
- Final answer grounded against inspected evidence
"""
import logging
import asyncio
import re
import json
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass
from datetime import datetime

from backend.ai.service import get_llm_service
from backend.ai.schemas import LLMRequest, Message, MessageRole
from backend.agent.context.contracts import RepositoryContext, ContextEvidence, ContextBudget
from backend.intelligence.context_management.manager import ContextManager
from backend.intelligence.context_management.models import ContextItemPriority
from backend.intelligence.engine.orchestration.stage8_phase2l_adapter import (
    Phase2LToolWrapper,
    ExecutionContext,
    ResearchEvent,
    ResearchEventType,
)

logger = logging.getLogger(__name__)


@dataclass
class GroundingValidationResult:
    """Result from grounding validation."""
    query: str
    answer: str
    grounded_entities: List[str]
    grounding_status: str  # "grounded", "partial", "ungrounded", "insufficient_context"
    validation_errors: List[str]
    evidence_size_kb: float
    llm_latency: float


class GroundingValidator:
    """Validates that LLM answers are grounded in provided repository evidence."""

    def __init__(self, context: RepositoryContext):
        self.context = context
        self.file_names = set(context.relevant_files or [])
        self.symbol_names = set()
        self.entity_names = set()

        # Extract entity names from context
        if context.relevant_symbols:
            for sym in context.relevant_symbols:
                if isinstance(sym, dict):
                    self.symbol_names.add(sym.get("name", ""))
                    self.symbol_names.add(sym.get("full_name", ""))

        if context.evidence:
            for evidence in context.evidence:
                # Handle both dict and ContextEvidence object formats
                source_id = evidence.get("source_id") if isinstance(evidence, dict) else getattr(evidence, "source_id", None)
                summary = evidence.get("summary") if isinstance(evidence, dict) else getattr(evidence, "summary", None)

                if source_id:
                    self.entity_names.add(source_id)
                if summary:
                    # Extract entity names from summary
                    words = summary.split()
                    for word in words:
                        if len(word) > 3 and word.isidentifier():
                            self.entity_names.add(word)

    def validate(self, answer: str) -> GroundingValidationResult:
        """
        Validate that answer references entities from provided context.

        Strategy:
        1. Extract file paths/symbols from answer using regex
        2. Check if extracted entities exist in context
        3. Classify grounding status

        Args:
            answer: LLM-generated answer

        Returns:
            GroundingValidationResult
        """
        # Extract potential file paths (heuristic: path-like strings with / or \)
        extracted_files = re.findall(r'[\w\-./\\]+\.[\w]+', answer)
        extracted_files = [f for f in extracted_files if '/' in f or '\\' in f]
        extracted_files = [f.replace('\\', '/') for f in extracted_files]

        # Extract potential symbol/function/class names (capitalized or snake_case)
        extracted_symbols = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b|\b[a-z_][a-z0-9_]*\([^)]*\)\b', answer)

        # Check grounding
        grounded_files = [f for f in extracted_files if f in self.file_names]
        grounded_symbols = [s for s in extracted_symbols if s in self.symbol_names or s in self.entity_names]

        grounded_entities = grounded_files + grounded_symbols
        errors = []

        # Determine grounding status
        if not self.context.evidence or len(self.context.evidence) < 2:
            status = "insufficient_context"
            errors.append("Context has no or minimal evidence")
        elif not extracted_files and not extracted_symbols:
            status = "ungrounded"
            errors.append("Answer contains no repository-specific references")
        elif len(grounded_entities) > 0:
            if len(grounded_entities) >= len(set(extracted_files + extracted_symbols)):
                status = "grounded"
            else:
                status = "partial"
                errors.append(f"Some references not grounded: {set(extracted_files + extracted_symbols) - set(grounded_entities)}")
        else:
            status = "ungrounded"
            errors.append("Extracted entities not found in provided context")

        return GroundingValidationResult(
            query=self.context.requirement,
            answer=answer,
            grounded_entities=grounded_entities,
            grounding_status=status,
            validation_errors=errors,
            evidence_size_kb=len(str(self.context.evidence)) / 1024 if self.context.evidence else 0.0,
            llm_latency=0.0,  # Set by caller
        )


class LLMGrounder:
    """
    Stage 8: Interactive research with Phase 2L tools.

    Phase 2M implementation:
    - Creates compact initial context (metadata only, no source)
    - LLM uses Phase 2L tools to inspect what it needs
    - ContextManager tracks dynamic context additions
    - Research events emitted for observability
    - Final answer grounded against inspected evidence
    """

    def __init__(self):
        self.llm_service = get_llm_service()

    def _create_compact_context(self, context: RepositoryContext) -> RepositoryContext:
        """
        Strip source_excerpt items from context.

        Returns compact context with only metadata.
        LLM must use tools to inspect actual source.
        """
        if not context.evidence:
            return context

        # Filter out source_excerpt items (these have actual code)
        # Keep structural/relationship metadata
        compact_evidence = [
            e for e in context.evidence
            if e.source_type != "source_excerpt"
        ]

        # Create new context with compact evidence
        return RepositoryContext(
            requirement=context.requirement,
            relevant_files=context.relevant_files,
            relevant_symbols=context.relevant_symbols,
            evidence=compact_evidence,
            # Copy other fields as-is
            **{k: v for k, v in context.__dict__.items()
               if k not in ["requirement", "relevant_files", "relevant_symbols", "evidence"]}
        )

    @staticmethod
    def _extract_json_from_response(response: str) -> str:
        """
        Extract JSON from model response.

        Handles both:
        - Plain JSON: {"tool": "...", "parameters": {...}}
        - Markdown-wrapped JSON: ```json {...} ```

        Args:
            response: Raw model response

        Returns:
            JSON string ready for parsing
        """
        # Check if response is wrapped in markdown code fences
        import re
        # Pattern: ```json\n...\n``` or ```\n...\n```
        fence_pattern = r"^```(?:json)?\s*\n(.*?)\n```\s*$"
        match = re.search(fence_pattern, response.strip(), re.DOTALL)

        if match:
            # Extract JSON from inside fences
            return match.group(1).strip()
        else:
            # Return as-is for plain JSON
            return response.strip()

    def _get_tool_descriptions(self) -> str:
        """Get descriptions of available Phase 2L tools for LLM prompt."""
        return """
## Available Research Tools

You have access to the following tools to inspect the repository:

### 1. inspect_file(file_path: str)
Inspect file structure without reading full source.
Returns: language, line count, symbols/functions/classes
Use this FIRST to understand what's in a file.

### 2. read_symbol(file_path: str, symbol_name: str)
Read exact source code for one symbol (function, class, method).
Returns: numbered source lines, line boundaries
Use this to read specific functions/classes you need.

### 3. read_lines(file_path: str, start_line: int, end_line: int)
Read specific lines from a file.
Returns: source code for the line range
Use this to read specific sections.

### 4. read_file(file_path: str)
Read entire file (expensive, use only for small files).
Use sparingly for small, critical files.

### 5. get_context_status()
Check current context utilization and budget status.
Use this to monitor context pressure.

### 6. list_context()
List all evidence currently collected.
Use this to see what you've already inspected.

## Tool Usage Pattern

To use a tool, format your response as follows in JSON:
```
{
  "thought": "What I'm trying to understand",
  "tool": "tool_name",
  "parameters": {
    "file_path": "...",
    "symbol_name": "..." // if applicable
  }
}
```

When you have enough information to answer, respond with:
```
{
  "thought": "I have enough information",
  "final_answer": "Your detailed answer here, citing specific files and symbols"
}
```
"""

    async def _run_research_loop(
        self,
        query: str,
        initial_context: RepositoryContext,
        tool_wrapper: Phase2LToolWrapper,
        max_iterations: int = 10,
    ) -> tuple[str, List[ResearchEvent]]:
        """
        Research loop: LLM decides what to inspect, we run tools, loop.

        Args:
            query: User's research question
            initial_context: Compact repository context (metadata only)
            tool_wrapper: Phase 2L tool wrapper
            max_iterations: Max tool calls before forcing answer

        Returns:
            (final_answer: str, research_events: List[ResearchEvent])
        """
        messages: List[Message] = [
            Message(
                role=MessageRole.SYSTEM,
                content="""You are a code researcher with access to repository inspection tools.

Your goal is to thoroughly investigate the repository to answer the user's question.

IMPORTANT RESEARCH STRATEGY:
1. Start by understanding the overall structure using inspect_file()
2. Identify relevant symbols and functions
3. Read their source to understand implementation
4. Follow function calls and relationships to build complete understanding
5. When you have enough information, provide a comprehensive answer

RULES:
- Use tools to inspect repository - do NOT make assumptions
- Cite specific file paths and symbol names from your inspections
- If you cannot find information after reasonable investigation, say so clearly
- Be thorough but efficient - avoid redundant inspections
- Stop when you have answered the question fully"""
            ),
            Message(
                role=MessageRole.USER,
                content=f"""Repository Context (metadata only):
{json.dumps(initial_context.model_dump(), indent=2)}

{self._get_tool_descriptions()}

Question: {query}

Investigate the repository using the available tools. Start by exploring the relevant files, then read specific symbols as needed. When you have sufficient information, provide a complete answer."""
            )
        ]

        tool_wrapper._emit_event(
            ResearchEventType.RESEARCH_STARTED,
            "research",
            f"Starting interactive research for query: {query}",
            {"query": query, "initial_files": len(initial_context.relevant_files or [])},
        )

        for iteration in range(max_iterations):
            logger.info(f"\n[Research Loop] Iteration {iteration + 1}/{max_iterations}")

            # Call LLM for next action
            try:
                request = LLMRequest(
                    messages=messages,
                    temperature=0.1,  # More deterministic for tool use
                    max_tokens=2048,
                )

                response = await self.llm_service.generate(request)
                llm_response = response.content

                logger.info(f"[Research Loop] LLM response: {llm_response[:500]}...")

            except Exception as e:
                logger.error(f"[Research Loop] LLM call failed: {e}")
                tool_wrapper._emit_event(
                    ResearchEventType.TOOL_ERROR,
                    "llm",
                    f"LLM call failed: {str(e)}",
                    {"error": str(e)},
                )
                raise

            # Parse LLM response - look for tool calls or final answer
            try:
                # Extract JSON from response (handles markdown-wrapped JSON)
                json_str = self._extract_json_from_response(llm_response)
                # Try to parse as JSON
                parsed = json.loads(json_str)
                if "final_answer" in parsed:
                    # LLM has decided to answer
                    final_answer = parsed["final_answer"]
                    logger.info(f"[Research Loop] LLM reached final answer at iteration {iteration + 1}")

                    tool_wrapper._emit_event(
                        ResearchEventType.LLM_RESPONSE,
                        "llm",
                        "LLM provided final answer",
                        {"iterations": iteration + 1},
                    )

                    # Add final answer to messages
                    messages.append(Message(
                        role=MessageRole.ASSISTANT,
                        content=llm_response,
                    ))

                    return final_answer, tool_wrapper.events

                elif "tool" in parsed:
                    # LLM wants to call a tool
                    tool_name = parsed.get("tool")
                    parameters = parsed.get("parameters", {})
                    thought = parsed.get("thought", "")

                    logger.info(f"[Research Loop] LLM requesting tool: {tool_name} with params: {parameters}")

                    # Execute tool
                    if tool_name == "inspect_file":
                        tool_result = tool_wrapper.inspect_file_tool(parameters.get("file_path", ""))
                    elif tool_name == "read_symbol":
                        tool_result = tool_wrapper.read_symbol_tool(
                            parameters.get("file_path", ""),
                            parameters.get("symbol_name", ""),
                        )
                    elif tool_name == "read_lines":
                        tool_result = tool_wrapper.read_lines_tool(
                            parameters.get("file_path", ""),
                            parameters.get("start_line", 1),
                            parameters.get("end_line", 100),
                        )
                    elif tool_name == "read_file":
                        tool_result = tool_wrapper.read_file_tool(parameters.get("file_path", ""))
                    elif tool_name == "get_context_status":
                        tool_result = tool_wrapper.get_context_status_tool()
                    elif tool_name == "list_context":
                        tool_result = tool_wrapper.list_context_tool()
                    else:
                        tool_result = {
                            "success": False,
                            "error": f"Unknown tool: {tool_name}",
                            "tool": tool_name,
                        }

                    # Add LLM message and tool result to conversation
                    messages.append(Message(
                        role=MessageRole.ASSISTANT,
                        content=llm_response,
                    ))
                    messages.append(Message(
                        role=MessageRole.TOOL,
                        content=json.dumps(tool_result),
                    ))

                    tool_wrapper._emit_event(
                        ResearchEventType.TOOL_INVOKED,
                        "research",
                        f"LLM called {tool_name}",
                        {
                            "tool": tool_name,
                            "parameters": parameters,
                            "success": tool_result.get("success", False),
                            "iteration": iteration + 1,
                        },
                    )

                else:
                    # Malformed response, ask for tool call
                    messages.append(Message(
                        role=MessageRole.ASSISTANT,
                        content=llm_response,
                    ))
                    messages.append(Message(
                        role=MessageRole.TOOL,
                        content=json.dumps({
                            "error": "Response must be JSON with either 'tool' or 'final_answer' field"
                        }),
                    ))

            except json.JSONDecodeError:
                # Response wasn't JSON, treat as malformed tool request
                logger.warning(f"[Research Loop] LLM response was not JSON: {llm_response[:200]}")
                messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=llm_response,
                ))
                messages.append(Message(
                    role=MessageRole.TOOL,
                    content=json.dumps({
                        "error": "Please respond with valid JSON containing either 'tool' (with name and parameters) or 'final_answer'"
                    }),
                ))

        # Max iterations reached - force answer from what we have
        logger.warning(f"[Research Loop] Reached max iterations ({max_iterations}), forcing answer")

        tool_wrapper._emit_event(
            ResearchEventType.RESEARCH_COMPLETED,
            "research",
            "Max iterations reached, generating final answer",
            {"iterations": max_iterations},
        )

        # Make one final call to get answer
        messages.append(Message(
            role=MessageRole.USER,
            content="You have reached the maximum number of investigations. Please provide your final answer based on what you have learned.",
        ))

        try:
            request = LLMRequest(
                messages=messages,
                temperature=0.2,
                max_tokens=2048,
            )
            response = await self.llm_service.generate(request)
            return response.content, tool_wrapper.events
        except Exception as e:
            logger.error(f"[Research Loop] Final answer call failed: {e}")
            return f"Research failed to complete: {str(e)}", tool_wrapper.events

    async def ground_interactive(
        self,
        context: RepositoryContext,
        query: str,
        execution_context: ExecutionContext,  # REQUIRED
    ) -> tuple[str, GroundingValidationResult, List[ResearchEvent]]:
        """
        Phase 2M Interactive research with Phase 2L tools.

        CRITICAL: execution_context is MANDATORY.

        If execution_context is None:
        - DO NOT fall back to bulk context
        - Return explicit REPOSITORY_CONTEXT_ERROR

        Phase 2M is NOT backward compatible with bulk context mode.

        Args:
            context: RepositoryContext from Stage 7
            query: Original user query
            execution_context: ExecutionContext with analysis_id, repo_root, db (REQUIRED)

        Returns:
            (answer: str, grounding_result: GroundingValidationResult, events: List[ResearchEvent])

        Raises:
            ValueError: If execution_context is missing or invalid
        """
        if not execution_context:
            error_msg = (
                "REPOSITORY_CONTEXT_ERROR: Phase 2M interactive research requires execution_context. "
                "execution_context must contain: analysis_id (int), repo_root (str), db (Session). "
                "Phase 2M is NOT backward compatible with bulk-context mode. "
                "Use ground_legacy() for bulk-context queries."
            )
            logger.error(f"[Stage 8 Interactive] {error_msg}")
            raise ValueError(error_msg)

        if not execution_context.analysis_id:
            raise ValueError("REPOSITORY_CONTEXT_ERROR: execution_context.analysis_id is required")
        if not execution_context.repo_root:
            raise ValueError("REPOSITORY_CONTEXT_ERROR: execution_context.repo_root is required")
        if not execution_context.db:
            raise ValueError("REPOSITORY_CONTEXT_ERROR: execution_context.db is required")

        import time
        start_time = time.time()

        logger.info(f"\n[Stage 8 - Phase 2M Interactive] RECEIVED CONTEXT FROM STAGE 7:")
        logger.info(f"  Relevant files: {len(context.relevant_files or [])} - {context.relevant_files[:3]}")
        logger.info(f"  Relevant symbols: {len(context.relevant_symbols or [])}")
        logger.info(f"  Evidence items: {len(context.evidence or [])}")

        # Create compact context (strip source)
        compact_context = self._create_compact_context(context)
        original_size = len(context.model_dump_json())
        compact_size = len(compact_context.model_dump_json())
        logger.info(f"\n[Stage 8 - Phase 2M Interactive] CONTEXT COMPACTION:")
        logger.info(f"  Original size: {original_size/1024:.1f}KB")
        logger.info(f"  Compact size: {compact_size/1024:.1f}KB")
        logger.info(f"  Reduction: {((original_size - compact_size) / original_size * 100):.1f}%")

        # Initialize Phase 2L tools (no fallback option)
        context_manager = ContextManager(
            budget=ContextBudget(max_tokens=100000, current_tokens=compact_size),
        )
        tool_wrapper = Phase2LToolWrapper(execution_context, context_manager)

        logger.info(f"[Stage 8 - Phase 2M Interactive] Phase 2L tools initialized:")
        logger.info(f"  analysis_id: {execution_context.analysis_id}")
        logger.info(f"  repo_root: {execution_context.repo_root}")

        # Run interactive research loop
        answer, research_events = await self._run_research_loop(
            query,
            compact_context,
            tool_wrapper,
            max_iterations=10,
        )

        llm_latency = time.time() - start_time

        # Validate grounding against ALL collected evidence
        final_context = compact_context
        collected_items = context_manager.list_context()
        for item in collected_items:
            # item is already a ContextEvidence object (inherits from ContextItem which inherits from ContextEvidence)
            # Only append if it has actual content data
            if item.data and isinstance(item.data, dict) and item.data.get("content"):
                final_context.evidence.append(item)

        validator = GroundingValidator(final_context)
        grounding_result = validator.validate(answer)
        grounding_result.llm_latency = llm_latency

        logger.info(
            f"[Stage 8 - Phase 2M Interactive] Research complete: {len(answer)} chars, "
            f"grounding={grounding_result.grounding_status}, "
            f"latency={llm_latency:.2f}s"
        )

        tool_wrapper._emit_event(
            ResearchEventType.GROUNDING_VALIDATED,
            "grounding",
            f"Answer grounding: {grounding_result.grounding_status}",
            {
                "grounding_status": grounding_result.grounding_status,
                "grounded_entities": len(grounding_result.grounded_entities),
            },
        )

        return answer, grounding_result, research_events

    async def ground_legacy(
        self,
        context: RepositoryContext,
        query: str,
    ) -> tuple[str, GroundingValidationResult]:
        """
        Legacy bulk-context mode (backward compatibility only).

        This is the OLD Stage 8 behavior:
        - Full RepositoryContext sent to LLM
        - No interactive tool calling
        - No research events
        - Simple grounding validation

        DEPRECATED: Use ground_interactive() for new code.

        Args:
            context: RepositoryContext from Stage 7
            query: Original user query

        Returns:
            (answer: str, grounding_result: GroundingValidationResult)
        """
        import time
        start_time = time.time()

        logger.warning("[Stage 8 Legacy] Using deprecated bulk-context mode. Consider using ground_interactive().")

        context_json = context.model_dump_json(indent=2)
        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content="""You are a code analyst with access to repository structure.

IMPORTANT:
1. Answer ONLY using the provided repository context.
2. If information is not in the context, say "This information is not available in the provided context."
3. Cite specific file paths and symbol names from the context when possible.
4. Do not make assumptions about code you have not seen.
5. Be concise and precise."""
            ),
            Message(
                role=MessageRole.USER,
                content=f"""Repository Context (from retrieval + graph traversal):
{context_json}

Question: {query}

Answer based ONLY on the provided context. Cite specific files and symbols."""
            )
        ]

        try:
            request = LLMRequest(
                messages=messages,
                temperature=0.2,
                max_tokens=1024,
            )
            response = await self.llm_service.generate(request)
            answer = response.content
        except Exception as e:
            logger.error(f"[Stage 8 Legacy] LLMService failed: {e}")
            raise

        llm_latency = time.time() - start_time

        # Validate grounding
        validator = GroundingValidator(context)
        grounding_result = validator.validate(answer)
        grounding_result.llm_latency = llm_latency

        logger.info(
            f"[Stage 8 Legacy] Answer: {len(answer)} chars, "
            f"grounding={grounding_result.grounding_status}, "
            f"latency={llm_latency:.2f}s"
        )

        return answer, grounding_result


def stage8_sync_wrapper(
    context: RepositoryContext,
    query: str,
    execution_context: Optional[ExecutionContext] = None,
) -> tuple[str, GroundingValidationResult]:
    """
    Synchronous wrapper for Stage 8 (for integration with sync validation scripts).

    DEPRECATED: Use ground_interactive_sync() or ground_legacy_sync() explicitly.

    Args:
        context: RepositoryContext from Stage 7
        query: Original user query
        execution_context: Optional ExecutionContext with analysis_id, repo_root, db

    Returns:
        (answer: str, grounding_result: GroundingValidationResult)
    """
    grounder = LLMGrounder()
    try:
        if execution_context:
            # Phase 2M interactive mode
            answer, grounding, _events = asyncio.run(
                grounder.ground_interactive(context, query, execution_context)
            )
            return answer, grounding
        else:
            # Legacy bulk context mode
            return asyncio.run(grounder.ground_legacy(context, query))
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.warning("[Stage 8] Already in event loop, cannot use asyncio.run()")
            raise
        raise


def stage8_sync_wrapper_interactive(
    context: RepositoryContext,
    query: str,
    execution_context: ExecutionContext,
) -> tuple[str, GroundingValidationResult, List[ResearchEvent]]:
    """
    Synchronous wrapper for Phase 2M interactive research.

    Args:
        context: RepositoryContext from Stage 7
        query: Original user query
        execution_context: ExecutionContext with analysis_id, repo_root, db (REQUIRED)

    Returns:
        (answer: str, grounding_result: GroundingValidationResult, events: List[ResearchEvent])

    Raises:
        ValueError: If execution_context is None or invalid
    """
    grounder = LLMGrounder()
    try:
        return asyncio.run(grounder.ground_interactive(context, query, execution_context))
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.warning("[Stage 8] Already in event loop, cannot use asyncio.run()")
            raise
        raise


def stage8_sync_wrapper_legacy(
    context: RepositoryContext,
    query: str,
) -> tuple[str, GroundingValidationResult]:
    """
    Synchronous wrapper for legacy bulk-context mode.

    DEPRECATED: Consider migrating to ground_interactive_sync().

    Args:
        context: RepositoryContext from Stage 7
        query: Original user query

    Returns:
        (answer: str, grounding_result: GroundingValidationResult)
    """
    grounder = LLMGrounder()
    try:
        return asyncio.run(grounder.ground_legacy(context, query))
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.warning("[Stage 8] Already in event loop, cannot use asyncio.run()")
            raise
        raise
