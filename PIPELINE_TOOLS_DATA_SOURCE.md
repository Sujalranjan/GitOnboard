# Pipeline Tools 1-4: Data Sources & Repo Resolution

## How Repos Are Identified (ALL 4 TOOLS)

**Function:** `resolve_repository(repo_name, db, current_user)`  
**Location:** `/backend/routers/repo/services/analysis.py:7-56`

**Resolution Strategy (in order):**
1. **Repository ID (integer)** - Direct match: `repo.id == int(repo_name)`
2. **Exact URL match** - Full GitHub URL: `repo.url == repo_name`
3. **Slug suffix match** - Last part of URL: `repo.url.endswith(f"/{repo_name}")`
4. **User filtering** - Only repos where `repo.user_id == current_user.id`

**Example Resolutions:**
```
repo_name="1"              → Repository with id=1
repo_name="GitOnboard"     → Repository URL ending in "/GitOnboard"
repo_name="https://github.com/user/repo"  → Exact URL match
```

**Ambiguity Handling:**
- Returns HTTPException 400 if multiple matches
- Returns HTTPException 404 if no matches

---

## Tool #1: Symbol Inspection

**File:** `/backend/intelligence/inspection/symbol_inspector.py`

**Function:** `inspect_symbol(file_path, symbol_name, repo_name, db, user_id)`

### Data Source Chain:
```
1. resolve_repository(repo_name)
   ↓ Gets Repository object
2. RepositoryToolLayer.__init__
   ├─ analysis_id = latest completed Analysis.id for this repo
   └─ repo_root = resolved repository root directory
3. Query FactStore:
   ├─ SELECT FactFile WHERE analysis_id + path
   ├─ SELECT FactSymbol WHERE analysis_id + file_id + name
   └─ SELECT FactRelationship WHERE symbol_id + analysis_id
```

### Exact Queries:
```python
# Line 68-75: Find file in FactStore
fact_file = db.query(FactFile).filter(
    FactFile.analysis_id == tool_layer.analysis_id,  # From resolved repo's latest analysis
    FactFile.path == file_path  # Repository-relative path
).first()

# Line 92-99: Find symbol in FactStore
symbols = db.query(FactSymbol).filter(
    FactSymbol.analysis_id == tool_layer.analysis_id,  # From resolved repo's latest analysis
    FactSymbol.file_id == fact_file.id,  # From FactFile lookup
    FactSymbol.name == symbol_name  # Exact name match
).all()

# Line 152-157: Get relationships
relationships = _get_symbol_relationships(
    db, symbol.id, tool_layer.analysis_id  # Uses analysis_id for isolation
)
```

**Data Source:** `PostgreSQL (FactStore tables)`
**Repo Identification:** Via `repo_name` → `resolve_repository()` → `Repository.id` → Latest `Analysis.id`
**Key Tables:** `FactFile`, `FactSymbol`, `FactRelationship`

---

## Tool #2: File Retrieval

**File:** `/backend/routers/repo/structure.py`

**Function:** `GET /{repo_name}/files/{file_path}`

### Data Source Chain:
```
1. resolve_repository(repo_name)
   ↓ Gets Repository object
2. get_latest_analysis(repo_name)
   ├─ Returns repo + latest Analysis with status="Completed"
   └─ Sets context for FactStore queries
3. RepositoryToolLayer.read_file()
   ├─ Try 1: Read from active worktree (filesystem) if present
   └─ Try 2: Read from Azure Blob Storage (via FactFile.blob_name)
4. Query FactFile for metadata:
   ├─ total_lines, file_size, blob_name
   └─ Line range validation
```

### Exact Queries:
```python
# From structure.py: resolve repo and analysis
repo, analysis = get_latest_analysis(repo_name, db, current_user)

# From RepositoryToolLayer.read_file():
# Priority 1: Active worktree (if repo_root exists)
if self.repo_root and self.repo_root.exists():
    target_file = validate_repo_path(self.repo_root, path)
    # Read from filesystem
    
# Priority 2: Azure Blob Storage
# Query FactFile for blob location:
fact_file = db.query(FactFile).filter(
    FactFile.analysis_id == analysis.id,
    FactFile.path == file_path
).first()
# Download from Azure using blob_name
```

**Data Source:** 
- **Primary:** Filesystem (active worktree) `/tmp/repo-analysis/job_X_RepoName/`
- **Fallback:** Azure Blob Storage `repositories/{repo_id}/snapshots/{snapshot_id}/{file_path}`
- **Metadata:** PostgreSQL `FactFile` table

**Repo Identification:** Via `repo_name` → `resolve_repository()` → `Repository.id` → `get_latest_analysis()`
**Key Metadata:** `FactFile.blob_name`, `FactFile.path`

---

## Tool #3: Graph Query

**File:** `/backend/routers/repo/graph.py`

**Function:** `POST /{repo_name}/graph/query` with `node_id, direction, depth, max_nodes, relationship_type`

### Data Source Chain:
```
1. resolve_repository(repo_name)
   ↓ Gets Repository object
2. get_or_build_model(repo_name, db, current_user)
   ├─ Gets latest Analysis
   └─ Loads/builds RIM (Repository Intelligent Model)
3. GraphQueryService(model)
   ├─ Traverses relationships in RIM
   └─ Returns entities connected to node_id
4. RIM built from FactStore:
   ├─ FactSymbol (entities)
   ├─ FactRelationship (edges)
   ├─ FactRoute (HTTP routes)
   └─ FactDatabaseObject (DB tables)
```

