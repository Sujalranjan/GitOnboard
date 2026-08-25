"""
Semantic Query Interpreter: Analyzes natural-language repository exploration queries
and produces a structured SemanticQueryIntent.

Pure NLP / Pattern matching layer with zero database or network access.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List


class SemanticQueryClass(str, Enum):
    CONTAINMENT = "CONTAINMENT"            # "What functions in file?", "Methods in class?"
    IMPORTS_FORWARD = "IMPORTS_FORWARD"    # "What does file import?", "What modules are imported by file?"
    IMPORTS_REVERSE = "IMPORTS_REVERSE"    # "What files import file?", "Who depends on file?"
    CALLS_FORWARD = "CALLS_FORWARD"        # "What does function call?", "What does foo invoke?"
    CALLS_REVERSE = "CALLS_REVERSE"        # "What functions call function?", "Who calls foo?"
    INHERITS_FORWARD = "INHERITS_FORWARD"  # "What does class inherit from?", "Base class of class?"
    INHERITS_REVERSE = "INHERITS_REVERSE"  # "What classes inherit from class?", "Subclasses of class?"
    ROUTE_HANDLER = "ROUTE_HANDLER"        # "What handler serves route /api/...", "Who handles GET /users?"
    DATABASE_ACCESS = "DATABASE_ACCESS"    # "What code uses Table/Model?", "Functions accessing users table?"
    GENERIC_LOOKUP = "GENERIC_LOOKUP"      # "Where is X?", "Search for X"


class TraversalDirection(str, Enum):
    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


@dataclass
class SemanticQueryIntent:
    query_class: SemanticQueryClass
    target_raw_name: str
    target_hint: Optional[str] = None  # "file", "function", "class", "route", "database"
    direction: TraversalDirection = TraversalDirection.FORWARD
    http_method: Optional[str] = None
    confidence: float = 1.0


def classify_semantic_query(user_requirement: str) -> SemanticQueryIntent:
    """
    Deterministically extracts the semantic query class, target entity name, and direction.
    """
    if not user_requirement or not user_requirement.strip():
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.GENERIC_LOOKUP,
            target_raw_name="",
            confidence=1.0,
        )

    req_clean = user_requirement.strip()
    req_lower = req_clean.lower()

    # 0. Early exclusion guards
    # If the prompt starts with a mutation action verb (modify, implement, add, fix, refactor, etc.) -> NOT exploration
    if re.search(r'^\s*(?:modify|add|implement|fix|refactor|delete|create|update|build|remove)\b', req_lower):
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.GENERIC_LOOKUP,
            target_raw_name=req_clean,
            confidence=0.0,
        )

    # If the prompt starts with a general explanation phrase without an explicit relationship keyword -> NOT exploration
    if re.search(r'^\s*(?:tell\s+me\s+about|why\s+is|how\s+does|explain\s+how|explain\s+why|explain\s+the)\b', req_lower) and not any(r in req_lower for r in ["call", "import", "inherit", "handler", "endpoint", "route", "depend on"]):
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.GENERIC_LOOKUP,
            target_raw_name=req_clean,
            confidence=0.0,
        )

    # 1. Check for Route / Endpoint patterns
    # e.g., "What handler serves /api/v1/login?", "Who handles GET /users?"
    route_match = re.search(r'(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)?\s*(\/[a-zA-Z0-9_\-\.\/\{\}]+)', req_clean)
    method_match = re.search(r'\b(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\b', req_clean)
    http_method = method_match.group(1).upper() if method_match else None

    if route_match and any(v in req_lower for v in ["handler", "serve", "handle", "endpoint", "route", "serves", "handles"]):
        route_path = route_match.group(1)
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.ROUTE_HANDLER,
            target_raw_name=route_path,
            target_hint="route",
            direction=TraversalDirection.FORWARD,
            http_method=http_method,
            confidence=0.95,
        )

    # 2. Extract potential file path candidate if present
    file_path_match = re.search(r'([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)', req_clean)
    target_file = file_path_match.group(1).replace("\\", "/").strip("./") if file_path_match else None

    # 3. Check for Forward Imports: "What imports does X have?", "What does X import?", "What modules does X import?", "What files does X import?"
    if any(re.search(p, req_lower) for p in [
        r'\bwhat\s+imports\s+does\b',
        r'\bwhat\s+(?:modules|files|packages)\s+does\s+.*\s+import\b',
        r'\bwhat\s+does\s+.*\s+import\b',
        r'\bshow\s+(?:all\s+)?imports\s+(?:for|in|of)\s+',
        r'\blist\s+(?:all\s+)?imports\s+(?:for|in|of)\s+',
        r'\bimports\s+(?:in|of|for)\s+',
        r'\bimports\s+used\s+by\b',
    ]):
        target = target_file or _extract_subject_target(req_clean, [
            "what imports does", "does", "import", "imports in", "imports of", "imports for", "imports used by"
        ])
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.IMPORTS_FORWARD,
            target_raw_name=target,
            target_hint="file" if target_file else "module",
            direction=TraversalDirection.FORWARD,
            confidence=0.95,
        )

    # Reverse Imports: "What files import X?", "Who imports X?", "What files depend on X?", "Which files use X?", "Who depends on X?"
    if any(re.search(p, req_lower) for p in [
        r'\b(?:what|which)\s+(?:files|modules|code)\s+(?:import|depend\s+on|use)\s+',
        r'\b(?:who|what)\s+(?:imports|depends\s+on|uses)\s+',
        r'\bimported\s+by\b',
        r'\bdependents?\s+of\b',
        r'\bdependencies\s+(?:on|for)\b',
    ]) and not any(d in req_lower for d in ["table", "database model", "db model", "database table", "schema"]):
        target = target_file or _extract_subject_target(req_clean, [
            "import", "imports", "depend on", "depends on", "use", "uses", "imported by", "dependents of", "dependencies on", "dependencies for"
        ])
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.IMPORTS_REVERSE,
            target_raw_name=target,
            target_hint="file" if target_file else "module",
            direction=TraversalDirection.REVERSE,
            confidence=0.95,
        )

    # 4. Check for Calls Forward & Reverse
    # Reverse Calls (Callers): "What functions call X?", "Who calls X?", "Which functions invoke X?", "Who invokes X?"
    if any(re.search(p, req_lower) for p in [
        r'\b(?:what|which)\s+(?:functions|methods|code|callers)\s+(?:call|invoke|use)\s+',
        r'\b(?:who|what)\s+(?:calls|invokes)\s+',
        r'\bcalled\s+by\b',
        r'\binvoked\s+by\b',
        r'\bcallers\s+of\b',
    ]):
        target = _extract_subject_target(req_clean, ["call", "calls", "invoke", "invokes", "called by", "invoked by", "callers of"])
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.CALLS_REVERSE,
            target_raw_name=target,
            target_hint="function",
            direction=TraversalDirection.REVERSE,
            confidence=0.95,
        )

    # Forward Calls (Callees): "What functions does X call?", "What does X call?", "What does X invoke?"
    if any(re.search(p, req_lower) for p in [
        r'\bwhat\s+(?:functions|methods)\s+does\s+.*\s+(?:call|invoke)\b',
        r'\bwhat\s+does\s+.*\s+(?:call|invoke)\b',
        r'\bwhich\s+functions\s+does\s+.*\s+call\b',
        r'\bwhat\s+methods\s+does\s+.*\s+call\b',
        r'\bcallees\s+of\b',
        r'\bfunctions\s+called\s+by\b',
    ]):
        target = _extract_subject_target(req_clean, [
            "what functions does", "what methods does", "what does", "which functions does", "callees of", "called by"
        ])
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.CALLS_FORWARD,
            target_raw_name=target,
            target_hint="function",
            direction=TraversalDirection.FORWARD,
            confidence=0.95,
        )

    # 5. Check for Inheritance Forward & Reverse
    # Reverse Inheritance (Subclasses): "What classes inherit from X?", "Which classes extend X?", "Subclasses of X"
    if any(re.search(p, req_lower) for p in [
        r'\b(?:what|which)\s+classes\s+(?:inherit\s+from|extend)\s+',
        r'\b(?:who|what)\s+(?:inherits\s+from|extends)\s+',
        r'\bsubclasses\s+of\b',
        r'\bclasses\s+extending\b',
        r'\bclasses\s+inheriting\s+from\b',
    ]):
        target = _extract_subject_target(req_clean, ["inherit from", "inherits from", "extend", "extends", "subclasses of", "extending"])
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.INHERITS_REVERSE,
            target_raw_name=target,
            target_hint="class",
            direction=TraversalDirection.REVERSE,
            confidence=0.95,
        )

    # Forward Inheritance (Base Class): "What classes does X inherit from?", "What does X extend?", "Base class of X"
    if any(re.search(p, req_lower) for p in [
        r'\bwhat\s+classes\s+does\s+.*\s+inherit\s+from\b',
        r'\bwhat\s+does\s+.*\s+(?:inherit\s+from|extend)\b',
        r'\bwhich\s+classes\s+does\s+.*\s+extend\b',
        r'\bbase\s+class\s+(?:of|for)\b',
        r'\bparent\s+class\s+(?:of|for)\b',
        r'\bsuper\s*class\s+(?:of|for)\b',
    ]):
        target = _extract_subject_target(req_clean, [
            "what classes does", "what does", "which classes does", "base class of", "base class for", "parent class of", "parent class for", "superclass of", "superclass for"
        ])
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.INHERITS_FORWARD,
            target_raw_name=target,
            target_hint="class",
            direction=TraversalDirection.FORWARD,
            confidence=0.95,
        )

    # 6. Check for Database Access / Queries
    # e.g., "What code uses UserTable?", "Which functions access the users table?", "Where is users table used?"
    if (
        (any(k in req_lower for k in ["table", "database model", "db model", "database table", "schema"]) and any(v in req_lower for v in ["uses", "use", "accesses", "access", "queries", "query", "reads", "writes", "where is", "what code"]))
        or (any(v in req_lower for v in ["uses", "accesses", "queries", "reads", "writes"]) and any(d in req_lower for d in ["table", "model", "db", "userstable", "ordermodel"]))
    ):
        target = _extract_subject_target(req_clean, ["uses", "use", "accesses", "access", "queries", "query", "reads", "writes", "table", "model"])
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.DATABASE_ACCESS,
            target_raw_name=target,
            target_hint="database",
            direction=TraversalDirection.REVERSE,
            confidence=0.90,
        )

    # 7. Check for Containment
    # e.g., "What functions are defined in X?", "List functions in X", "What methods are in X?"
    if any(re.search(p, req_lower) for p in [
        r'\b(?:what|which)\s+(?:functions|methods|classes|symbols)\s+(?:are\s+)?(?:defined|implemented|contained)?\s*(?:in|inside)\s+',
        r'\blist\s+(?:all\s+)?(?:functions|methods|classes|symbols)\s+(?:in|inside|of)\s+',
        r'\bshow\s+(?:me\s+)?(?:the\s+)?(?:functions|methods|classes|symbols)\s+(?:in|inside|of)\s+',
        r'\bmethods\s+(?:in|inside|of)\s+',
        r'\bfunctions\s+(?:in|inside|of)\s+',
    ]):
        target = target_file or _extract_subject_target(req_clean, ["defined in", "implemented in", "functions in", "methods in", "classes in", "in", "inside", "of"])
        return SemanticQueryIntent(
            query_class=SemanticQueryClass.CONTAINMENT,
            target_raw_name=target,
            target_hint="file" if target_file else "class",
            direction=TraversalDirection.FORWARD,
            confidence=0.95,
        )

    # 8. Fallback: Generic Lookup
    target = target_file or _extract_fallback_target(req_clean)
    return SemanticQueryIntent(
        query_class=SemanticQueryClass.GENERIC_LOOKUP,
        target_raw_name=target,
        target_hint=None,
        direction=TraversalDirection.FORWARD,
        confidence=0.80,
    )


def _extract_subject_target(text: str, trigger_phrases: List[str]) -> str:
    """Helper to extract clean entity name following or preceding trigger phrases."""
    clean = text.rstrip("?.! ")
    clean_lower = clean.lower()

    for phrase in trigger_phrases:
        if phrase in clean_lower:
            parts = re.split(re.escape(phrase), clean, flags=re.IGNORECASE)
            if len(parts) > 1 and parts[1].strip():
                candidate = parts[1].strip()
                # Remove trailing question words / punctuation / relationship verbs
                candidate = re.split(r'\b(?:have|call|import|invoke|use|from|in|do|does|have\s+been|inherit|inherits|extend|extends)\b', candidate, flags=re.IGNORECASE)[0].strip()
                candidate = re.sub(r'^(?:the|a|an|this|that|my)\s+', '', candidate, flags=re.IGNORECASE).strip()
                candidate = candidate.rstrip("?.! ")
                if candidate:
                    return candidate
            elif len(parts) > 0 and parts[0].strip():
                candidate = parts[0].strip()
                candidate = re.sub(r'^(?:what|which|who|show|list|tell\s+me)\s+(?:functions|methods|classes|files|modules)?\s*(?:does|do|is|are)?\s*', '', candidate, flags=re.IGNORECASE).strip()
                candidate = re.sub(r'^(?:the|a|an|this|that|my)\s+', '', candidate, flags=re.IGNORECASE).strip()
                candidate = candidate.rstrip("?.! ")
                if candidate:
                    return candidate

    return _extract_fallback_target(text)


def _extract_fallback_target(text: str) -> str:
    """Extracts the most significant identifier or file path token from query text."""
    # Check for file path
    file_match = re.search(r'([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)', text)
    if file_match:
        return file_match.group(1).replace("\\", "/").strip("./")

    # Check for identifiers
    stop_words = {
        "what", "which", "where", "how", "why", "who", "when", "show", "find", "list",
        "give", "tell", "explain", "defined", "implemented", "functions", "function",
        "classes", "class", "methods", "method", "symbols", "symbol", "files", "file",
        "exact", "names", "name", "based", "only", "indexed", "evidence", "repository",
        "repo", "each", "does", "do", "did", "done", "with", "from", "that", "this",
        "these", "those", "their", "have", "has", "had", "been", "here", "there",
        "work", "code", "about", "are", "the", "and", "for", "all", "in", "on", "at",
        "to", "of", "by", "me", "my", "a", "an", "is", "it", "its", "as", "or", "so",
        "if", "up", "out", "no", "not", "be", "we", "he", "she", "us", "you", "they",
        "them", "would", "could", "should", "shall", "will", "can", "may", "might",
        "must", "trace", "detail", "describe", "see", "get", "look", "inspect"
    }
    tokens = re.findall(r'[a-zA-Z0-9_]+', text)
    significant = [t for t in tokens if len(t) >= 2 and t.lower() not in stop_words]
    return significant[0] if significant else text.strip().rstrip("?.!")
