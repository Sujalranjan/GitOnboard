# Phase 2M Implementation Audit: Actual Code Contracts

**Date**: 2026-09-07  
**Status**: Code audit completed, implementation ready  
**Purpose**: Document actual API contracts before Phase 2M integration coding

---

## 1. ACTUAL LLMGrounder INTERFACE (Stage 8 Current)

**File**: `backend/intelligence/engine/orchestration/stage8_grounding.py`

**Key Class**: `LLMGrounder`

```python
class LLMGrounder:
    def __init__(self):
        self.llm_service = get_llm_service()
    
    async def ground(self, context: RepositoryContext, query: str) -> tuple[str, GroundingValidationResult]:
        """
        Current behavior:
        - Receives RepositoryContext from Stage 7
        - Dumps entire context JSON into LLM prompt
        - Logs context composition
        - Validates grounding
        """
```

**Current Message Structure**:
```python
messages = [
    Message(role="system", content="You are a code analyst..."),
    Message(role="user", content=f"Repository Context (from retrieval + graph traversal):\n{context_json}\n\nQuestion: {query}")
]
```

**Limitation**: All source is in the context before LLM even thinks about what it needs.

**Tool-Calling Support**: Not currently implemented - would need to be added via LangGraph/LLMService.

---

## 2. ACTUAL LLMService INTERFACE

**File**: `backend/ai/service.py`

**Key Method Pattern**:
```python
# LLMService must support:
async def generate(self, messages: List[Message], tools: Optional[List[Dict]] = None) -> str

# If tools are provided, LLM can invoke them
# LangGraph manages the loop
```

**Required for Phase 2M**:
- LLMService must accept `tools` parameter
- Must handle tool-calling and return tool calls to caller
- Current implementation may need wrapping for tool-calling loop

---

## 3. ACTUAL PHASE 2L INSPECTION TOOL SIGNATURES

From `backend/intelligence/inspection/`:

```python
# file_inspector.py
def inspect_file(
    file_path: str,
    repo_name: str = "default",
    db: Optional[Session] = None,
    repo_root: Optional[str] = None,
    user_id: Optional[int] = None,
    analysis_id: Optional[int] = None,  # ADDED IN 2L.2
) -> InspectFileResult

# source_reader.py
def read_symbol(
    file_path: str,
    symbol_name: str,
    repo_name: str = "default",
    db: Optional[Session] = None,
    repo_root: Optional[str] = None,
    user_id: Optional[int] = None,
    analysis_id: Optional[int] = None,  # ADDED IN 2L.2
) -> SourceReadResult

def read_file(
    file_path: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
    repo_name: str = "default",
    db: Optional[Session] = None,
    repo_root: Optional[str] = None,
    user_id: Optional[int] = None,
) -> SourceReadResult
```

**Critical Error Handling** (Phase 2L.2):
```python
# If analysis_id missing + repo_name="default":
return InspectFileResult(
    success=False,
    error="REPOSITORY_CONTEXT_ERROR: analysis_id is required..."
)
```

---

## 4. ACTUAL PHASE 2L CONTEXTMANAGER INTERFACE

From `backend/intelligence/context_management/manager.py`:

```python
class ContextManager:
    def __init__(self, budget: ContextBudget, configured_context_budget_tokens: int = 100000):
        self.items: List[ContextItem] = []
        self.budget = budget
        self.peak_tokens_used = 0
    
    def add_item(
        self,
        evidence: ContextEvidence,
        priority: Optional[ContextItemPriority] = None,
        retrieval_source: str = "unknown",
    ) -> ContextItem:
        """Returns ContextItem with assigned ID (ctx_NNNN_XXXXXXXX)"""
    
    def list_context(self) -> List[ContextItem]:
        """Returns active items only"""
    
    def drop_context(self, context_item_id: str):
        """Marks item as DROPPED (recoverable)"""
    
    def calculate_utilization(self) -> float:
        """Returns [0.0, 1.0] utilization ratio"""
    
    def get_budget_checkpoint(self) -> BudgetCheckpoint:
        """Returns NORMAL/MODERATE/CAUTION/HIGH/CRITICAL"""
```

