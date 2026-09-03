# Tracing RIM Usage Through the System

## How to Verify RIM is Being Used (Not the Old Code Path)

### Quick Verification
```bash
# Run the integration check
uv run python verify_rim_integration.py

# Expected: ✅ on all 8 checks
```

---

## Data Flow: From Code to Knowledge Graph

### 1. **Repository Analysis Entry Point**
```
worker.py: analyze_repository()
  └─> AnalysisEngine.run()
      └─> [NEW RIM PIPELINE]
```

**File**: `backend/intelligence/engine/orchestration/pipeline.py`

```python
def run(self, repo_name: str, commit_info: Optional[dict] = None) -> RepositoryModel:
    # 1. Scan Repository
    scanner = RepositoryScanner(self.target_dir)
    manifest = scanner.scan()
    
    # 2. Parse ASTs [PHASE 1: TREE-SITTER]
    parser_manager = ASTParserManager(self.target_dir)
    asts = parser_manager.parse_manifest(manifest)
    
    # 3. Execute Analyzers [PHASES 1-4]
    for analyzer in self.registry.get_all():
        analyzer.analyze(model, asts)
    
    return model
```

### 2. **AST Parsing (Phase 1)**
```
ASTParserManager.parse_file()
  └─> TypeScriptProvider.parse() [TREE-SITTER]
      ├─> tree_sitter.Parser()
      ├─> TypeScriptTreeSitterVisitor.visit()
      │   ├─> Extract functions/classes
      │   ├─> Extract methods
      │   └─> Extract imports
      └─> ParsedFile(metadata={'symbols': [...], 'imports': [...]})
```

**Files**:
- `backend/intelligence/engine/parser/providers/typescript.py`
- `backend/intelligence/engine/parser/manager.py`

**Key change**: Metadata now contains extracted symbols instead of synthetic dict.

### 3. **Symbol Analysis (Phase 1)**
```
SymbolAnalyzer.analyze()
  └─> For each parsed file:
      ├─> Extract symbols from metadata
      ├─> Create DECLARES relationships
      └─> Use SymbolIndex for fast lookup
```

**File**: `backend/intelligence/engine/analyzers/symbol.py`

**Key change**: Uses `parsed.metadata['symbols']` instead of synthetic AST dict.

### 4. **Import Analysis (Phase 1)**
```
ImportAnalyzer.analyze()
  └─> For each import in metadata:
      ├─> Resolve to canonical MODULE entity
      ├─> Create IMPORTS relationships
      └─> Enable cross-file queries
```

**File**: `backend/intelligence/engine/analyzers/imports.py`

**Key change**: Creates one MODULE per package (not per importer).

### 5. **Call Graph Analysis (Phase 1)**
```
CallGraphAnalyzer.analyze()
  └─> For TypeScript:
      ├─> Walk tree-sitter AST
      ├─> Find call_expression nodes
      ├─> Use resolve_reference() [4-strategy lookup]
      ├─> Create CALLS relationships
      └─> Extract JSX → RENDERS relationships [Phase 3]
  └─> For Python:
      ├─> Walk Python AST
      ├─> Create CALLS relationships
      └─> Extract INHERITS from base classes
```

**Files**:
- `backend/intelligence/engine/analyzers/callgraph.py`
- `backend/intelligence/engine/analyzers/resolution.py`

**Key changes**: 
- Multi-strategy symbol resolution
- Cross-file CALLS
- JSX/RENDERS extraction

### 6. **Uses Analysis (Phase 2)**
```
UsesAnalyzer.analyze()
  └─> For each function/class:
      ├─> Find property access (obj.prop)
      ├─> Create USES relationships
      ├─> Extract type annotations
      └─> Create REFERENCES relationships
```

**File**: `backend/intelligence/engine/analyzers/uses.py`

### 7. **Route Analysis (Phase 4)**
```
RouteAnalyzer.analyze()
  └─> For TypeScript files:
      ├─> Check if matches Next.js patterns
      ├─> Extract route path from filename
      ├─> Create ROUTE entities
      └─> Create EXPOSES relationships
```

**File**: `backend/intelligence/engine/analyzers/route.py`

**Key change**: Added NextJsRouteExtractor for file-based routing.

### 8. **Fact Store Persistence**
```
save_rim_to_fact_store()
  └─> Convert RIM entities/relationships to:
      ├─> FactSymbol (functions, classes, etc.)
      ├─> FactFile
      ├─> FactRoute [NEW]
      ├─> FactRelationship [NEW - includes CALLS, USES, RENDERS]
      └─> PostgreSQL
```

**File**: `backend/intelligence/store/fact_store.py`

---

## How to Trace the Flow

### Option 1: Add Debug Logging
Edit `backend/intelligence/engine/analyzers/callgraph.py`:

```python
class CallGraphAnalyzer(BaseAnalyzer):
    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        print(f"[DEBUG] CallGraphAnalyzer: Processing {len(asts)} files")
        
        for file_path, parsed in asts.items():
            print(f"[DEBUG] Analyzing {file_path} ({parsed.language})")
            # ... rest of logic
```

### Option 2: Check Docker Logs
```bash
docker compose logs backend | grep -E "CallGraphAnalyzer|UsesAnalyzer|RouteAnalyzer"
```

