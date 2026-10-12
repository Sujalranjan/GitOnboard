"""
Baseline execution runners for benchmark arms:
- Arm 0: Model Prior (Direct question -> LLM, no tools, no retrieval)
- Arm 1: Conventional RAG (Single-turn top-K chunk retrieval -> LLM context prompt)
- Arm 2: GitOnboard Retrieval-Only (GitOnboard HybridRetriever top-K evidence -> LLM context prompt, no agent tools)
"""
from __future__ import annotations
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.ai.service import LLMService, get_llm_service
from backend.ai.schemas import LLMRequest, Message, MessageRole
from backend.evaluation.schemas import ExperimentalArm, QuestionBenchmarkSpec, TrajectoryTurn
from backend.repository_tools.tools import RepositoryToolLayer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Arm 0: Model Prior
# ─────────────────────────────────────────────────────────────────────────────

async def run_model_prior(
    spec: QuestionBenchmarkSpec,
    llm_service: Optional[LLMService] = None,
    temperature: float = 0.0,
) -> Tuple[str, List[TrajectoryTurn], List[str], str, float, int, int]:
    """
    Direct single-shot query without external repository retrieval or tools.
    Measures the model's pre-training knowledge and priors.
    """
    service = llm_service or get_llm_service()
    t0 = time.perf_counter()

    prompt = (
        f"You are an expert software engineer answering questions about the repository '{spec.repository}'.\n\n"
        f"Question: {spec.question}\n\n"
        "Provide a precise, technical answer detailing exact files, functions, architectures, and data flows."
    )

    request = LLMRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a precise codebase expert."),
            Message(role=MessageRole.USER, content=prompt),
        ],
        temperature=temperature,
        max_tokens=4096,
    )

    response = await service.generate(request)
    duration_ms = (time.perf_counter() - t0) * 1000

    prompt_toks = response.usage.prompt_tokens if response.usage else 0
    comp_toks = response.usage.completion_tokens if response.usage else 0

    turn = TrajectoryTurn(
        turn_index=0,
        tool_name=None,
        observation_preview="Direct LLM answer (no tools)",
        prompt_tokens=prompt_toks,
        completion_tokens=comp_toks,
        duration_ms=round(duration_ms, 2),
    )

    return (
        response.content,
        [turn],
        [],  # Zero retrieved files
        response.model or "unknown",
        round(duration_ms, 2),
        prompt_toks,
        comp_toks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Arm 1: Conventional RAG (Single-Turn Top-K Chunk Retrieval)
# ─────────────────────────────────────────────────────────────────────────────

CONVENTIONAL_RAG_PROMPT = """You are answering a question about the repository '{repository}' using only the retrieved code snippets below.

Retrieved Context Chunks:
==================================================
{context_chunks}
==================================================

Question: {question}

Instructions:
1. Ground your answer in the provided code snippets.
2. If the context does not contain sufficient information, state what is missing.
3. Be technically specific: cite files, functions, and data flows.
"""

async def run_conventional_rag(
    spec: QuestionBenchmarkSpec,
    tool_layer: RepositoryToolLayer,
    llm_service: Optional[LLMService] = None,
    top_k: int = 5,
    temperature: float = 0.0,
) -> Tuple[str, List[TrajectoryTurn], List[str], str, float, int, int]:
    """
    Single-turn Conventional RAG:
    1. Executes ONE single retrieval query over the repository corpus to fetch top-K chunks.
    2. Packages retrieved chunks into a standard RAG prompt template.
    3. Invokes LLM in a single turn (no iterative searching, reading, or tool use).
    """
    service = llm_service or get_llm_service()
    t0 = time.perf_counter()

    # ONE single retrieval operation
    t_search = time.perf_counter()
    search_res = tool_layer.search_repository(query=spec.question, limit=top_k)
    search_duration = (time.perf_counter() - t_search) * 1000

    retrieved_files: List[str] = []
    chunk_texts: List[str] = []

    if isinstance(search_res, list):
        matches = search_res
    elif isinstance(search_res, dict):
        matches = search_res.get("matches", [])
    else:
        matches = []

    for item in matches[:top_k]:
        f_path = item.get("file") or item.get("path") or ""
        sym = item.get("symbol") or ""
        snip = item.get("snippet") or item.get("content") or ""
        if f_path:
            retrieved_files.append(f_path)
            if snip:
                chunk_texts.append(f"--- File: {f_path} (Symbol: {sym}) ---\n{snip}\n")

    # If search didn't yield text snippets, read the top file slices
    if not chunk_texts and retrieved_files:
        for f in retrieved_files[:top_k]:
            read_res = tool_layer.read_file(f, start_line=1, end_line=100)
            content = read_res.get("content") or read_res.get("raw_text") or ""
            chunk_texts.append(f"--- File: {f} (lines 1-100) ---\n{content[:2000]}\n")

    context_str = "\n".join(chunk_texts) if chunk_texts else "No matching code snippets retrieved."

    user_prompt = CONVENTIONAL_RAG_PROMPT.format(
        repository=spec.repository,
        context_chunks=context_str,
        question=spec.question,
    )

    request = LLMRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a code QA assistant operating over retrieved context chunks."),
            Message(role=MessageRole.USER, content=user_prompt),
        ],
        temperature=temperature,
        max_tokens=4096,
    )

    response = await service.generate(request)
    total_duration = (time.perf_counter() - t0) * 1000

    prompt_toks = response.usage.prompt_tokens if response.usage else 0
    comp_toks = response.usage.completion_tokens if response.usage else 0

    turn = TrajectoryTurn(
        turn_index=0,
        tool_name="single_turn_retrieval",
        arguments={"query": spec.question, "top_k": top_k},
        observation_preview=f"Retrieved {len(retrieved_files)} files: {', '.join(retrieved_files[:3])}",
        prompt_tokens=prompt_toks,
        completion_tokens=comp_toks,
        duration_ms=round(total_duration, 2),
    )

    return (
        response.content,
        [turn],
        retrieved_files,
        response.model or "unknown",
        round(total_duration, 2),
        prompt_toks,
        comp_toks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Arm 2: GitOnboard Retrieval-Only (Ablation Arm)
# ─────────────────────────────────────────────────────────────────────────────

async def run_gitonboard_rag(
    spec: QuestionBenchmarkSpec,
    tool_layer: RepositoryToolLayer,
    llm_service: Optional[LLMService] = None,
    top_k: int = 5,
    temperature: float = 0.0,
) -> Tuple[str, List[TrajectoryTurn], List[str], str, float, int, int]:
    """
    Arm 2 (Ablation): GitOnboard HybridRetriever top-K evidence chunks -> LLM.
    Uses GitOnboard's hybrid retriever (exact symbol + BM25 + dense semantic + FactStore expansion),
    but WITHOUT the iterative multi-turn agent loop, graph traversal tool, or verification passes.
    """
    service = llm_service or get_llm_service()
    t0 = time.perf_counter()

    retrieved_files: List[str] = []
    chunk_texts: List[str] = []

    # Use HybridRetriever if available on tool_layer
    retriever = getattr(tool_layer, "_retriever", None)
    if retriever is None and hasattr(tool_layer, "db") and tool_layer.db is not None and tool_layer.analysis_id:
        from backend.intelligence.retrieval import HybridRetriever
        try:
            retriever = HybridRetriever(db=tool_layer.db, analysis_id=tool_layer.analysis_id)
        except Exception as e:
            logger.warning(f"Could not initialize HybridRetriever for Arm 2: {e}")

    if retriever is not None:
        try:
            results = retriever.retrieve(query=spec.question, top_k=top_k)
            for res in results[:top_k]:
                f_path = getattr(res, "file_path", None) or getattr(res, "path", "")
                if f_path:
                    retrieved_files.append(f_path)
                    read_res = tool_layer.read_file(f_path, start_line=1, end_line=120)
                    content = read_res.get("content") or read_res.get("raw_text") or ""
                    chunk_texts.append(f"--- File: {f_path} ---\n{content[:2500]}\n")
        except Exception as e:
            logger.warning(f"Arm 2 hybrid retrieval error ({e}), falling back to search_repository.")

    if not chunk_texts:
        # Fallback to repository tool layer multi-search
        s_res = tool_layer.search_repository(query=spec.question, limit=top_k)
        if isinstance(s_res, list):
            s_matches = s_res
        elif isinstance(s_res, dict):
            s_matches = s_res.get("matches", [])
        else:
            s_matches = []

        for item in s_matches[:top_k]:
            f = item.get("file") or item.get("path")
            if f:
                retrieved_files.append(f)
                read_res = tool_layer.read_file(f, start_line=1, end_line=100)
                content = read_res.get("content") or read_res.get("raw_text") or ""
                chunk_texts.append(f"--- File: {f} ---\n{content[:2000]}\n")

    context_str = "\n".join(chunk_texts) if chunk_texts else "No matching code snippets retrieved."

    user_prompt = CONVENTIONAL_RAG_PROMPT.format(
        repository=spec.repository,
        context_chunks=context_str,
        question=spec.question,
    )

    request = LLMRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a code QA assistant evaluating GitOnboard hybrid retrieval."),
            Message(role=MessageRole.USER, content=user_prompt),
        ],
        temperature=temperature,
        max_tokens=4096,
    )

    response = await service.generate(request)
    total_duration = (time.perf_counter() - t0) * 1000

    prompt_toks = response.usage.prompt_tokens if response.usage else 0
    comp_toks = response.usage.completion_tokens if response.usage else 0

    turn = TrajectoryTurn(
        turn_index=0,
        tool_name="gitonboard_hybrid_retrieval",
        arguments={"query": spec.question, "top_k": top_k},
        observation_preview=f"Hybrid retrieved {len(retrieved_files)} files: {', '.join(retrieved_files[:3])}",
        prompt_tokens=prompt_toks,
        completion_tokens=comp_toks,
        duration_ms=round(total_duration, 2),
    )

    return (
        response.content,
        [turn],
        retrieved_files,
        response.model or "unknown",
        round(total_duration, 2),
        prompt_toks,
        comp_toks,
    )
