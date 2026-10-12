"""
Search operations for RepositoryToolLayer (search_code, search_repository, fallback).
Extracted from backend.repository_tools.tools to maintain modularity.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.intelligence.notebook import resolve_source_document
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.models.fact_store import FactFile
from backend.storage import get_storage

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't",
    "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having",
    "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no",
    "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
    "over", "own", "same", "shan't", "she", "should", "shouldn't", "so", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "were", "weren't", "what", "when",
    "where", "which", "while", "who", "whom", "why", "with", "won't", "would", "wouldn't", "you", "your", "yours"
}


def decompose_query(query: str) -> List[str]:
    """
    Decomposes a complex query or natural language question into focused subqueries.
    Handles:
    1. Multi-sentence questions (splits on . ? !)
    2. Comma-separated lists of symbols or topics
    3. Technical identifiers, code symbols, and keyword density
    """
    if not query:
        return []

    # If already a simple comma-separated list of short phrases
    parts = [p.strip() for p in query.split(",") if p.strip()]
    if len(parts) > 1 and all(len(p.split()) <= 4 for p in parts):
        return parts[:8]

    sub_queries: List[str] = []

    # Split by sentence/clause boundaries (. ? ! ;)
    sentences = [s.strip() for s in re.split(r'[.?!;]+', query) if s.strip()]

    for s in sentences:
        words = s.split()
        if not words:
            continue

        if len(words) <= 6:
            sub_queries.append(s)
            continue

        # Extract code/technical terms (snake_case, camelCase, identifiers with underscores/slashes)
        tech_terms = [t.replace("/", " ") for t in re.findall(r'[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)+|[A-Z][a-z]+[A-Z][a-zA-Z]*|[a-z0-9]+_[a-z0-9_]+', s)]
        # Significant keywords (>= 4 chars, skipping stop words)
        sig_words = [w for w in re.findall(r'\b[a-zA-Z_]{4,}\b', s) if w.lower() not in STOP_WORDS]

        # Combine terms to make a rich multi-keyword query
        combined_words = []
        for t in tech_terms:
            combined_words.extend(t.split())
        for w in sig_words:
            if w.lower() not in [cw.lower() for cw in combined_words]:
                combined_words.append(w)

        if combined_words:
            sub_queries.append(" ".join(combined_words[:5]))


    # Deduplicate while preserving order and limit to top 3 focused subqueries
    seen = set()
    deduped = []
    for sq in sub_queries:
        norm = sq.lower().strip()
        if norm and norm not in seen and len(norm) >= 3:
            seen.add(norm)
            deduped.append(sq)
        if len(deduped) >= 3:
            break

    return deduped if deduped else [query]





def search_code_ops(
    tool_layer: Any,
    query: str,
    file_pattern: Optional[str] = None,
    max_matches: int = 25,
    max_files_scanned: int = 40,
) -> List[Dict[str, Any]]:
    """
    Performs lexical regex/substring search over source files in Azure Blob Storage.
    Worktrees are temporary and deleted after indexing; all file content is persisted in blobs.
    """
    try:
        max_matches = int(max_matches) if max_matches else 25
        max_files_scanned = int(max_files_scanned) if max_files_scanned else 40
    except (ValueError, TypeError):
        max_matches = 25
        max_files_scanned = 40

    if not query:
        return []

    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(query), re.IGNORECASE)

    try:
        logger.debug(
            f"[search_code:DIAGNOSTIC] ENTRY query={query!r} repo={tool_layer.repo_name!r} "
            f"db={bool(tool_layer.db)} analysis_id={tool_layer.analysis_id}"
        )
    except Exception:
        pass

    results: List[Dict[str, Any]] = []

    # 1. Local filesystem branch (when repo_root exists)
    if tool_layer.repo_root and tool_layer.repo_root.exists():
        files_scanned = 0
        files_with_matches = 0
        from backend.repository_tools.security import is_binary_file

        for root, dirs, files in os.walk(tool_layer.repo_root):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build"}
            ]
            for file in sorted(files):
                if file_pattern:
                    import fnmatch
                    if not fnmatch.fnmatch(file, file_pattern):
                        continue

                files_scanned += 1
                if files_scanned > max_files_scanned:
                    break

                file_path = Path(root) / file
                if is_binary_file(file_path):
                    continue

                try:
                    rel_path = str(file_path.relative_to(tool_layer.repo_root)).replace("\\", "/")
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_content = f.read()

                    if file.endswith(".ipynb"):
                        doc = resolve_source_document(rel_path, raw_content)
                        text = doc.source if not doc.conversion_error else raw_content
                    else:
                        text = raw_content

                    matches_in_file = 0
                    for line_idx, line in enumerate(text.splitlines(), start=1):
                        if pattern.search(line):
                            results.append({
                                "file": rel_path,
                                "path": rel_path,
                                "line": line_idx,
                                "snippet": line.strip()[:200],
                                "match_type": "lexical",
                            })
                            matches_in_file += 1
                            if len(results) >= max_matches:
                                return results
                    if matches_in_file > 0:
                        files_with_matches += 1
                except Exception:
                    continue

            if files_scanned > max_files_scanned:
                break
        return results

    # 2. Azure Blob Storage branch
    if not tool_layer.db or not tool_layer.analysis_id:
        return []

    file_query = (
        tool_layer.db.query(FactFile)
        .filter(FactFile.analysis_id == tool_layer.analysis_id)
        .filter(FactFile.blob_name.isnot(None))
    )

    if file_pattern:
        sql_pattern = file_pattern.replace("*", "%").replace("?", "_")
        file_query = file_query.filter(FactFile.path.ilike(sql_pattern))

    candidate_files = file_query.limit(max_files_scanned).all()
    storage = get_storage()
    files_scanned = 0
    files_with_matches = 0

    for f_rec in candidate_files:
        files_scanned += 1
        if not f_rec.blob_name:
            continue

        try:
            raw_text = storage.get_object_text(f_rec.blob_name)
            if not raw_text:
                continue

            doc = resolve_source_document(f_rec.path, raw_text)
            text = doc.source if not doc.conversion_error else raw_text

            matches_in_file = 0
            for line_idx, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    results.append({
                        "file": f_rec.path,
                        "path": f_rec.path,
                        "line": line_idx,
                        "snippet": line.strip()[:200],
                        "match_type": "lexical",
                    })
                    matches_in_file += 1
                    if len(results) >= max_matches:
                        return results
            if matches_in_file > 0:
                files_with_matches += 1
        except Exception:
            continue

    return results


def search_repository_ops(
    tool_layer: Any,
    query: str,
    limit: int = 10,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Hybrid search using HybridRetriever with comma-separated multi-query batching."""
    try:
        limit = int(limit) if limit else 10
        offset = int(offset) if offset else 0
    except (ValueError, TypeError):
        limit = 10
        offset = 0

    retriever = tool_layer._get_retriever()
    if retriever is None:
        return search_repository_fallback_ops(tool_layer, query, limit, offset)

    sub_queries = decompose_query(query)
    if not sub_queries:
        return []

    combined: List[Dict[str, Any]] = []
    seen_keys = set()
    max_total = min(limit * len(sub_queries), 30)

    for sub_query in sub_queries:
        try:
            top_k = max(limit, 10)
            results = retriever.retrieve(sub_query, top_k=top_k)

            for result in results:
                # RetrieverResult has entity_name, entity_type, line_start, line_end, file_path
                sym = getattr(result, "symbol", None) or getattr(result, "entity_name", None)
                l_start = getattr(result, "line_start", None)
                l_end = getattr(result, "line_end", None)
                l_num = getattr(result, "line_number", None) or l_start or 1
                snippet = getattr(result, "snippet", "") or getattr(result, "entity_name", "")

                if sym and getattr(result, "entity_type", None) == "symbol":
                    key = f"sym:{result.file_path}:{sym}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        combined.append({
                            "type": "symbol",
                            "file": result.file_path,
                            "symbol": sym,
                            "lines": f"{l_start}-{l_end}" if l_start else "",
                            "query": sub_query,
                            "match_source": result.score_type or "symbol_index",
                            "score": result.score,
                        })
                else:
                    key = f"code:{result.file_path}:{l_num}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        combined.append({
                            "type": "code",
                            "file": result.file_path,
                            "line": l_num,
                            "snippet": snippet,
                            "query": sub_query,
                            "match_source": result.score_type or "hybrid",
                            "score": result.score,
                        })
        except Exception as e:
            logger.debug(f"Error retrieving for query '{sub_query}': {e}")
            continue

    if not combined:
        return search_repository_fallback_ops(tool_layer, query, limit, offset)

    start = offset
    end = offset + max_total
    return combined[start:end]


