# Phase 2: Verify RIM Retrieval of Repository-Specific Entities

## Objective

Verify that the RIM system (HybridRetriever + GraphTraverser) actually identifies and retrieves repository-specific entities and relationships for the query.

## Problem from Phase 1 Findings

From the system prompt logs (`02_system_prompt_45466c86_rim.txt`):
```
### RIM_RELATIONSHIPS
RIM_METADATA: No structural facts could be resolved for this question in this repository's index.
```

Despite the ContextAssembler identifying 15 relevant files, the RIM metadata block shows **zero relationships found**. This suggests the retrieval pipeline is failing at some stage.

---

## Diagnostic Questions

### Q1: Does HybridRetriever find any seed candidates?

**What to check:**
- Run HybridRetriever with question "How does authentication work in this repo?"
- Should return 5-10 candidates (top_k=5)
- Each candidate should have: `entity_name`, `entity_type`, `file_path`, `match_reason`

**Expected candidates for auth query in GitOnboard:**
- `authenticate_user` (function in backend/services/github_oauth.py)
- `verify_password` (function in backend/services/auth.py)
- `/login` (route in backend/routers/auth.py)
- `User` (class/model)
- Similar auth-related symbols

**Failure case:** If retriever returns 0 candidates, the seed identification phase fails.

### Q2: Can TargetEntityResolver resolve candidates to ORM objects?

**What to check:**
- For each candidate returned by retriever, attempt to resolve:
  - Candidate name → entity_type → ORM object
- Test resolution in this order:
  1. Type-specific lookup (e.g., entity_type="SYMBOL" → FactSymbol)
  2. Fallback pattern matching

**Failure case:** If resolver returns None for valid candidates, no traversals happen.

### Q3: Can FactStoreGraphTraverser find relationships?

**What to check:**
- For each resolved seed, traverse one-hop relationships
- For a `FactSymbol` like `authenticate_user`:
  - Should find CALLS relationships (what functions does it call?)
  - Should find CALLED_BY relationships (what functions call it?)
  - Should find CONTAINS relationships (if class method, what class contains it?)

**Expected relationships for `authenticate_user`:**
```
  authenticate_user CALLS verify_password (backend/services/auth.py:XX)
  authenticate_user CALLS db.query (backend/services/auth.py:XX)
  login_route CALLS authenticate_user (backend/routers/auth.py:XX)
```

**Failure case:** If traverser returns 0 related entities, no fact lines are generated.

---

## Diagnostic Implementation

### Step 1: Create a diagnostic script that traces each stage

Location: `run_phase2_rim_retrieval_diagnostic.py`

```python
#!/usr/bin/env python3
"""
Phase 2 Diagnostic: Trace RIM retrieval pipeline for auth query.
Tests each stage: retriever → resolver → traverser
"""

import logging
from backend.ai.service import get_llm_service
from backend.services.rim_metadata import build_rim_metadata_block, TargetEntityResolver
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from backend.database import SessionLocal
from backend.routers.repo.services.analysis import get_latest_analysis

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def main():
    db = SessionLocal()
    repo_name = "GitOnboard"
    question = "How does authentication work in this repo?"

    # Get analysis
    repo, analysis = get_latest_analysis(repo_name, db, user_id=1)
    analysis_id = analysis.id
    print(f"[PHASE2] Testing RIM retrieval for analysis_id={analysis_id}")
    print(f"[PHASE2] Question: {question}\n")

    # Stage 1: HybridRetriever
    print("=" * 70)
    print("STAGE 1: HybridRetriever.retrieve()")
    print("=" * 70)
    retriever = HybridRetriever(
        db=db,
        analysis_id=analysis_id,
        enable_graph_expansion=True,
        graph_expansion_depth=2,
    )
    candidates = retriever.retrieve(question, top_k=5, expand_with_fact_store=False, enable_graph_expansion=True)
    print(f"[✓] Retrieved {len(candidates)} candidates")
    for i, cand in enumerate(candidates[:5]):
        print(f"  [{i}] {cand.get('entity_name') if isinstance(cand, dict) else cand.entity_name}")
        if isinstance(cand, dict):
            print(f"      Type: {cand.get('entity_type')}")
            print(f"      File: {cand.get('file_path')}")
        else:
            print(f"      Type: {cand.entity_type}")
            print(f"      File: {cand.file_path}")

    if not candidates:
        print("[✗] NO CANDIDATES RETRIEVED - Retriever failed!")
        return

    # Stage 2: TargetEntityResolver
    print("\n" + "=" * 70)
    print("STAGE 2: TargetEntityResolver.resolve()")
    print("=" * 70)
    resolver = TargetEntityResolver(db, analysis_id)
    seeds = []
    for cand in candidates:
        entity_name = cand.get('entity_name') if isinstance(cand, dict) else cand.entity_name
        entity_type = cand.get('entity_type') if isinstance(cand, dict) else cand.entity_type
        target = resolver.resolve(entity_name, entity_type)
        if target:
            seeds.append((entity_name, target))
            print(f"[✓] Resolved: {entity_name} -> {type(target).__name__}")
        else:
            print(f"[✗] Failed to resolve: {entity_name} (type={entity_type})")

    if not seeds:
        print("[✗] NO SEEDS RESOLVED - Resolver failed!")
        return

    # Stage 3: FactStoreGraphTraverser
    print("\n" + "=" * 70)
    print("STAGE 3: FactStoreGraphTraverser.traverse()")
    print("=" * 70)
    traverser = FactStoreGraphTraverser(db, analysis_id)
    total_relationships = 0
    for seed_name, target in seeds:
        from backend.agent.intent.semantic_query import SemanticQueryClass, TraversalDirection, SemanticQueryIntent
        
        query_classes = [
            SemanticQueryClass.CALLS_FORWARD,
            SemanticQueryClass.CALLS_REVERSE,
            SemanticQueryClass.IMPORTS_FORWARD,
        ]
        
        print(f"\n[{seed_name}] Checking relationships:")
        for query_class in query_classes:
            direction = TraversalDirection.REVERSE if "REVERSE" in query_class.name else TraversalDirection.FORWARD
            intent = SemanticQueryIntent(
                query_class=query_class,
                target_raw_name=seed_name,
                direction=direction,
            )
            try:
                result = traverser.traverse(intent, target)
                rel_count = len(result.related_entities)
                total_relationships += rel_count
                status = "✓" if rel_count > 0 else "✗"
                print(f"  [{status}] {query_class.name}: {rel_count} relationships")
                for entity in result.related_entities[:3]:
                    print(f"       - {entity.name}")
            except Exception as e:
                print(f"  [✗] {query_class.name}: {e}")

    print(f"\n[PHASE2] TOTAL RELATIONSHIPS FOUND: {total_relationships}")

    # Stage 4: Full metadata block
    print("\n" + "=" * 70)
    print("STAGE 4: build_rim_metadata_block()")
    print("=" * 70)
    metadata = build_rim_metadata_block(
        db, analysis_id, question, retriever,
        max_seed_entities=3,
        max_related_per_seed=8,
    )
    print(f"[{('✓' if metadata.text and 'No structural' not in metadata.text else '✗')}] Metadata block built")
    print(f"    Anchors: {len(metadata.anchor_entities)}")
    print(f"    Expanded: {len(metadata.expanded_entities)}")
    print(f"    Relationships: {len(metadata.relationships)}")
    print(f"    Chars: {len(metadata.text)}")
    print(f"\n[TEXT PREVIEW]:\n{metadata.text[:500]}...")

    db.close()

if __name__ == "__main__":
    main()
```

