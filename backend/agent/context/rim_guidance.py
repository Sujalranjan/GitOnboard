"""
RIM LLM Guidance: System prompt sections for teaching LLMs to interpret and use RIM metadata.

Provides reusable, focused prompt sections that explain:
- What anchors and expanded entities are
- How relationship direction works
- Graph distance significance
- When to trust anchors vs expanded entities
- Negative query safety constraints
"""

# Section A: Understanding Repository Relationships (Anchors & Expansion)
RIM_ANCHOR_AND_EXPANSION_GUIDANCE = """
### Understanding Repository Relationships and Context

When analyzing code, you have access to repository relationship and impact metadata (RIM):

**Anchors:** Direct matches to your query. These are the strongest relevance signals.
Example: Query "predict_images" → Anchor is the predict_images symbol itself at its definition location.

**Expanded Entities:** Symbols connected to anchors through repository relationships
(functions that call predict_images, functions that predict_images calls, classes it belongs to, etc.).
These provide connected context but are less directly relevant than anchors.

**Relationship Types:**
- CALLS: Function A calls Function B (A invokes/triggers B)
- IMPORTS: Module A imports Module B (A depends on B's public interface)
- CONTAINS: Class A contains Method B (B is a member of A)
- INHERITS: Class A inherits from Class B (A is a subclass of B)
- ACCESSES: Code A accesses Database Table/Model B

**Graph Distance:**
- Distance 0 = Anchor (direct match, source of query)
- Distance 1 = Directly connected (single hop: immediate callers/callees, imports, members)
- Distance 2+ = Multiple hops away (weaker connection, provides broader context)

**Priority Rules:**
1. Prefer anchors and distance-1 entities over more distant relationships.
2. When multiple entities exist at same distance, prefer those most closely aligned with query intent.
3. Expanded entities provide architectural context; use them to explain broader impact and dependencies.
"""

# Section B: Using RIM Context for Positive Queries
RIM_POSITIVE_QUERY_GUIDANCE = """
### Using Repository Relationships for "How" and "What" Questions

For questions about how code works, dependencies, and architecture ("How does X flow?", "What does X depend on?", "Who calls X?"):

1. **Start with the anchor entity** - Begin your explanation from the direct match to the user's query
2. **Follow relationships clearly** - Use expanded entities to show connected code flow
3. **Explain relationship direction precisely**:
   - Use exact phrasing: "X calls Y" (not "X and Y interact")
   - Use exact phrasing: "X imports Y" (not "X uses Y")
   - Preserve direction: "A calls B" means A initiates B, not vice versa
4. **Cite distance** when relevant - Note when you're using distance-1 vs distance-2+ relationships
5. **Use expanded entities for architecture** - Show how the anchor fits into larger patterns and subsystems

Example:
  Question: "What does authenticate_user call?"
  Approach: Find authenticate_user (anchor), then list all distance-1 CALLS relationships
  Response: "authenticate_user calls jwt.encode (line X), validate_password (line Y), and database.query (line Z)"
"""

