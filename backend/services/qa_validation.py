"""
Stage 4 Fact validation, absence claim verification, and evidence sufficiency checking for QALoop.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.qa_loop import QALoopResult

logger = logging.getLogger(__name__)

# Expanded dictionary of common architectural entities and their related keywords/aliases
SUSPICIOUS_TERMS = [
    ("postgres", ["postgres", "postgresql", "psycopg"]),
    ("postgresql", ["postgres", "postgresql", "psycopg"]),
    ("mysql", ["mysql", "pymysql"]),
    ("sqlite", ["sqlite", "sqlite3"]),
    ("redis", ["redis"]),
    ("chroma", ["chroma", "chromadb"]),
    ("qdrant", ["qdrant"]),
    ("jwt", ["jwt", "pyjwt"]),
    ("token", ["token", "tokens"]),
    ("auth", ["auth", "authenticate", "authoriz"]),
    ("session", ["session"]),
    ("docker", ["docker", "dockerfile"]),
    ("fastapi", ["fastapi"]),
    ("router", ["router", "routing"]),
    ("endpoint", ["endpoint", "endpoints"]),
    ("celery", ["celery"]),
    ("worker", ["worker"]),
    ("queue", ["queue"]),
    ("cache", ["cache"]),
    ("blob", ["blob"]),
    ("s3", ["s3", "boto3"]),
    ("azure", ["azure"]),
    ("websocket", ["websocket", "websockets", "ws"]),
    ("cors", ["cors"]),
    ("middleware", ["middleware"]),
    ("graphql", ["graphql", "strawberry", "ariadne"]),
    ("oauth", ["oauth", "oauth2"]),
    ("migration", ["migration", "migrations", "alembic"]),
    ("alembic", ["alembic"]),
    ("prisma", ["prisma"]),
]

DIRECT_NEGATION = [
    "does not",
    "doesn't",
    "do not",
    "don't",
    "is not",
    "isn't",
    "was not",
    "wasn't",
    "are not",
    "aren't",
    "no function",
    "no module",
    "no package",
    "no component",
    "no service",
    "no feature",
    "no implementation",
    "no code",
    "no database",
    "no postgres",
    "no redis",
    "no auth",
    "no model",
    "no class",
    "there is no",
    "there are no",
    "there's no",
    "has no ",
    "have no ",
    "contains no ",
]

SOFT_NEGATION = [
    "does not appear",
    "doesn't appear",
    "appears not",
    "appears to not",
    "doesn't seem",
    "does not seem",
    "seems not",
    "unable to find",
    "cannot find",
    "could not find",
    "couldn't find",
    "found no",
    "no evidence",
    "no mention",
    "no instances",
    "no references",
    "not found",
    "not present",
    "not implemented",
    "not detected",
    "no results",
]

ENTITY_CONTEXT = [
    "function",
    "module",
    "package",
    "library",
    "component",
    "service",
    "feature",
    "class",
    "interface",
    "method",
    "implementation",
    "pattern",
    "dependency",
    "tool",
    "framework",
    "redis",
    "database",
    "cache",
    "authentication",
    "reset",
    "recovery",
]

REPO_CONTEXT = [
    "repository",
    "codebase",
    "project",
    "code",
    "repo",
    "repository",
    "this repo",
    "this project",
]


def is_absence_claim(answer: str) -> bool:
    """
    Improved heuristic: detect if answer claims repository-wide absence.
    Handles direct negation, soft negation, and entity/repo context.
    """
    answer_lower = answer.lower()
    has_direct = any(p in answer_lower for p in DIRECT_NEGATION)
    has_soft = any(p in answer_lower for p in SOFT_NEGATION)
    has_context = (
        any(e in answer_lower for e in ENTITY_CONTEXT) or
        any(r in answer_lower for r in REPO_CONTEXT)
    )
    return has_direct or (has_soft and has_context)


def has_retrieval_been_performed(result: QALoopResult) -> bool:
    """
    Check if any repository retrieval has been performed in this execution.
    Returns True if: search_repository, read_file, or get_symbol was called and succeeded.
    """
    retrieval_tools = ["search_repository", "read_file", "get_symbol", "search_code", "get_code_relationships"]
    for turn in result.turns:
        if turn.tool_call:
            tool_name = turn.tool_call.get("tool_name", "")
            if tool_name in retrieval_tools:
                if turn.tool_observation and turn.tool_observation.get("success", False):
                    return True
    return False


def check_evidence_sufficiency(question: str, result: QALoopResult) -> Tuple[bool, Optional[str]]:
    """
    Evaluate whether the evidence collected so far is sufficient to answer the user's question,
    enabling proactive early stopping and synthesis rather than exhausting execution turns.

    Relationship-Aware Sufficiency:
    - CALLERS ("Who calls X?"): Requires confirmed CALLS/usage relationships (or inspection of caller code).
      Crucially: imports != callers, definition != callers, text occurrence != caller relationship.
      Reading file X (the definition) alone is NOT sufficient.
    - IMPORTERS ("Who imports X?", "What depends on X?"): Requires IMPORTS relationships.
    - CALLEES ("What does X call?"): Requires forward CALLS relationships or definition inspection.
    - INHERITANCE ("Who inherits X?"): Requires INHERITS relationships.
    - FUNCTIONAL ("What does X do?", "How does X work?"): Target implementation inspection via read_file is sufficient.
    """
    if not question or not result or len(result.turns) == 0:
        return False, None

    from backend.agent.intent.semantic_query import classify_semantic_query, SemanticQueryClass

    intent = classify_semantic_query(question)
    q_lower = question.lower()

    def _extract_read_content(obs_data: Any) -> str:
        if isinstance(obs_data, dict):
            return str(obs_data.get("raw_text") or obs_data.get("content") or "")
        elif isinstance(obs_data, str):
            return obs_data
        return ""

    successful_reads = [
        t for t in result.turns
        if t.tool_call and t.tool_call.get("tool_name") == "read_file"
        and t.tool_observation and t.tool_observation.get("success")
        and len(_extract_read_content(t.tool_observation.get("data"))) > 40
    ]
    successful_graph = [
        t for t in result.turns
        if t.tool_call and t.tool_call.get("tool_name") == "get_code_relationships"
        and t.tool_observation and t.tool_observation.get("success")
        and isinstance(t.tool_observation.get("data"), dict)
        and t.tool_observation.get("data", {}).get("found")
    ]

    target_name = (intent.target_raw_name or "").strip().lower()

    # 1. CALLERS Intent ("Who calls X?", "What functions call X?", "Callers of X")
    if intent.query_class == SemanticQueryClass.CALLS_REVERSE:
        # Require CALLS relationship evidence specifically.
        # imports != callers; definition != callers; text occurrence != callers.
        calls_graph_turns = [
            t for t in successful_graph
            if (
                t.tool_call.get("arguments", {}).get("relationship_type", "").upper() == "CALLS"
                or any(
                    isinstance(r, dict) and r.get("relationship_role") in ("caller", "invoker")
                    for r in t.tool_observation.get("data", {}).get("related", [])
                )
            )
        ]

        if calls_graph_turns:
            graph_data = calls_graph_turns[0].tool_observation.get("data", {})
            related = graph_data.get("related", [])
            resolution = graph_data.get("resolution")

            # Check if caller implementations were inspected or graph confirmed static callers
            has_caller_read = False
            for t in successful_reads:
                read_path = t.tool_call.get("arguments", {}).get("path", "").lower()
                # If read file is different from target definition file or matches a known caller location
                for r in related:
                    loc = r.get("location", "").lower() if isinstance(r, dict) else ""
                    if loc and (loc in read_path or read_path in loc):
                        has_caller_read = True
                        break

            if has_caller_read:
                return True, (
                    "[EVIDENCE SUFFICIENT] Caller relationships and caller implementation details have been inspected. "
                    "You have sufficient evidence to provide your final answer now. Do not call additional tools."
                )

            if resolution == "STATIC_CONFIRMED" and len(related) > 0:
                return True, (
                    "[EVIDENCE SUFFICIENT] Callers have been confirmed by code graph analysis. "
                    "You have sufficient evidence to provide your final answer now. Do not call additional tools."
                )

            if resolution == "NO_STATIC_EDGE_FOUND":
                # Static graph found 0 callers; check if caller files were read or verified
                if len(successful_reads) >= 1:
                    return True, (
                        "[EVIDENCE SUFFICIENT] Graph and code inspections confirmed no static callers. "
                        "You have sufficient evidence to provide your final answer now. Do not call additional tools."
                    )

        # Notice: simply reading the target file (read_file(target)) without caller relationship evidence
        # is NOT sufficient for CALLERS!
        return False, None

    # 2. IMPORTERS / DEPENDENTS Intent ("Who imports X?", "What files depend on X?")
    if intent.query_class == SemanticQueryClass.IMPORTS_REVERSE:
        imports_graph_turns = [
            t for t in successful_graph
            if (
                t.tool_call.get("arguments", {}).get("relationship_type", "").upper() == "IMPORTS"
                or any(
                    isinstance(r, dict) and r.get("relationship_role") in ("importer", "dependent")
                    for r in t.tool_observation.get("data", {}).get("related", [])
                )
            )
        ]
        if imports_graph_turns:
            graph_data = imports_graph_turns[0].tool_observation.get("data", {})
            if graph_data.get("resolution") == "STATIC_CONFIRMED" and len(graph_data.get("related", [])) > 0:
                return True, (
                    "[EVIDENCE SUFFICIENT] Dependent/importer relationships confirmed by code graph analysis. "
                    "You have sufficient evidence to provide your final answer now. Do not call additional tools."
                )
        return False, None

    # 3. CALLEES Intent ("What does X call?", "What does X invoke?")
    if intent.query_class == SemanticQueryClass.CALLS_FORWARD:
        calls_fwd_turns = [
            t for t in successful_graph
            if (
                t.tool_call.get("arguments", {}).get("relationship_type", "").upper() == "CALLS"
                and t.tool_call.get("arguments", {}).get("direction", "").upper() != "REVERSE"
            )
        ]
        if calls_fwd_turns:
            return True, (
                "[EVIDENCE SUFFICIENT] Callees have been confirmed by code graph analysis. "
                "You have sufficient evidence to provide your final answer now. Do not call additional tools."
            )
        # For callees, reading the function definition body is also sufficient evidence of what it calls
        if len(successful_reads) >= 1:
            return True, (
                "[EVIDENCE SUFFICIENT] Target function implementation has been inspected with read_file. "
                "You have sufficient evidence to identify what it calls. Do not call additional tools."
            )
        return False, None

    # 4. INHERITANCE Intent ("Who inherits X?", "Subclasses of X")
    if intent.query_class in (SemanticQueryClass.INHERITS_REVERSE, SemanticQueryClass.INHERITS_FORWARD):
        inherits_graph_turns = [
            t for t in successful_graph
            if t.tool_call.get("arguments", {}).get("relationship_type", "").upper() == "INHERITS"
        ]
        if inherits_graph_turns:
            return True, (
                "[EVIDENCE SUFFICIENT] Inheritance relationships confirmed by code graph analysis. "
                "You have sufficient evidence to provide your final answer now. Do not call additional tools."
            )
        return False, None

    # 5. Other Relational Queries (General graph match fallback)
    is_other_relational = any(w in q_lower for w in ["who calls", "what calls", "caller", "callee", "depend", "import", "where is", "inherits"])
    if is_other_relational and len(successful_graph) >= 1:
        if len(successful_reads) >= 1:
            return True, (
                "[EVIDENCE SUFFICIENT] Structural relationship and relevant code implementation have been inspected. "
                "You have sufficient evidence to provide your final answer now. Do not call additional tools."
            )
        first_graph = successful_graph[0].tool_observation.get("data", {})
        if first_graph.get("resolution") == "STATIC_CONFIRMED" and len(first_graph.get("related", [])) > 0:
            return True, (
                "[EVIDENCE SUFFICIENT] Structural relationships have been confirmed by code graph analysis. "
                "You have sufficient evidence to provide your final answer now. Do not call additional tools."
            )

    # 6. Functional questions ("what does", "how does", "explain", "how is", "where is", "definition of")
    # Exclude multi-hop, trace, or compound lifecycle queries which require multi-component investigation
    is_trace_or_multihop = any(w in q_lower for w in ["trace", "lifecycle", "across", "preventing", "flow", "pipeline", "and how", "and where"])
    is_functional_q = any(w in q_lower for w in ["what does", "how does", "explain", "how is", "where is", "definition of"])
    if is_functional_q and not is_trace_or_multihop and len(successful_reads) >= 1:
        return True, (
            "[EVIDENCE SUFFICIENT] The target implementation has been inspected with read_file. "
            "You have sufficient evidence to provide your final answer now. Do not call additional tools."
        )

    return False, None


def identify_missing_evidence(
    question: str,
    result: QALoopResult,
    attempted_tool: str,
    attempted_args: Dict[str, Any],
) -> str:
    """
    Diagnose what evidence is missing when a model makes a duplicate tool call,
    providing targeted and actionable guidance to prevent endless duplicate loops.
    """
    from backend.agent.intent.semantic_query import classify_semantic_query, SemanticQueryClass

    q_lower = question.lower() if question else ""
    turns = result.turns if result else []
    intent = classify_semantic_query(question) if question else None

    successful_reads = [
        t for t in turns
        if t.tool_call and t.tool_call.get("tool_name") == "read_file"
        and t.tool_observation and t.tool_observation.get("success")
    ]
    successful_graph = [
        t for t in turns
        if t.tool_call and t.tool_call.get("tool_name") == "get_code_relationships"
        and t.tool_observation and t.tool_observation.get("success")
        and isinstance(t.tool_observation.get("data"), dict)
        and t.tool_observation.get("data", {}).get("found")
    ]
    successful_searches = [
        t for t in turns
        if t.tool_call and t.tool_call.get("tool_name") in ("search_repository", "search_code")
        and t.tool_observation and t.tool_observation.get("success")
        and isinstance(t.tool_observation.get("data"), list)
        and len(t.tool_observation.get("data", [])) > 0
    ]

    target_name = intent.target_raw_name if intent else ""

    # Special guidance for CALLERS questions:
    if intent and intent.query_class == SemanticQueryClass.CALLS_REVERSE:
        calls_graph = [
            t for t in successful_graph
            if t.tool_call.get("arguments", {}).get("relationship_type", "").upper() == "CALLS"
        ]
        if not calls_graph:
            return (
                f"For caller questions ('Who calls {target_name or 'target'}?'), definition or imports do NOT prove callers. "
                f"Missing evidence: callers relationship. Call get_code_relationships(entity_name='{target_name or 'target'}', "
                f"relationship_type='CALLS', direction='REVERSE')."
            )
        else:
            graph_data = calls_graph[0].tool_observation.get("data", {})
            related = graph_data.get("related", [])
            if related and isinstance(related[0], dict) and related[0].get("location"):
                loc = related[0].get("location")
                line = related[0].get("line_number", 1)
                start = max(1, line - 15)
                end = line + 25
                return (
                    f"Callers were identified by code graph. What is missing is inspecting caller usage. "
                    f"Read the caller file '{loc}' around line {line} using: "
                    f"read_file(path='{loc}', start_line={start}, end_line={end})."
                )
            return (
                f"Callers relationship was queried. If no static callers were found, search for invocations "
                f"'{target_name}(' using search_repository or provide your final answer."
            )

    # Special guidance for IMPORTERS questions:
    if intent and intent.query_class == SemanticQueryClass.IMPORTS_REVERSE:
        imports_graph = [
            t for t in successful_graph
            if t.tool_call.get("arguments", {}).get("relationship_type", "").upper() == "IMPORTS"
        ]
        if not imports_graph:
            return (
                f"For dependency/importer questions, missing evidence: reverse import relationship. "
                f"Call get_code_relationships(entity_name='{target_name or 'target'}', relationship_type='IMPORTS', direction='REVERSE')."
            )

    is_relational_q = any(w in q_lower for w in ["who calls", "what calls", "caller", "callee", "depend", "import", "where is", "inherits"])
    is_functional_q = any(w in q_lower for w in ["what does", "how does", "explain", "how is", "where is", "definition of"])

    # 1. Relational query: graph was checked but implementation not read
    if is_relational_q:
        if len(successful_graph) >= 1 and len(successful_reads) == 0:
            graph_data = successful_graph[0].tool_observation.get("data", {})
            related = graph_data.get("related", [])
            target = graph_data.get("target", {})
            if related and isinstance(related[0], dict) and related[0].get("location"):
                loc = related[0].get("location")
                line = related[0].get("line_number", 1)
                start = max(1, line - 15)
                end = line + 25
                return (
                    f"Structural relationships were already discovered. What is missing is the implementation details. "
                    f"Read the caller/callee file at '{loc}' around line {line} using: "
                    f"read_file(path='{loc}', start_line={start}, end_line={end})."
                )
            if target and target.get("location"):
                loc = target.get("location")
                line = target.get("line", 1)
                start = max(1, line - 10)
                end = line + 30
                return (
                    f"Target symbol was located. What is missing is the source code implementation. "
                    f"Inspect '{loc}' using: read_file(path='{loc}', start_line={start}, end_line={end})."
                )

        if len(successful_graph) == 0:
            return (
                "Code relationships have not yet been queried. "
                "Call get_code_relationships with the entity_name and relationship_type (e.g. CALLS, IMPORTS)."
            )

    # 2. Functional query: symbol or file located but implementation not read
    if is_functional_q or len(successful_reads) == 0:
        if successful_searches:
            # Look for matches in files that haven't been read yet, or unread ranges
            read_files_map = {}
            for r in successful_reads:
                r_args = r.tool_call.get("arguments", {})
                r_path = (r_args.get("path") or "").replace("\\", "/").strip("/").lower()
                r_end = r_args.get("end_line") or 0
                if r_path:
                    read_files_map[r_path] = max(read_files_map.get(r_path, 0), int(r_end))

            candidate_matches = []
            for s_turn in successful_searches:
                for match in s_turn.tool_observation.get("data", []):
                    if isinstance(match, dict):
                        p = match.get("file_path") or match.get("file")
                        ln = match.get("line_number") or match.get("line") or 1
                        if p:
                            p_norm = p.replace("\\", "/").strip("/").lower()
                            if p_norm not in read_files_map:
                                candidate_matches.append((p, int(ln), False))
                            elif int(ln) > read_files_map[p_norm]:
                                # Match is in lines of an active file that were NOT read yet
                                candidate_matches.append((p, int(ln), True))

            if candidate_matches:
                # Prioritize unread ranges of files already being examined, or specific matches
                candidate_matches.sort(key=lambda c: (0 if c[2] else 1))
                path, line, _ = candidate_matches[0]
                start = max(1, line - 10)
                end = line + 30
                return (
                    f"Search results located potential references. What is missing is inspecting the actual code. "
                    f"Call read_file(path='{path}', start_line={start}, end_line={end})."
                )

    # 3. Default fallback when specific path not matched
    return (
        "Do not repeat identical calls. If you need implementation details, call read_file on discovered files; "
        "if you need another symbol or file, search for that specific term; otherwise provide your final answer."
    )



def retrieval_evidence_supports_absence(result: QALoopResult, answer: str = "") -> Tuple[bool, str]:
    """
    Check if the actual retrieval result data supports an absence claim.
    """
    retrieval_tools = ["search_repository", "read_file", "get_symbol", "search_code", "get_code_relationships"]
    found_positive_matches: List[str] = []
    had_successful_retrieval = False
    had_failed_search = False

    answer_lower = answer.lower() if answer else ""

    for turn in result.turns:
        if not turn.tool_call or not turn.tool_observation:
            continue

        tool_name = turn.tool_call.get("tool_name", "")
        if tool_name not in retrieval_tools:
            continue

        if not turn.tool_observation.get("success", False):
            had_failed_search = True
            continue

        had_successful_retrieval = True
        result_data = turn.tool_observation.get("data", None)

        if tool_name in ("search_repository", "search_code"):
            if isinstance(result_data, list) and len(result_data) > 0:
                for item in result_data:
                    if isinstance(item, dict):
                        sym = item.get("symbol") or ""
                        file_p = item.get("file") or item.get("path") or ""
                        snip = item.get("snippet") or ""
                        found_positive_matches.append(f"{sym} in {file_p}: {snip[:80]}".strip())

        elif tool_name == "get_symbol":
            if result_data:
                if isinstance(result_data, list):
                    for sym in result_data:
                        if isinstance(sym, dict):
                            found_positive_matches.append(f"symbol {sym.get('name')} in {sym.get('file')}")
                elif isinstance(result_data, dict):
                    found_positive_matches.append(f"symbol {result_data.get('name')}")

        elif tool_name == "read_file":
            if isinstance(result_data, dict):
                raw_text = result_data.get("raw_text") or result_data.get("content") or ""
                file_p = result_data.get("path", "")
                if raw_text:
                    found_positive_matches.append(f"file content in {file_p}")

    if not had_successful_retrieval:
        if had_failed_search:
            return False, "Failed or errored searches cannot be treated as proof of absence."
        return False, "No retrieval was performed to verify this absence claim."

    # 1. Contradiction Check: If positive evidence was retrieved that contradicts an absence claim
    if found_positive_matches and answer_lower:
        for term, aliases in SUSPICIOUS_TERMS:
            if term in answer_lower and any(neg in answer_lower for neg in ["no ", "not ", "does not", "doesn't", "without"]):
                for turn in result.turns:
                    obs = turn.tool_observation or {}
                    if obs.get("success"):
                        data_str = str(obs.get("data", "")).lower()
                        if any(alias in data_str for alias in aliases):
                            return False, f"Contradicted by evidence: repository search/read observed '{term}' in the codebase."

    # 2. Targeted Query Relevance Check
    if answer_lower:
        claimed_absent = []
        for term, aliases in SUSPICIOUS_TERMS:
            if term in answer_lower and any(neg in answer_lower for neg in ["no ", "not ", "does not", "doesn't", "without"]):
                claimed_absent.append((term, aliases))

        if claimed_absent:
            searched_queries = []
            for turn in result.turns:
                tc = turn.tool_call or {}
                obs = turn.tool_observation or {}
                if not obs.get("success"):
                    continue
                args = tc.get("arguments", {})
                q_str = str(args.get("query") or args.get("name") or args.get("entity_name") or args.get("path") or "").lower()
                if q_str:
                    searched_queries.append(q_str)

            has_relevant_search = False
            for term, aliases in claimed_absent:
                for q in searched_queries:
                    if any(alias in q for alias in aliases) or q in aliases or term in q:
                        has_relevant_search = True
                        break
                if has_relevant_search:
                    break

            if not has_relevant_search:
                terms_str = ", ".join(t[0] for t in claimed_absent[:3])
                return False, f"Absence claim for '{terms_str}' is unverified: searches performed in this session did not target '{terms_str}' or related identifiers."

    return True, "supported"


def validate_final_answer_against_evidence(
    answer: str,
    result: QALoopResult,
) -> Tuple[bool, Optional[str], str]:
    """
    Stage 4: Validate factual claims in the final answer against tool results
    available in the current QA session.
    """
    if not answer or not answer.strip():
        return False, "Final answer is empty. Please provide your answer based on repository evidence.", answer

    answer_clean = answer.strip()
    contradictions: List[str] = []
    caveats: List[str] = []

    # 1. Check for absence claims
    if is_absence_claim(answer_clean):
        is_supported, reason = retrieval_evidence_supports_absence(result, answer_clean)
        if not is_supported:
            contradictions.append(f"Absence claim unverified: {reason}")

    # 2. Check for contradictions with read_file contents
    inspected_files: Dict[str, Dict[str, Any]] = {}
    for turn in result.turns:
        tc = turn.tool_call or {}
        obs = turn.tool_observation or {}
        if tc.get("tool_name") == "read_file" and obs.get("success") and isinstance(obs.get("data"), dict):
            p = tc.get("arguments", {}).get("path", "")
            if p:
                inspected_files[p] = obs["data"]

    # Check for truncated read caveats
    truncated_files = [p for p, data in inspected_files.items() if data.get("is_truncated") or data.get("_truncated")]
    if truncated_files:
        for tf in truncated_files:
            base_name = tf.split("/")[-1]
            if base_name in answer_clean and ("entire" in answer_clean.lower() or "only" in answer_clean.lower() or "complete" in answer_clean.lower()):
                caveats.append(f"Note: '{tf}' was partially read due to line limits. Further definitions may exist beyond the inspected lines.")

    # Check for contradictions with specific search results and inspected file contents
    for turn in result.turns:
        tc = turn.tool_call or {}
        obs = turn.tool_observation or {}
        tname = tc.get("tool_name", "")
        if not obs.get("success"):
            continue
        data = obs.get("data")

        if tname in ("search_repository", "search_code", "get_symbol") and isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    sym_name = item.get("symbol") or item.get("name")
                    file_name = item.get("file") or item.get("path")
                    if sym_name and len(sym_name) > 2:
                        sym_pat = re.compile(rf"\b(no|not|does not contain|does not exist|cannot find|isn't any)\b[^\.\n]*\b{re.escape(sym_name)}\b", re.IGNORECASE)
                        if sym_pat.search(answer_clean):
                            contradictions.append(f"Claim that '{sym_name}' does not exist is contradicted by tool observation in {file_name}.")

        elif tname == "read_file" and isinstance(data, dict):
            file_text = data.get("raw_text") or data.get("content") or ""
            file_name = data.get("path", "")
            for def_match in re.finditer(r"\b(?:class|def|function|interface)\s+([A-Za-z0-9_]+)", file_text):
                sym_name = def_match.group(1)
                if len(sym_name) > 2:
                    sym_pat = re.compile(rf"\b(no|not|does not contain|does not exist|cannot find|isn't any)\b[^\.\n]*\b{re.escape(sym_name)}\b", re.IGNORECASE)
                    if sym_pat.search(answer_clean):
                        contradictions.append(f"Claim that '{sym_name}' does not exist is contradicted by tool observation in {file_name}.")

    # Check for blanket claims that inspected files were "not inspected" or "could not be verified"
    for file_path in inspected_files.keys():
        file_base = file_path.split("/")[-1].split("\\")[-1]
        not_inspected_pat = re.compile(
            rf"\b(?:was not|were not|could not be|not)\s+(?:inspected|read|investigated|found)\b[^\.\n]*\b{re.escape(file_base)}\b"
            rf"|\b{re.escape(file_base)}\b[^\.\n]*\b(?:was not|were not|could not be|not)\s+(?:inspected|read|investigated|found)\b",
            re.IGNORECASE,
        )
        if not_inspected_pat.search(answer_clean):
            contradictions.append(
                f"Claim that '{file_base}' was not inspected is contradicted by execution trace: "
                f"file was read and inspected in this session."
            )

    # 3. Positive Relationship Claim Validation (P0-4):
    # Detect assertions like "X calls Y" or "X invokes Y" and verify that evidence was retrieved.
    # Pattern: `<file_or_func> calls <callee>` or `<file_or_func> invokes <callee>`
    call_claim_patterns = [
        re.compile(r'([a-zA-Z0-9_\-\.\/]+)\s+(?:directly\s+|indirectly\s+)?(?:calls|invokes|executes)\s+([a-zA-Z0-9_]+)', re.IGNORECASE),
        re.compile(r'([a-zA-Z0-9_]+)\s+is\s+(?:called|invoked)\s+by\s+([a-zA-Z0-9_\-\.\/]+)', re.IGNORECASE),
    ]

    claimed_relationships: List[Tuple[str, str]] = []
    for pattern in call_claim_patterns:
        for match in pattern.finditer(answer_clean):
            g1, g2 = match.group(1).strip(), match.group(2).strip()
            # If pattern was "is called by", g1 is target/callee and g2 is caller
            if "called" in pattern.pattern:
                caller, callee = g2, g1
            else:
                caller, callee = g1, g2
            # Filter out generic words or punctuation
            if len(caller) >= 2 and len(callee) >= 2 and caller.lower() not in ("what", "who", "which", "how", "it", "this", "that", "there"):
                claimed_relationships.append((caller, callee))

    if claimed_relationships:
        # Collect all verified relationships from graph observations and read_file contents
        verified_relationships: List[Tuple[str, str]] = []
        observed_files_text: Dict[str, str] = {}
        observed_symbols: set[str] = set()

        for turn in result.turns:
            tc = turn.tool_call or {}
            obs = turn.tool_observation or {}
            if not obs.get("success"):
                continue
            tname = tc.get("tool_name", "")
            tdata = obs.get("data")

            if tname == "get_code_relationships" and isinstance(tdata, dict):
                target = tdata.get("target", {})
                target_name = (target.get("name") or "").lower()
                target_loc = (target.get("location") or "").lower()
                related = tdata.get("related", [])
                for rel in related:
                    if isinstance(rel, dict):
                        rel_name = (rel.get("name") or "").lower()
                        rel_loc = (rel.get("location") or "").lower()
                        role = (rel.get("relationship_role") or "").lower()
                        # If related is caller, (related, target) is verified
                        if role in ("caller", "invoker", "calls"):
                            verified_relationships.append((rel_name, target_name))
                            if rel_loc:
                                verified_relationships.append((rel_loc, target_name))
                        # If related is callee, (target, related) is verified
                        elif role in ("callee", "invoked"):
                            verified_relationships.append((target_name, rel_name))
                            if target_loc:
                                verified_relationships.append((target_loc, rel_name))
                        else:
                            # General relationship
                            verified_relationships.append((rel_name, target_name))
                            verified_relationships.append((target_name, rel_name))
                            if rel_loc:
                                verified_relationships.append((rel_loc, target_name))
                            if target_loc:
                                verified_relationships.append((target_loc, rel_name))

            elif tname == "read_file" and isinstance(tdata, dict):
                p = (tc.get("arguments", {}).get("path") or tdata.get("path") or "").lower()
                text = tdata.get("raw_text") or tdata.get("content") or ""
                if p and text:
                    observed_files_text[p] = text

            elif tname in ("search_repository", "search_code") and isinstance(tdata, list):
                for item in tdata:
                    if isinstance(item, dict):
                        fp = (item.get("file_path") or item.get("file") or "").lower()
                        snip = item.get("snippet") or ""
                        if fp and snip:
                            observed_files_text[fp] = observed_files_text.get(fp, "") + "\n" + snip

        for caller, callee in claimed_relationships:
            c_caller = caller.lower()
            c_callee = callee.lower()
            caller_base = c_caller.split("/")[-1].split("\\")[-1]

            # Check 1: In verified graph relationships?
            is_verified = False
            for v_caller, v_callee in verified_relationships:
                if (c_caller in v_caller or caller_base in v_caller or v_caller in c_caller) and (c_callee in v_callee or v_callee in c_callee):
                    is_verified = True
                    break

            # Check 2: In observed file texts (e.g. caller file was read and contains call to callee)?
            if not is_verified:
                for fpath, fcontent in observed_files_text.items():
                    fpath_base = fpath.split("/")[-1].split("\\")[-1]
                    if (c_caller in fpath or caller_base == fpath_base or c_caller in fcontent.lower()):
                        # Check if callee is called or referenced in this file's observed text
                        callee_call_pattern = rf"\b{re.escape(c_callee)}\s*\("
                        if re.search(callee_call_pattern, fcontent, re.IGNORECASE) or (fpath_base == caller_base and c_callee in fcontent.lower()):
                            is_verified = True
                            break

            if not is_verified:
                contradictions.append(
                    f"Claim that '{caller}' calls '{callee}' is unsupported by retrieved evidence: "
                    f"no tool observations (graph relationships or inspected files) show this call relationship."
                )

    # 4. Unverified Implementation Claims & File Reference Grounding:
    # If the answer cites specific files that were NEVER read or even observed in search hits,
    # prompt the agent to inspect those files before asserting claims about their behavior.
    cited_files = set(re.findall(r'\b(?:app\/[a-zA-Z0-9_\-\.\/]+\.(?:js|ts|py)|backend\/[a-zA-Z0-9_\-\.\/]+\.(?:py|ts|js))\b', answer_clean))
    inspected_paths_lower = {p.lower() for p in inspected_files.keys()}
    searched_hits_lower = set()
    for turn in result.turns:
        obs = (turn.tool_observation or {}).get("data")
        if isinstance(obs, list):
            for item in obs:
                if isinstance(item, dict):
                    f = (item.get("file_path") or item.get("file") or item.get("path") or "").lower()
                    if f:
                        searched_hits_lower.add(f)
        elif isinstance(obs, dict):
            f = (obs.get("file_path") or obs.get("file") or obs.get("path") or "").lower()
            if f:
                searched_hits_lower.add(f)

    for cited_file in cited_files:
        cf_lower = cited_file.lower()
        has_read = cf_lower in inspected_paths_lower or any(cf_lower in p or p in cf_lower for p in inspected_paths_lower)
        has_search = cf_lower in searched_hits_lower or any(cf_lower in p or p in cf_lower for p in searched_hits_lower)
        if not has_read and not has_search:
            contradictions.append(
                f"File '{cited_file}' is cited as part of the core implementation/flow but was never inspected or observed in search in this session. "
                f"Inspect '{cited_file}' with read_file to verify its behavior before asserting claims about it."
            )

    if contradictions:
        feedback_msg = (
            "[VERIFICATION FAILED] The following factual claims conflict with tool observations or lack evidence:\n"
            + "\n".join(f"- {c}" for c in contradictions)
            + "\n\nPlease review your observations, correct any contradicted statements, and provide a verified answer."
        )
        warning_box = (
            "\n\n> [!WARNING]\n> **Verification Caveat:**\n"
            + "\n".join(f"> - {c}" for c in contradictions)
        )
        caveated_answer = answer_clean + warning_box
        return False, feedback_msg, caveated_answer

    if caveats:
        disclaimer = "\n\n> [!NOTE]\n" + "\n".join(f"> {c}" for c in caveats)
        return True, None, answer_clean + disclaimer

    return True, None, answer_clean