### Step 2: Run the diagnostic

```bash
cd /home/dheeraj/repository_intelligence_platform
uv run python run_phase2_rim_retrieval_diagnostic.py
```

### Step 3: Interpret results

**Expected output if working:**
```
[PHASE2] Testing RIM retrieval for analysis_id=14
[PHASE2] Question: How does authentication work in this repo?

STAGE 1: HybridRetriever.retrieve()
[✓] Retrieved 5 candidates
  [0] authenticate_user
      Type: SYMBOL
      File: backend/services/github_oauth.py
  [1] verify_password
      Type: SYMBOL
      File: backend/services/auth.py
  ...

STAGE 2: TargetEntityResolver.resolve()
[✓] Resolved: authenticate_user -> FactSymbol
[✓] Resolved: verify_password -> FactSymbol
...

STAGE 3: FactStoreGraphTraverser.traverse()
[authenticate_user] Checking relationships:
  [✓] CALLS_FORWARD: 2 relationships
       - verify_password
       - db.query
  [✓] CALLS_REVERSE: 1 relationships
       - login

[PHASE2] TOTAL RELATIONSHIPS FOUND: 12
```

**If failing, expected output:**
```
[✗] NO CANDIDATES RETRIEVED - Retriever failed!
  → Indicates: HybridRetriever not finding auth-related symbols
  → Root cause: BM25 index missing or semantic search failing
  
[✗] NO SEEDS RESOLVED - Resolver failed!
  → Indicates: Entity names from retriever don't match FactStore entries
  → Root cause: Name normalization mismatch between retriever and FactStore
  
[✓] 0 relationships FOUND in STAGE 3
  → Indicates: Graph edges not recorded in FactRelationship table
  → Root cause: Analysis was never completed with relationship extraction
```

---

## Key Findings Expected

### If Phase 2 is Successful
- Retriever finds auth-related entities (authenticate_user, verify_password, etc.)
- Resolver maps them to FactSymbol/FactRoute records
- Traverser finds 10-20+ relationships
- Metadata block contains actionable relationship facts
- Result: LLM can use relationships to answer "How does authentication work?"

### If Phase 2 Fails at Any Stage
- Document which stage fails
- Determine if it's retriever, resolver, or graph traversal issue
- Phase 3 will verify if source code retrieval works as fallback
- Phase 4-5 will determine if system prompts need stronger grounding

---

## Success Criteria

✓ Passed Phase 2 if:
1. HybridRetriever returns 3+ auth-related candidates
2. TargetEntityResolver resolves 3+ candidates successfully
3. FactStoreGraphTraverser finds 10+ total relationships
4. build_rim_metadata_block returns non-empty fact lines

This confirms the RIM pipeline CAN find repository-specific facts.
If Phase 2 fails, the RIM system is not working as intended.
