# Repository Hash Design: Unique, Immutable Identification

## Problem with Current Design
- Repository identified by name (ambiguous)
- Tool #2 uses filesystem `/tmp/` (won't work in production)
- Multiple repos can have same name (with slug matching workaround)
- No guarantee of uniqueness across operations

## Solution: Repository Hash (UUID)

Every repository gets a **unique, immutable hash** at creation time.
All tools use this hash, never the name.

---

## Database Schema Changes

### Add `repository_hash` column to Repository table:

```python
# File: /backend/models/repository.py

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    repository_hash = Column(String(36), index=True, nullable=False, unique=True)  # UUID v4
    github_repo_id = Column(String, index=True, nullable=True)
    url = Column(String, index=True, nullable=False)
    default_branch = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_user_repo_url"),
        UniqueConstraint("user_id", "github_repo_id", name="uq_user_github_repo"),
        UniqueConstraint("repository_hash", name="uq_repository_hash"),  # Globally unique
    )
    
    analyses = relationship("Analysis", back_populates="repository", cascade="all, delete-orphan")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.repository_hash:
            self.repository_hash = str(uuid.uuid4())  # Auto-generate on creation
```

### Migration:

```sql
-- Add column to existing repositories
ALTER TABLE repositories ADD COLUMN repository_hash VARCHAR(36) UNIQUE;

-- Generate UUID for existing repos
UPDATE repositories SET repository_hash = gen_random_uuid()::text WHERE repository_hash IS NULL;

-- Make NOT NULL
ALTER TABLE repositories ALTER COLUMN repository_hash SET NOT NULL;

-- Create index for fast lookup
CREATE INDEX idx_repository_hash ON repositories(repository_hash);
```

---

## Tool #1: Symbol Inspection

### Current (Name-based):
```python
def inspect_symbol(
    file_path: str,
    symbol_name: str,
    repo_name: str = "default",  # ❌ Ambiguous
    db: Optional[Session] = None,
):
    tool_layer = RepositoryToolLayer(
        repo_name=repo_name,  # Must resolve via name (can fail)
        db=db,
    )
```

### New (Hash-based):
```python
def inspect_symbol(
    file_path: str,
    symbol_name: str,
    repo_hash: str,  # ✅ UUID - unambiguous
    db: Optional[Session] = None,
):
    # Direct lookup by hash - NO ambiguity
    repo = db.query(Repository).filter(
        Repository.repository_hash == repo_hash
    ).first()
    
    if not repo:
        raise ValueError(f"Repository not found: {repo_hash}")
    
    # Get latest analysis
    analysis = db.query(Analysis).filter(
        Analysis.repository_id == repo.id,
        Analysis.status == "Completed"
    ).order_by(Analysis.created_at.desc()).first()
    
    # Query FactStore with analysis_id
    symbol = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis.id,
        FactSymbol.name == symbol_name
    ).first()
```

---

## Tool #2: File Retrieval (CRITICAL CHANGE)

### Current (Filesystem + Azure):
```python
def read_file(self, path: str, start_line: int = 1, end_line: Optional[int] = None):
    clean_path = path.replace("\\", "/").removeprefix("./").lstrip("/")

    # 1. Try Active Worktree (❌ Won't work in production)
    if self.repo_root and self.repo_root.exists():
        target_file = validate_repo_path(self.repo_root, path, allow_binary=False)
        if target_file.exists():
            with open(target_file, "r") as f:
                # Read from filesystem
                
    # 2. Fallback to Azure
    # Get blob from FactFile...
```

### New (Azure Blob Only - Production Ready):
```python
def read_file(
    repo_hash: str,  # ✅ UUID instead of repo_name
    file_path: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Read file ONLY from Azure Blob Storage.
    No filesystem fallback - production-ready.
    """
    
    # 1. Get repository by hash
    repo = db.query(Repository).filter(
        Repository.repository_hash == repo_hash
    ).first()
    
    if not repo:
        raise ValueError(f"Repository not found: {repo_hash}")
    
    # 2. Get latest analysis
    analysis = db.query(Analysis).filter(
        Analysis.repository_id == repo.id,
        Analysis.status == "Completed"
    ).order_by(Analysis.created_at.desc()).first()
    
    if not analysis:
        raise ValueError(f"No completed analysis for repo: {repo_hash}")
    
    # 3. Get file metadata from FactFile
    fact_file = db.query(FactFile).filter(
        FactFile.analysis_id == analysis.id,
        FactFile.path == file_path
    ).first()
    
    if not fact_file:
        raise ValueError(f"File not found: {file_path}")
    
    # 4. Read from Azure Blob Storage ONLY
    blob_name = fact_file.blob_name  # E.g., "repositories/repo-hash/snapshots/uuid/file/path"
    
    try:
        blob_client = container_client.get_blob_client(blob_name)
        blob_data = blob_client.download_blob().readall()
        content = blob_data.decode('utf-8', errors='replace')
        lines = content.split('\n')
        
        total_lines = len(lines)
        s, e = clamp_line_range(total_lines, start_line, end_line)
        selected_lines = lines[s-1:e]
        
        return {
            "path": file_path,
            "start_line": s,
            "end_line": e,
            "total_lines": total_lines,
            "content": "\n".join(selected_lines),
            "source": "azure_blob_storage"
        }
    except Exception as e:
        raise ValueError(f"Failed to read from blob storage: {e}")
```