def search_repository_fallback_ops(
    tool_layer: Any,
    query: str,
    limit: int = 10,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Fallback to original multi-method search when HybridRetriever is unavailable."""
    combined: List[Dict[str, Any]] = []
    seen_keys = set()

    sub_queries = decompose_query(query)
    if not sub_queries:
        return []


    max_total = min(limit * len(sub_queries), 30)

    # Direct search_code pass with original query for multi-term density matching
    if query not in sub_queries:

        direct_lex = tool_layer.search_code(query, max_matches=10)
        for lex in direct_lex:
            f = lex["file"]
            if f not in seen_keys:
                seen_keys.add(f)
                combined.append({
                    "type": "code",
                    "file": f,
                    "line": lex["line"],
                    "snippet": lex["snippet"],
                    "query": query,
                    "match_source": "lexical_density",
                    "score": 10,
                })

    for sub_query in sub_queries:
        # 1. Symbol search
        sym_matches = tool_layer.get_symbol(sub_query)
        for sym in sym_matches[:5]:
            f = sym["file"]
            if f not in seen_keys:
                seen_keys.add(f)
                combined.append({
                    "type": "symbol",
                    "file": f,
                    "symbol": sym["name"],
                    "symbol_type": sym["symbol_type"],
                    "lines": f"{sym['line_start']}-{sym['line_end']}",
                    "query": sub_query,
                    "match_source": "symbol_index",
                    "score": 5,
                })

        # 2. File path match
        file_matches = tool_layer.find_files(f"*{sub_query}*")
        for f_item in file_matches[:5]:
            f = f_item["path"]
            if f not in seen_keys:
                seen_keys.add(f)
                combined.append({
                    "type": "file",
                    "file": f,
                    "size": f_item.get("size", 0),
                    "query": sub_query,
                    "match_source": "filename_manifest",
                    "score": 2,
                })

        # 3. Lexical search in source files
        lex_matches = tool_layer.search_code(sub_query, max_matches=5)
        for lex in lex_matches:
            f = lex["file"]
            if f not in seen_keys:
                seen_keys.add(f)
                combined.append({
                    "type": "code",
                    "file": f,
                    "line": lex["line"],
                    "snippet": lex["snippet"],
                    "query": sub_query,
                    "match_source": "lexical",
                    "score": 1,
                })

    # Sort results to bubble high-signal density matches to the top
    combined.sort(key=lambda x: -x.get("score", 0))

    start = offset
    end = offset + limit
    return combined[start:end]



