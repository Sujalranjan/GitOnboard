# Phase 2M: Stage 8 Integration Plan

**Date**: 2026-09-07  
**Status**: PLANNING  
**Scope**: Integrate Phase 2L inspection tools into Stage 8 LLM interaction

---

## Current State Analysis

### Existing Stage 8 Architecture

**LLMGrounder** (stage8_grounding.py):
- Receives `RepositoryContext` from Stage 7
- Logs context composition
- Builds messages for LLMService
- Validates grounding of LLM answer

**Current Context Flow**:
```
Stage 7 ContextAssembler
    ↓
RepositoryContext (all files + symbols + code)
    ↓
Stage 8 LLMGrounder
    ↓
Full context → LLM
    ↓
Answer + Grounding validation
```

**Problem with Current**:
- All source is sent upfront (bulk context)
- LLM has no tool to request additional information
- No interactive exploration

### Phase 2L Integration Point

**New Flow**:
```
Stage 7 ContextAssembler
    ↓
Repository Candidates (files + symbols, NO full source)
    ↓
Stage 8 LLM with Tools
    ├→ inspect_file()
    ├→ read_symbol()
    ├→ read_file()
    ├→ list_context()
    ├→ drop_context()
    └→ summarize_context()
    ↓
LLM decision: what source to read
    ↓
Interactive exploration
    ↓
Context management (budget, priorities)
    ↓
Final grounded answer
```

---

## Integration Points Required

### 1. Repository Execution Context

At Stage 8 start, establish:

```python
# Stage 8 receives
analysis_id: int        # from Stage 7/context
repo_root: str         # from config/repository
db: Session            # from context

# Pass to all Phase 2L tools
inspect_file(..., analysis_id=analysis_id, repo_root=repo_root)
read_symbol(..., analysis_id=analysis_id, repo_root=repo_root)
```

### 2. Initial Context (Compact)

Instead of sending all source, send:

```json
{
    "requirement": "How does login work?",
    "relevant_files": ["backend/routers/auth.py", "backend/services/..."],
    "relevant_symbols": [{"name": "login_route", "file": "..."}],
    "evidence": [
        {
            "type": "rim_fact",
            "summary": "login_route calls authenticate()"
        }
    ]
}
```

**NO source excerpts in initial context.**

LLM must inspect what it needs.

### 3. Tool Registration

In LangGraph, add tools:

```python
tools = [
    Tool(
        name="inspect_file",
        description="Get file structure: symbols, line counts, language",
        func=lambda path: inspect_file(
            path,
            db=db,
            repo_root=repo_root,
            analysis_id=analysis_id
        ),
        schema={...}
    ),
    Tool(
        name="read_symbol",
        description="Get exact source for one symbol",
        func=lambda file, symbol: read_symbol(
            file, symbol,
            db=db,
            repo_root=repo_root,
            analysis_id=analysis_id
        ),
        schema={...}
    ),
    ...
]
```

### 4. Context Manager Integration

```python
context_manager = ContextManager(budget=context_budget)

# When LLM reads source
source_result = read_symbol(...)
context_manager.add_item(
    evidence=ContextEvidence(
        source_type="source_excerpt",
        source_id=f"{file}:{symbol}",
        data={"content": source_result.source},
        ...
    ),
    retrieval_source="llm_tool_inspection"
)

# Monitor pressure
utilization = context_manager.calculate_utilization()
if utilization > 0.85:
    # Consider dropping low-value items
    low_value = [...]
    context_manager.drop_context(low_value)
```

### 5. Grounding Validation

Existing grounding validator works but needs update:

```python
grounding = GroundingValidator(context)
result = grounding.validate(answer)

# Check that files/symbols referenced in answer are actually in context
# (already implemented in Stage 8)
```

---

## Implementation Steps

1. **Create Stage 8 Phase 2L adapter**
   - Extract repository execution context from Stage 7
   - Create tool wrappers that inject context

2. **Modify LLMGrounder**
   - Create compact initial context
   - Register Phase 2L tools in LangGraph
   - Integrate ContextManager

3. **Update tool descriptions**
   - Clear guidance on inspect vs read
   - Examples of tool usage

4. **Test integration**
   - Real GitOnboard queries
   - Tool invocation tracking
   - Context metrics

5. **Validate grounding**
   - Existing validator
   - Check that answers reference inspected source

---

## Files to Create/Modify

**New**:
- `backend/intelligence/engine/orchestration/stage8_phase2l_adapter.py` - Tool wrapper + context management

**Modified**:
- `backend/intelligence/engine/orchestration/stage8_grounding.py` - Add tool support

**Tests**:
- `backend/tests/phase2m/test_stage8_integration.py` - Real GitOnboard queries

---

## Validation Queries

Real GitOnboard questions to test:

1. "How does login work?"
   - Expected: Trace auth.py → oauth → user model

2. "Where does repository analysis start?"
   - Expected: scanner → pipeline → stages

3. "Explain retrieval implementation"
   - Expected: retriever → lexical/semantic → ranking

4. "How does frontend trigger scanning?"
   - Expected: UI component → API → backend

5. "Explain authentication mechanisms"
   - Expected: Multi-file flow (login, JWT, OAuth, middleware)

---

## Success Criteria

✅ Tools are actually callable by LLM
✅ Tools receive analysis_id and repo_root reliably
✅ Initial context is compact (no bulk source)
✅ LLM can explore repository interactively
✅ Source is only read when tool invoked
✅ Context manager tracks utilization
✅ Answers are grounded in inspected source
✅ All 5 validation queries produce correct answers
✅ No regressions in existing tests

---

## Timeline

Phase 2M should:
- Not redesign existing systems
- Minimal changes to Stage 8
- Work with existing LLMService
- Reuse existing grounding validator
- Add Phase 2L as opt-in tool layer

Estimated scope: 200-300 lines of new code + test suite.