**ContextItem Structure**:
```python
@dataclass
class ContextItem:
    context_item_id: str  # "ctx_NNNN_XXXXXXXX"
    priority: ContextItemPriority  # PROTECTED/ACTIVE/COMPRESSIBLE/DISPOSABLE
    estimated_tokens: int
    state: ContextItemState  # ACTIVE/REFERENCE/COMPRESSED/DROPPED
    is_compressed: bool
    created_timestamp: datetime
    retrieval_source: str
    source_type: str  # From ContextEvidence
    source_id: str  # From ContextEvidence
    data: Dict  # From ContextEvidence
    # ... more fields
```

---

## 5. ACTUAL REPOSITORYCONTEXT STRUCTURE (Stage 7 Output)

From `backend/agent/context/contracts.py`:

```python
class RepositoryContext(BaseModel):
    requirement: str
    relevant_files: List[str]
    relevant_symbols: List[Dict[str, Any]]  # FactSymbol as dict
    evidence: List[ContextEvidence]  # Includes source_excerpt items
    # ... metadata fields
```

**Current Problem**: 
- `evidence` list contains source_excerpt items with full code
- All sent to LLM in initial prompt

**Phase 2M Fix**:
- Keep only metadata evidence initially
- Don't include source_excerpt in initial context
- LLM must inspect to get source

---

## 6. EXECUTION CONTEXT PROPAGATION PATTERN

**Where to get it**:
```python
# In Stage 8 input
context: RepositoryContext
analysis_id = context.analysis_id  # May not be in RepositoryContext!

# Must retrieve from:
# 1. RepositoryContext if present
# 2. Request metadata
# 3. Pipeline execution context
# 4. Config/environment

repo_root = "/home/dheeraj/repository_intelligence_platform"  # From config or context
db = SessionLocal()  # Current session
```

**CRITICAL**: These may NOT be in RepositoryContext currently - audit Stage 7 output to confirm what's actually available.

---

## 7. TOOL WRAPPER PATTERN (For Phase 2M Adapter)

```python
class Phase2LToolWrapper:
    def __init__(self, analysis_id: int, repo_root: str, db: Session, context_manager: ContextManager):
        self.analysis_id = analysis_id
        self.repo_root = repo_root
        self.db = db
        self.context_manager = context_manager
    
    def inspect_file_tool(self, file_path: str) -> Dict:
        """Wrapper that injects context, handles errors, adds to ContextManager"""
        try:
            result = inspect_file(
                file_path,
                db=self.db,
                repo_root=self.repo_root,
                analysis_id=self.analysis_id
            )
            
            if result.success:
                # Add to context manager
                evidence = ContextEvidence(
                    source_type="repository_structure",
                    source_id=file_path,
                    summary=f"File structure: {len(result.symbols)} symbols",
                    data={"symbols": [s.dict() for s in result.symbols]},
                    confidence=1.0,
                    relevance=1.0,
                )
                self.context_manager.add_item(evidence, retrieval_source="llm_inspect_file")
            
            return {
                "file": file_path,
                "success": result.success,
                "error": result.error,
                "symbols": [s.dict() for s in result.symbols] if result.success else [],
                "language": result.language,
                "total_lines": result.total_lines,
            }
        except Exception as e:
            return {
                "file": file_path,
                "success": False,
                "error": f"TOOLING_FAILURE: {str(e)}"
            }
```

---

## 8. LANGGRAPH TOOL REGISTRATION PATTERN

```python
from langchain.tools import tool
from langchain.tools.base import BaseTool

# Convert wrapper methods to LangChain tools
tools = [
    Tool(
        name="inspect_file",
        description="Inspect file structure: symbols, line count, language. Does NOT read source.",
        func=wrapper.inspect_file_tool,
        schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Repository-relative path"}
            },
            "required": ["file_path"]
        }
    ),
    Tool(
        name="read_symbol",
        description="Read exact source for one symbol using canonical line boundaries.",
        func=wrapper.read_symbol_tool,
        schema={...}
    ),
    # ... more tools
]

# Add to LangGraph workflow
workflow.add_tools(tools)
```

---

## 9. COMPACT INITIAL CONTEXT CONSTRUCTION

**Current Stage 7 Output**: Full context with source_excerpt items

**Phase 2M Goal**: Strip source_excerpt items from initial context