# Section C: Negative Query Safety (CRITICAL)
RIM_NEGATIVE_QUERY_GUIDANCE = """
### Critical: Negative Queries and Absence Claims

For questions about absence and non-existence ("Does system have X?", "Is feature Y implemented?", "Does code use Z?"):

**RULES:**
1. **Expanded entities do NOT prove a feature exists** - Just because related code exists doesn't mean the requested feature is implemented
2. **Lack of retrieval results does NOT prove absence** - Missing results may indicate gaps in repository analysis, not feature absence
3. **Only direct repository evidence confirms** - Code mentions, implementations, configurations, and explicit references count as evidence
4. **When evidence is limited, express uncertainty** - Say "Repository evidence is insufficient to confirm X" rather than inferring absence

**DO NOT DO:**
- Infer feature implementation from expanded context ("Related code exists, so feature must work")
- Claim absence based on negative retrieval ("No results found, so feature doesn't exist")
- Fabricate implementation details to fill gaps in evidence

**EXAMPLES:**

  Question: "Does system support WebSocket connections?"

  WRONG: "No mention of WebSocket found in symbols, so system doesn't support it" (fabricated absence)
  RIGHT: "Repository analysis found no direct WebSocket implementation (search, imports, or configurations)"
         + "If WebSocket support exists, it may be through external libraries not directly referenced in code"

  Question: "Does authentication use OAuth2?"

  WRONG: "Found auth-related code, so OAuth2 must be implemented" (fabricated from expanded context)
  RIGHT: "Direct search found no OAuth2 references or imports. System implements custom JWT-based authentication"
         + "OAuth2 support is not evidenced in the current codebase"

**Negative Query Decision Tree:**
1. Search for direct evidence (imports, function calls, configuration keys, comments mentioning feature)
2. If found: "Yes, X is implemented at [location]"
3. If NOT found: "Repository evidence does not show X. Consider: missing analysis, feature disabled, external library"
4. Never infer implementation from expanded context alone
"""

# Section D: Anchor Priority and Ambiguity
RIM_ANCHOR_PRIORITY_GUIDANCE = """
### Resolving Ambiguity: Anchor Priority

When multiple interpretations or matches exist:

1. **Prefer direct anchors** - When query matches multiple symbols, prefer exact name/scope matches
2. **Prefer distance-1 over distance-2+** - Relationships one hop away matter more than distant connections
3. **Note when ambiguous** - When query could mean multiple things, acknowledge it:
   - "query 'authenticate' matches 3 functions: authenticate_user (line X), authenticate_token (line Y), and authenticate_api_key (line Z)"
   - "Most likely match: authenticate_user (exact name match)"
4. **Ask for clarification indirectly** - In text response, suggest specific matches the user might have meant

Example:
  Question: "What does auth do?"
  Response: "Found 7 functions with 'auth' in name. Most likely target: `auth()` function in auth.py (line X)
             Other candidates: authenticate_user(), authenticate_token(), check_auth_header() - let me know if you meant a different one"
"""

# Section E: Relationship Direction Precision
RIM_RELATIONSHIP_DIRECTION_GUIDANCE = """
### Critical: Maintaining Relationship Direction

Repository relationships have explicit directionality. Preserve direction in your explanations:

**CALLS relationships:**
- "A CALLS B" means: A invokes/triggers B (A is caller, B is callee)
- NOT: "A and B are related" or "A uses B"
- Direction matters: CALLS(foo, bar) ≠ CALLS(bar, foo)

**IMPORTS relationships:**
- "A IMPORTS B" means: A depends on B's public interface (A requires B)
- NOT: "A and B are connected" or "they share functionality"
- Direction matters: IMPORTS(service, database) means service depends on database

**CONTAINS relationships:**
- "A CONTAINS B" means: B is a member/field/method of A
- Direction: Always from class/parent to member/child

**When Describing Call Chains:**
- Correct: "main() calls process(), which calls validate()"
- Wrong: "main, process, and validate interact" or "validate is called in the chain"

**Test Your Understanding:**
1. If user asks "Who calls X?" → Answer with all distance-1 CALLS(?, X) relationships
2. If user asks "What does X call?" → Answer with all distance-1 CALLS(X, ?) relationships
3. Never reverse the order unless explicitly stated
"""

# Section F: When RIM Metadata May Not Be Present
RIM_FALLBACK_GUIDANCE = """
### Using the System Without RIM Metadata

Some queries or repository states may not have RIM metadata available. In these cases:

1. Fall back to direct source code analysis
2. Use basic static text search when RIM data is unavailable
3. Be explicit about the limitation: "Relationship metadata not available for this repository; based on source code text search"
4. Do NOT fabricate relationship data to compensate for missing metadata

Indicator that RIM is unavailable: Response context will be minimal or marked as "No relationship metadata"
"""