**Key Changes:**
- ❌ Remove filesystem fallback (`/tmp/` worktree)
- ✅ Use only Azure Blob Storage
- ✅ Use repository_hash instead of repo_name
- ✅ Production-ready (works in cloud, Kubernetes, etc.)

---

## Tool #3: Graph Query

### Current:
```python
@graph_router.post("/{repo_name}/graph/query")  # ❌ Name-based
def graph_query(repo_name: str, ...):
    query_layer = get_or_build_model(repo_name, db, current_user)
```

### New:
```python
@graph_router.post("/{repo_hash}/graph/query")  # ✅ Hash-based
def graph_query(repo_hash: str, req: GraphQueryRequest, db: Session = Depends(get_db)):
    # Direct lookup by hash
    repo = db.query(Repository).filter(
        Repository.repository_hash == repo_hash
    ).first()
    
    if not repo:
        raise HTTPException(404, f"Repository not found: {repo_hash}")
    
    # Get latest analysis
    analysis = db.query(Analysis).filter(
        Analysis.repository_id == repo.id,
        Analysis.status == "Completed"
    ).order_by(Analysis.created_at.desc()).first()
    
    # Build RIM from analysis_id
    query_layer = build_model_from_analysis(analysis.id, db)
    service = GraphQueryService(query_layer.model)
    
    # Query graph...
```

---

## Tool #4: Symbol Search

### Current:
```python
@symbols_router.post("/{repo_name}/symbols/explain")  # ❌ Name-based
def explain_symbol(repo_name: str, ...):
```

### New:
```python
@symbols_router.post("/{repo_hash}/symbols/explain")  # ✅ Hash-based
def explain_symbol(repo_hash: str, request: ExplainSymbolRequest, db: Session = Depends(get_db)):
    repo = db.query(Repository).filter(
        Repository.repository_hash == repo_hash
    ).first()
    
    if not repo:
        raise HTTPException(404, f"Repository not found: {repo_hash}")
    
    # Get latest analysis
    analysis = db.query(Analysis).filter(
        Analysis.repository_id == repo.id,
        Analysis.status == "Completed"
    ).order_by(Analysis.created_at.desc()).first()
    
    # Query FactStore...
```

---

## API Changes Summary

### Before (Name-based, ambiguous):
```
GET  /repo/{repo_name}/files/{file_path}
GET  /repo/{repo_name}/graph/search
POST /repo/{repo_name}/graph/query
POST /repo/{repo_name}/symbols/explain
```

### After (Hash-based, unambiguous):
```
GET  /repo/{repo_hash}/files/{file_path}
GET  /repo/{repo_hash}/graph/search
POST /repo/{repo_hash}/graph/query
POST /repo/{repo_hash}/symbols/explain
```

---

## Benefits

✅ **No Ambiguity** - UUID is globally unique  
✅ **Production Ready** - Works in cloud, Kubernetes, containers  
✅ **No Filesystem Dependency** - All tools use Azure Blob  
✅ **Scalable** - Direct hash lookup instead of name resolution  
✅ **Immutable** - Hash never changes for a repository  
✅ **Secure** - Hash is random, not guessable  
✅ **LLM Friendly** - Simple, unambiguous identifier  

---

## Migration Path

1. **Phase 1:** Add `repository_hash` column (nullable)
2. **Phase 2:** Generate UUIDs for existing repositories
3. **Phase 3:** Make `repository_hash` NOT NULL
4. **Phase 4:** Update tools to accept both `repo_name` and `repo_hash` (backwards compatible)
5. **Phase 5:** Deprecate `repo_name` parameter
6. **Phase 6:** Remove `repo_name` parameter entirely

---

## Example Usage (After Implementation)

```python
# LLM Agent calls Tool #2
resp = requests.get(
    f"/repo/550e8400-e29b-41d4-a716-446655440000/files/backend/auth.py",
    params={"start_line": 1, "end_line": 50}
)

# LLM Agent calls Tool #3
resp = requests.post(
    f"/repo/550e8400-e29b-41d4-a716-446655440000/graph/query",
    json={
        "node_id": "sym_123",
        "direction": "incoming",
        "depth": 2
    }
)

# Simple, clean, unambiguous
```

---

## Implementation Checklist

- [ ] Add `repository_hash` column to Repository model
- [ ] Create database migration
- [ ] Generate UUIDs for existing repositories
- [ ] Update Tool #1 (Symbol Inspection) to use repo_hash
- [ ] Update Tool #2 (File Retrieval) to:
  - [ ] Remove `/tmp/` filesystem fallback
  - [ ] Use only Azure Blob Storage
  - [ ] Accept repo_hash instead of repo_name
- [ ] Update Tool #3 (Graph Query) to use repo_hash
- [ ] Update Tool #4 (Symbol Search) to use repo_hash
- [ ] Remove `resolve_repository()` function (no longer needed)
- [ ] Update API route signatures
- [ ] Update tests
- [ ] Update LLM Agent tool wrappers to pass repo_hash

---

## This is the Proper Architecture

No ambiguity, no workarounds, no filesystem dependencies, production-ready.