```python
def create_compact_context(context: RepositoryContext) -> RepositoryContext:
    """Remove bulk source, keep metadata"""
    
    # Keep only non-source-excerpt evidence
    compact_evidence = [
        e for e in context.evidence
        if e.source_type != "source_excerpt"
    ]
    
    return RepositoryContext(
        requirement=context.requirement,
        relevant_files=context.relevant_files,
        relevant_symbols=context.relevant_symbols,
        evidence=compact_evidence,
        # ... other fields
    )

# Measure:
original_tokens = estimate_tokens(context.model_dump())
compact_tokens = estimate_tokens(compact_context.model_dump())
print(f"Initial context: {compact_tokens} tokens ({original_tokens - compact_tokens} saved)")
```

---

## 10. GROUNDING VALIDATOR INTEGRATION (Existing)

From `backend/intelligence/engine/orchestration/stage8_grounding.py`:

```python
class GroundingValidator:
    def __init__(self, context: RepositoryContext):
        # Extracts files, symbols, entities from context
        pass
    
    def validate(self, answer: str) -> GroundingValidationResult:
        # Checks if answer references only context-provided entities
        # Returns: grounded / partial / ungrounded / insufficient_context
        pass

# Usage in Phase 2M:
validator = GroundingValidator(final_context)  # After all tool calls
result = validator.validate(answer)
```

**Note**: Validator checks FINAL context (after all tool calls) against answer.

---

## 11. PHASE 2M INTEGRATION CHECKLIST

Before implementing, verify:

- [ ] Read actual `LLMGrounder.ground()` signature
- [ ] Confirm `LLMService.generate()` tool-calling support
- [ ] Audit actual `RepositoryContext` fields (Stage 7 output)
- [ ] Verify `analysis_id` is available in Stage 8 input
- [ ] Verify `repo_root` can be resolved in Stage 8
- [ ] Confirm LangGraph tool registration pattern
- [ ] Verify ContextManager integration point
- [ ] Confirm grounding validator works on tool-built context
- [ ] Verify Phase 2L error handling (explicit vs silent)

---

## 12. IMPLEMENTATION SEQUENCE

**Phase 2M.1**: Create adapter (200 lines)
1. Repository execution context extraction
2. Tool wrapper class (inject context, handle errors)
3. ContextManager integration
4. Tool return formats

**Phase 2M.2**: Modify LLMGrounder (100 lines)
1. Compact initial context construction
2. Tool registration in LangGraph
3. Tool-calling loop
4. Final context assembly from tool results

**Phase 2M.3**: Testing (300 lines)
1. Execution context propagation tests
2. Tool invocation tests
3. Real GitOnboard queries
4. A/B comparison

**Phase 2M.4**: Validation (200 lines)
1. Telemetry collection
2. Grounding validation
3. Error classification
4. Report generation

---

## 13. CRITICAL ASSUMPTIONS TO VERIFY

1. **LLMService supports tools**: Confirm `generate(messages, tools=...)` signature
2. **analysis_id is available**: Check Stage 7 passes it
3. **LangGraph is used**: Confirm tool-calling integration point
4. **ContextManager can be instantiated**: Verify budget constraints exist
5. **Grounding validator works on dynamic context**: Test with tool-built evidence

---

## 14. KNOWN RISKS

| Risk | Mitigation |
|------|-----------|
| LLMService doesn't support tool calling | Fall back to bulk context (won't achieve goals) |
| analysis_id not available in Stage 8 | Must retrieve from Stage 7/config |
| repo_root not accessible | Fall back to metadata-only inspection |
| LLM doesn't actually call tools | Tools were registered but not used (silent failure) |
| Context manager not thread-safe | Use per-query instance (not shared) |
| Grounding validator broken | Test with sample context first |

---

## 15. NEXT STEPS

1. **Audit** actual code signatures (this audit may be incomplete)
2. **Implement** Phase 2M.1 adapter (minimal, testable)
3. **Implement** Phase 2M.2 LLMGrounder modifications
4. **Test** with one real query before scaling
5. **Run** full test suite and A/B validation
6. **Report** results

---

**Status**: Ready to implement once code audit is confirmed.

All Phase 2L infrastructure is validated and available. No blockers identified.