def get_rim_guidance_for_system_prompt(
    include_sections: list[str] | None = None,
    max_chars: int = 3000,
) -> str:
    """
    Build a complete RIM guidance section for LLM system prompts.

    Args:
        include_sections: List of section keys to include.
            Options: 'anchor', 'positive', 'negative', 'priority', 'direction', 'fallback', 'all'
            Default: ['anchor', 'positive', 'negative', 'priority', 'direction']
        max_chars: Maximum character limit for output

    Returns:
        Formatted prompt section ready for system prompt injection
    """
    if include_sections is None or include_sections == ['all']:
        include_sections = ['anchor', 'positive', 'negative', 'priority', 'direction', 'fallback']

    section_map = {
        'anchor': RIM_ANCHOR_AND_EXPANSION_GUIDANCE,
        'positive': RIM_POSITIVE_QUERY_GUIDANCE,
        'negative': RIM_NEGATIVE_QUERY_GUIDANCE,
        'priority': RIM_ANCHOR_PRIORITY_GUIDANCE,
        'direction': RIM_RELATIONSHIP_DIRECTION_GUIDANCE,
        'fallback': RIM_FALLBACK_GUIDANCE,
    }

    selected_sections = [
        section_map[key] for key in include_sections
        if key in section_map
    ]

    text = "\n\n".join(selected_sections)

    # Enforce character limit
    if len(text) > max_chars:
        text = text[:max_chars]
        text = text.rsplit("\n", 1)[0]  # Remove partial line
        text += f"\n\n[RIM Guidance truncated to {max_chars} chars]"

    return text


def format_rim_metadata_for_prompt(
    anchors: list[dict],
    expanded: list[dict] | None = None,
    max_items: int = 15,
) -> str:
    """
    Format RIM metadata (anchors and expanded entities) for LLM context injection.

    Args:
        anchors: List of anchor entities with name, type, file_path, line_start
        expanded: List of expanded entities with distance_from_anchor, rel_type, relationship_role
        max_items: Maximum total entities to include

    Returns:
        Formatted text block suitable for LLM user context
    """
    lines = []
    lines.append("### REPOSITORY RELATIONSHIP METADATA")
    lines.append("")

    # Anchors section
    if anchors:
        lines.append(f"**ANCHORS (Direct Matches) - {len(anchors)} found:**")
        for anchor in anchors[:min(3, max_items)]:
            name = anchor.get('name', '?')
            sym_type = anchor.get('type', 'unknown')
            file_path = anchor.get('file_path', '?')
            line = anchor.get('line_start', '?')
            lines.append(f"  [ANCHOR] {name} ({sym_type}) in {file_path}:{line}")
        lines.append("")

    # Expanded entities section
    if expanded:
        lines.append(f"**EXPANDED ENTITIES (Connected via Relationships) - {len(expanded)} found:**")

        # Group by distance for clarity
        by_distance = {}
        for entity in expanded:
            dist = entity.get('distance_from_anchor', 99)
            by_distance.setdefault(dist, []).append(entity)

        items_shown = 0
        for distance in sorted(by_distance.keys()):
            if items_shown >= max_items:
                break

            entities = by_distance[distance]
            lines.append(f"\n  Distance {distance}:")

            for entity in entities[:3]:  # Max 3 per distance
                if items_shown >= max_items:
                    break

                name = entity.get('name', '?')
                sym_type = entity.get('type', '?')
                rel_type = entity.get('rel_type', 'UNKNOWN')
                role = entity.get('relationship_role', '')
                file_path = entity.get('file_path', '?')
                line = entity.get('line_start', '?')

                role_str = f" ({role})" if role else ""
                lines.append(f"    {rel_type}: {name} ({sym_type}) in {file_path}:{line}{role_str}")
                items_shown += 1

        if len(expanded) > max_items:
            lines.append(f"\n  ... and {len(expanded) - max_items} more entities")
        lines.append("")

    lines.append("**Use anchors as primary evidence. Use expanded entities for architectural context.**")

    return "\n".join(lines)