### Option 3: Query the Database
```sql
-- Check if relationships are being saved
SELECT type, COUNT(*) FROM fact_relationships 
WHERE analysis_id = <your_analysis_id>
GROUP BY type
ORDER BY COUNT(*) DESC;

-- Expected output shows: CALLS, USES, RENDERS, etc.
```

### Option 4: Use the Verification Script
```bash
uv run python verify_rim_integration.py
```

---

## Comparing Old vs New Behavior

### OLD CODE PATH (Pre-Enhancement)
```
Files → Regex parsing → Basic entities (DECLARES, IMPORTS only)
  ↓
Limited retriever expansion
  ↓
Shallow context (no CALLS, no USES, no RENDERS)
```

### NEW CODE PATH (Current)
```
Files → Tree-sitter parsing → Rich entities + relationships
  ├─ DECLARES (file → symbol)
  ├─ IMPORTS (file → module)
  ├─ CALLS (cross-file function calls)
  ├─ USES (property access)
  ├─ RENDERS (component hierarchy)
  ├─ REFERENCES (type annotations)
  ├─ INHERITS (class inheritance)
  └─ EXPOSES (route handlers)
  ↓
Advanced retriever expansion via FactStoreExpander
  ↓
Rich context (full feature-level understanding)
```

---

## Key Evidence That RIM is Active

### 1. **Tree-Sitter is Parsing**
Look in logs for:
```
[DEBUG] TypeScriptProvider: Parsing with tree-sitter
[DEBUG] Extracted 5 symbols from test.tsx
```

### 2. **Analyzers Are Running**
Check that these are called:
```python
- SymbolAnalyzer ✓
- ImportAnalyzer ✓
- CallGraphAnalyzer ✓ [Phase 1]
- UsesAnalyzer ✓ [Phase 2]
- RouteAnalyzer ✓ [Phase 4]
```

### 3. **Relationships Are Created**
Database should show:
```
CALLS: 50+
DECLARES: 100+
USES: 20+
RENDERS: 5+
INHERITS: 10+
```

### 4. **Cross-File Resolution Works**
Query returns symbols from different files:
```sql
SELECT source_id, target_id FROM fact_relationships
WHERE type = 'CALLS' AND source_id LIKE '%foo.ts%' AND target_id LIKE '%bar.ts%';
```

### 5. **FactStoreExpander Uses New Relationships**
In `backend/intelligence/retrieval/expansion.py`, look for:
```python
# Expansion using CALLS/USES/RENDERS
for rel in db.query(FactRelationship).filter(
    FactRelationship.source_id == candidate_id
).all():
```

---

## Testing RIM in Production

### Test 1: Query with RIM
```bash
# Query that benefits from cross-file relationships
Question: "How are users authenticated in this app?"

Expected: Returns not just authenticate() function, but also:
- login() which calls authenticate()
- Login component which calls authenticate()
- API route which calls authenticate()
- All connected via CALLS and RENDERS relationships
```

### Test 2: Compare RIM vs No-RIM
```bash
# Disable RIM (comment out analyzers)
Result A: Only direct symbol matches

# Enable RIM (current)
Result B: Direct matches + callers + callees + renderers + type info

# Expect: Result B has 3-5x more relevant context
```

### Test 3: Verify Expansion Works
```python
# In expansion.py, check logs
LOG: "Expanding candidate 'authenticate'..."
LOG: "  Found 3 callers via CALLS relationships"
LOG: "  Found 2 components rendering related code via RENDERS"
```

---

## Verification Checklist

Use this to ensure RIM is active:

- [ ] `verify_rim_integration.py` passes all 8 checks
- [ ] `CallGraphAnalyzer` is in `get_default_registry()`
- [ ] `UsesAnalyzer` is in `get_default_registry()`
- [ ] `RouteAnalyzer` supports TypeScript (Next.js)
- [ ] `TypeScriptProvider` uses `tree_sitter` (not regex)
- [ ] `ParsedFile.metadata` contains `symbols` and `imports`
- [ ] `SymbolIndex` is imported in callgraph.py
- [ ] `RelationshipType.CALLS` is used in callgraph.py
- [ ] `RelationshipType.RENDERS` is used in callgraph.py
- [ ] Database has `fact_relationships` with CALLS/USES/RENDERS
- [ ] Fact store queries include relationship expansion
- [ ] Retriever expansion mentions "structural expansion"

---

## Commits That Prove RIM is in Use

```bash
# Phase 1: Tree-sitter + cross-file resolution
git show 9861563 | grep -E "tree.sitter|resolve_reference|CallGraphAnalyzer"

# Phase 2: USES/REFERENCES
git show db9b53a | grep -E "UsesAnalyzer|USES"

# Phase 3: RENDERS
git show e851534 | grep -E "RENDERS|jsx_element"

# Phase 4: Routes
git show dc86df5 | grep -E "RouteAnalyzer|NextJsRouteExtractor"
```

---

## Summary

The RIM system is **fully integrated** and will be used for:

1. ✅ **Parsing**: Tree-sitter (not regex)
2. ✅ **Symbol extraction**: From AST metadata
3. ✅ **Relationship discovery**: Via analyzers
4. ✅ **Cross-file resolution**: Via SymbolIndex
5. ✅ **Graph storage**: To FactStore
6. ✅ **Query expansion**: Via FactStoreExpander
7. ✅ **Context retrieval**: Via HybridRetriever

**The old regex-based, shallow-graph code path is completely replaced.**