### Exact Process:
```python
# From graph.py line 20, 66:
query_layer = get_or_build_model(repo_name, db, current_user)
# This builds RIM from FactStore:
#  - Queries FactSymbol WHERE analysis_id
#  - Queries FactRelationship WHERE analysis_id
#  - Loads into in-memory RIM object

# Create graph query service
service = GraphQueryService(query_layer.model)

# Traverse graph from node
graph_result = service.query(
    node_id=req.node_id,           # Starting entity ID
    direction=req.direction,       # "incoming"/"outgoing"/"both"
    depth=req.depth,               # 1-10 levels deep
    max_nodes=req.max_nodes,       # Cap results at N nodes
    relationship_type=req.relationship_type  # "calls", "imports", etc
)
```

**Data Source:** PostgreSQL (built into RIM)
- Query: FactSymbol WHERE `analysis_id`
- Query: FactRelationship WHERE `analysis_id`, `relationship_type`
- Query: FactRoute WHERE `analysis_id`
- Query: FactDatabaseObject WHERE `analysis_id`

**Repo Identification:** Via `repo_name` → `resolve_repository()` → `get_or_build_model()` → Latest `Analysis.id`
**Key Tables:** `FactSymbol`, `FactRelationship`, `FactRoute`, `FactDatabaseObject`

---

## Tool #4: Symbol Search

**File:** `/backend/routers/repo/symbols.py`

**Function:** `POST /{repo_name}/symbols/explain`

### Data Source Chain:
```
1. resolve_repository(repo_name)
   ↓ Gets Repository object
2. get_latest_analysis(repo_name)
   ├─ Gets Analysis with status="Completed"
   └─ Sets context for FactStore queries
3. Query FactStore:
   ├─ FactSymbol (find symbol by name/file)
   ├─ FactFile (get file metadata)
   └─ FactCapability (get feature info)
4. LLM Call:
   ├─ Generate explanation of symbol
   └─ Return to user
```

### Exact Queries:
```python
# From symbols.py line 241+:
@symbols_router.post("/{repo_name}/symbols/explain")
def explain_symbol(
    repo_name: str,
    request: ExplainSymbolRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Get repo and latest analysis
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    
    # Query FactSymbol
    symbol = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis.id,
        FactSymbol.name == request.name  # or by symbol_id/file_path
    ).first()
    
    # Optional: Query FactCapability for feature info
    capability = db.query(FactCapability).filter(
        FactCapability.analysis_id == analysis.id,
        FactCapability.name.ilike(f"%{request.name}%")
    ).all()
    
    # Call LLM to generate explanation
    explanation = llm_service.explain_symbol(symbol, capability)
```

**Data Source:** PostgreSQL (FactStore)
- Query: FactSymbol WHERE `analysis_id`, `name` or `symbol_id`
- Query: FactFile WHERE `analysis_id`, `id`
- Query: FactCapability WHERE `analysis_id`

**Repo Identification:** Via `repo_name` → `resolve_repository()` → `get_latest_analysis()` → Latest `Analysis.id`
**Key Tables:** `FactSymbol`, `FactFile`, `FactCapability`

---

## Summary: Data Source for All 4 Tools

| Tool | Primary Data Source | Location | Repo Lookup | Analysis Lookup |
|------|--------------------|-----------|----|-----|
| #1 - Symbol Inspection | PostgreSQL (FactStore) | Tables: FactFile, FactSymbol, FactRelationship | `resolve_repository()` | Latest completed Analysis.id |
| #2 - File Retrieval | Filesystem + Azure Blob | Priority: Worktree, then Blob Storage | `resolve_repository()` | Latest completed Analysis.id |
| #3 - Graph Query | PostgreSQL (RIM model) | Tables: FactSymbol, FactRelationship, FactRoute | `resolve_repository()` | Latest completed Analysis.id |
| #4 - Symbol Search | PostgreSQL (FactStore) | Tables: FactSymbol, FactFile, FactCapability | `resolve_repository()` | Latest completed Analysis.id |

---

## Key Points

1. **All 4 tools follow the same repo identification pattern:**
   - User provides `repo_name` (ID, URL, or slug)
   - `resolve_repository()` finds Repository record for current_user
   - `get_latest_analysis()` or `get_or_build_model()` gets latest completed Analysis.id
   - All FactStore queries filter by `analysis_id` for isolation

2. **All 4 tools query the same database:**
   - PostgreSQL FactStore (FactSymbol, FactFile, FactRelationship, etc.)
   - Analysis isolation: `WHERE analysis_id == X`

3. **Tool #2 also accesses:**
   - Filesystem (active worktree if present)
   - Azure Blob Storage (via FactFile.blob_name metadata)

4. **Analysis.id is the KEY:**
   - Every query filters by analysis_id
   - Ensures complete isolation between analyses
   - Enables concurrent multi-user analysis

---

## To Create Agent Tools

Wrap each with:
1. HTTP endpoint wrapper
2. Current user context
3. JSON request/response
4. Error handling (400/404/500)

The data sources and repo resolution logic remain **unchanged**.
