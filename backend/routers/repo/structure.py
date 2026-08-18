import logging
from typing import Dict
from pathlib import Path as PPath
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.models.repository import AnalysisJob, Analysis
from backend.dependencies.auth import get_current_user
from backend.services.github import fetch_file_content
from backend.routers.repo.services.analysis import get_latest_analysis
from backend.routers.repo.services.models import get_or_build_model

logger = logging.getLogger(__name__)

structure_router = APIRouter(tags=["structure"])

@structure_router.get("/{repo_name}/scan", include_in_schema=False)
def scan_repo(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        repo, analysis = get_latest_analysis(repo_name, db, current_user)
    except HTTPException:
        return {"status": "no_analysis"}
    
    if analysis.status in ["Failed", "Cancelled"]:
        safe_analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()
        
        if safe_analysis:
            # Revert changes: clean up the failed/cancelled analyses
            failed_analyses = db.query(Analysis).filter(
                Analysis.repository_id == repo.id,
                Analysis.id > safe_analysis.id
            ).all()
            for fa in failed_analyses:
                db.delete(fa)
            db.commit()
            analysis = safe_analysis
        else:
            # First scan failed, clear the scan entirely
            db.delete(repo)
            db.commit()
            return {"status": "failed", "message": f"Analysis {analysis.status.lower()} due to a network or processing error. The repository has been removed."}

    if analysis.status != "Completed":
        job = db.query(AnalysisJob).filter(AnalysisJob.analysis_id == analysis.id).first()
        job_status = job.status if job else analysis.status
        return {"status": "processing", "job_status": job_status}
    
    # Derive everything from core_model
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
    except HTTPException:
        return {"status": "no_model", "overview": {}, "hierarchy": {"name": repo_name, "type": "directory", "children": []}, "files": []}
    
    from backend.intelligence.rim.enums import EntityType
    
    # Build hierarchy from FILE and DIRECTORY entities
    files = list(query_layer.get_files())
    dirs = list(query_layer.get_directories())
    functions = [e for e in query_layer.model.entities.values() if e.type == EntityType.FUNCTION]
    classes = [e for e in query_layer.model.entities.values() if e.type == EntityType.CLASS]
    methods = [e for e in query_layer.model.entities.values() if e.type == EntityType.METHOD]
    
    # Build nested hierarchy tree
    dirs_by_path = {}
    hierarchy = {"name": repo_name, "type": "directory", "children": [], "path": ""}
    dirs_by_path[""] = hierarchy
    
    # Sort dirs so parents always come before children
    dir_paths = sorted([d.location.repository_path for d in dirs])
    for d_path in dir_paths:
        parts = PPath(d_path).parts
        name = parts[-1]
        parent_path = str(PPath(d_path).parent)
        if parent_path == ".":
            parent_path = ""
        d_node = {"name": name, "type": "directory", "path": d_path, "children": []}
        dirs_by_path[d_path] = d_node
        parent = dirs_by_path.get(parent_path, hierarchy)
        parent["children"].append(d_node)
    
    # Add files — with their functions and classes as children
    files_metadata = []
    for f in files:
        f_path = f.location.repository_path
        parts = PPath(f_path).parts
        name = parts[-1]
        parent_path = str(PPath(f_path).parent)
        if parent_path == ".":
            parent_path = ""
        
        # Build file children (classes + top-level functions)
        file_classes = [c for c in classes if c.metadata.get("file_id") == f_path or c.location.repository_path == f_path]
        file_fns = [fn for fn in functions if fn.metadata.get("file_id") == f_path or fn.location.repository_path == f_path]
        
        file_children = []
        for c in file_classes:
            cls_methods = [m for m in methods if m.metadata.get("class_id") == c.id]
            cls_node = {
                "name": c.name, "type": "class", "path": f_path,
                "children": [{"name": m.name, "type": "function", "path": f_path, "line": m.location.start_line, "children": []} for m in cls_methods]
            }
            file_children.append(cls_node)
        for fn in file_fns:
            file_children.append({"name": fn.name, "type": "function", "path": f_path, "line": fn.location.start_line, "children": []})
        
        ext = PPath(f_path).suffix
        lang_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".jsx": "JavaScript", ".java": "Java", ".go": "Go", ".rb": "Ruby", ".cpp": "C++", ".c": "C"}
        lang = lang_map.get(ext.lower(), f.location.language if hasattr(f.location, 'language') else "Unknown")
        
        f_node = {"name": name, "type": "file", "path": f_path, "children": file_children}
        parent = dirs_by_path.get(parent_path, hierarchy)
        parent["children"].append(f_node)
        
        files_metadata.append({"path": f_path, "extension": ext, "language": lang, "size": 0, "modified_time": ""})
    
    # Language detection from file extensions
    lang_counts: Dict[str, int] = {}
    for fm in files_metadata:
        if fm["language"] != "Unknown":
            lang_counts[fm["language"]] = lang_counts.get(fm["language"], 0) + 1
    language_str = ", ".join(sorted(lang_counts.keys(), key=lambda k: lang_counts[k], reverse=True)[:3]) if lang_counts else "Unknown"
    
    # Extract metadata if available
    commit = ""
    branch = ""
    commit_timestamp = ""
    if query_layer and query_layer.model and query_layer.model.metadata:
        commit = query_layer.model.metadata.commit
        branch = query_layer.model.metadata.branch
        if hasattr(query_layer.model.metadata, "metadata") and isinstance(query_layer.model.metadata.metadata, dict):
            commit_timestamp = query_layer.model.metadata.metadata.get("commit_timestamp") or ""
            
    return {
        "status": "completed",
        "overview": {
            "total_files": len(files),
            "total_directories": len(dirs),
            "total_functions": len(functions),
            "total_classes": len(classes),
            "language": language_str,
            "commit": commit,
            "branch": branch,
            "commit_timestamp": commit_timestamp
        },
        "hierarchy": hierarchy,
        "files": files_metadata
    }

@structure_router.get("/{repo_name}/parse", include_in_schema=False)
async def parse_repo_file(repo_name: str, file_path: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    
    parts = repo.url.rstrip("/").split("/")
    owner = parts[-2]
    
    from backend.models.fact_store import FactFile
    from backend.storage import get_storage

    clean_path = file_path.replace("\\", "/").lstrip("./").lstrip("/")
    source_code = ""

    # Priority 1: Fetch from Azure Blob Storage via Fact Store reference
    fact_file = (
        db.query(FactFile)
        .filter(FactFile.analysis_id == analysis.id, FactFile.path == clean_path)
        .first()
    )
    if fact_file and fact_file.blob_name:
        try:
            storage = get_storage()
            source_code = storage.get_object_text(fact_file.blob_name)
        except Exception as err:
            logger.warning(f"Failed to fetch blob {fact_file.blob_name}: {err}")

    # Priority 2: Fallback to GitHub API if not available in Blob Storage
    if not source_code:
        try:
            source_code = await fetch_file_content(owner, repo_name, repo.default_branch, file_path, current_user.github_access_token)
        except Exception as gh_err:
            logger.warning(f"Failed to fetch file from GitHub: {gh_err}")
    
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        from backend.intelligence.rim.enums import EntityType, RelationshipType
        
        file_functions = []
        file_classes = []
        file_imports = []
        
        file_id = None
        for e in query_layer.model.entities.values():
            if e.type == EntityType.FILE and e.location.repository_path == file_path:
                file_id = e.id
            if e.metadata.get("file_id") == file_path or e.location.repository_path == file_path:
                if e.type == EntityType.FUNCTION:
                    file_functions.append({"name": e.name, "line": e.location.start_line})
                elif e.type == EntityType.CLASS:
                    file_classes.append({
                        "id": e.id,
                        "name": e.name, 
                        "line": e.location.start_line,
                        "methods": []
                    })
                    
        # Populate methods
        for e in query_layer.model.entities.values():
            if e.type == EntityType.METHOD:
                for cls in file_classes:
                    # simplistic check: method is in the same file and declared within the class
                    # if we have class_id metadata, use it, otherwise fall back to matching file
                    if e.metadata.get("class_id") == cls["id"] or (e.metadata.get("file_id") == file_path and cls["name"] in e.qualified_name):
                        cls["methods"].append({"name": e.name, "line": e.location.start_line})
                        
        if file_id:
            for rel in query_layer.model.relationships.values():
                if rel.type == RelationshipType.IMPORTS and rel.source_id == file_id:
                    module_name = rel.metadata.get("module", "unknown")
                    file_imports.append({"module_name": module_name})
                    
    except Exception as e:
        logger.error(f"Error parsing file details: {e}")
        file_functions = []
        file_classes = []
        file_imports = []
        
    return {
        "source_code": source_code,
        "imports": file_imports,
        "functions": file_functions,
        "classes": file_classes,
        "docstring": ""
    }

@structure_router.get("/{repo_name}/dependencies")
def get_dependencies(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        from backend.intelligence.rim.enums import EntityType, RelationshipType
        # Build nodes from FILE entities
        nodes = []
        seen_nodes = set()
        for e in query_layer.model.entities.values():
            if e.type == EntityType.FILE and e.id not in seen_nodes:
                seen_nodes.add(e.id)
                nodes.append({"id": e.id, "label": e.name, "full_path": e.location.repository_path, "language": getattr(e.location, 'language', 'Unknown')})
        # Build edges from IMPORTS/DEPENDS_ON relationships
        edges = []
        for r in query_layer.model.relationships.values():
            if r.type in (RelationshipType.IMPORTS, RelationshipType.DEPENDS_ON):
                edges.append({"source": r.source_id, "target": r.target_id, "type": r.type.value})
        return {"nodes": nodes, "edges": edges}
    except HTTPException:
        return {"nodes": [], "edges": []}

@structure_router.get("/{repo_name}/call-graph")
def get_call_graph(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        from backend.intelligence.rim.enums import RelationshipType
        nodes = []
        edges = []
        seen_nodes = set()
        for r in query_layer.model.relationships.values():
            if r.type == RelationshipType.CALLS:
                edges.append({"source": r.source_id, "target": r.target_id})
                for nid in (r.source_id, r.target_id):
                    if nid not in seen_nodes:
                        seen_nodes.add(nid)
                        entity = query_layer.model.entities.get(nid)
                        label = entity.name if entity else nid.split("::")[-1]
                        nodes.append({"id": nid, "label": label})
        return {"nodes": nodes, "edges": edges}
    except HTTPException:
        return {"nodes": [], "edges": []}

@structure_router.get("/{repo_name}/symbols")
def get_symbols(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        from backend.intelligence.rim.enums import EntityType
        symbols = []
        for e in query_layer.model.entities.values():
            if e.type in (EntityType.CLASS, EntityType.FUNCTION, EntityType.METHOD):
                symbols.append({
                    "id": e.id,
                    "name": e.name,
                    "qualified_name": e.qualified_name or e.name,
                    "type": e.type.value,
                    "file_path": e.metadata.get("file_id", e.location.repository_path),
                    "line_number": e.location.start_line
                })
        return {"symbols": symbols}
    except HTTPException:
        return {"symbols": []}

@structure_router.get("/{repo_name}/stats")
def get_stats(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        from backend.intelligence.rim.enums import EntityType
        entities = query_layer.model.entities
        files = [e for e in entities.values() if e.type == EntityType.FILE]
        functions = [e for e in entities.values() if e.type == EntityType.FUNCTION]
        classes = [e for e in entities.values() if e.type == EntityType.CLASS]
        methods = [e for e in entities.values() if e.type == EntityType.METHOD]
        dirs = [e for e in entities.values() if e.type == EntityType.DIRECTORY]
        
        # Estimate lines of code from location data
        total_lines = sum(e.location.end_line - e.location.start_line + 1 for e in files if e.location)
        
        # Language counts
        lang_counts: Dict[str, int] = {}
        ext_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".jsx": "JavaScript", ".java": "Java", ".go": "Go"}
        for f in files:
            ext = PPath(f.location.repository_path).suffix.lower()
            lang = ext_map.get(ext, "Other")
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        
        return {
            "total_files": len(files),
            "total_directories": len(dirs),
            "total_functions": len(functions),
            "total_classes": len(classes),
            "total_methods": len(methods),
            "lines_of_code": total_lines,
            "language_distribution": lang_counts,
            "average_functions_per_module": round(len(functions) / max(len(files), 1), 2),
            "custom_metrics": {
                "test_coverage_approx_percent": "N/A",
                "documentation_coverage_percent": 0
            }
        }
    except HTTPException:
        return {}

@structure_router.get("/{repo_name}/architecture")
def get_architecture(repo_name: str, node_id: str = "root", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query_layer = get_or_build_model(repo_name, db, current_user)
    from backend.intelligence.rim.enums import EntityType
    nodes = []
    
    if node_id == "root":
        for d in query_layer.get_directories():
            path = d.location.repository_path
            parent = str(PPath(path).parent).replace("\\", "/")
            if parent in (".", ""):
                nodes.append({"id": path, "name": d.name, "type": "folder", "parent": "root", "has_children": True, "path": path})
        for f in query_layer.get_files():
            path = f.location.repository_path
            parent = str(PPath(path).parent).replace("\\", "/")
            if parent in (".", ""):
                has_children = f.metadata.get("is_supported", False)
                nodes.append({"id": path, "name": f.name, "type": "file", "parent": "root", "has_children": has_children, "path": path})
    elif "::" not in node_id:
        for d in query_layer.get_directories():
            path = d.location.repository_path
            parent = str(PPath(path).parent).replace("\\", "/")
            if parent == node_id:
                nodes.append({"id": path, "name": d.name, "type": "folder", "parent": node_id, "has_children": True, "path": path})
        for f in query_layer.get_files():
            path = f.location.repository_path
            parent = str(PPath(path).parent).replace("\\", "/")
            if parent == node_id:
                has_children = f.metadata.get("is_supported", False)
                nodes.append({"id": path, "name": f.name, "type": "file", "parent": node_id, "has_children": has_children, "path": path})
        
        # File children: classes and functions
        for c in query_layer.get_classes_in_file(node_id):
            nodes.append({"id": c.id, "name": c.name, "type": "class", "parent": node_id, "has_children": True, "path": node_id})
        for fn in [e for e in query_layer.model.entities.values() if e.type == EntityType.FUNCTION and (e.metadata.get("file_id") == node_id or e.location.repository_path == node_id)]:
            nodes.append({"id": fn.id, "name": fn.name, "type": "function", "parent": node_id, "has_children": False, "path": node_id})
    else:
        # It's a class — return methods
        methods = [e for e in query_layer.model.entities.values() if e.type == EntityType.METHOD and e.metadata.get("class_id") == node_id]
        for m in methods:
            nodes.append({"id": m.id, "name": m.name, "type": "function", "parent": node_id, "has_children": False, "path": m.metadata.get("file_id")})
            
    return {"nodes": nodes}


@structure_router.get("/{repo_name}/file")
async def get_raw_file(
    repo_name: str,
    path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Invalid empty file path")

    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    from backend.models.fact_store import FactFile
    from backend.storage import get_storage

    clean_path = path.replace("\\", "/").lstrip("./").lstrip("/")
    fact_file = (
        db.query(FactFile)
        .filter(FactFile.analysis_id == analysis.id, FactFile.path == clean_path)
        .first()
    )

    if fact_file and fact_file.blob_name:
        try:
            storage = get_storage()
            content = storage.get_object_text(fact_file.blob_name)
            if content is not None:
                return {
                    "path": clean_path,
                    "content": content,
                    "size": fact_file.size,
                    "language": fact_file.language,
                    "content_type": fact_file.content_type,
                }
        except Exception as e:
            logger.warning(f"Error reading blob {fact_file.blob_name}: {e}")

    # Fallback to GitHub API if token and repository URL are available
    if current_user.github_access_token and repo.url:
        try:
            parts = repo.url.rstrip("/").split("/")
            if len(parts) >= 2:
                owner = parts[-2]
                content = await fetch_file_content(owner, repo_name, repo.default_branch or "main", clean_path, current_user.github_access_token)
                if content is not None:
                    return {
                        "path": clean_path,
                        "content": content,
                        "size": len(content.encode("utf-8")),
                        "language": None,
                        "content_type": "text/plain",
                    }
        except Exception as e:
            logger.debug(f"GitHub fallback read failed for {clean_path}: {e}")

    # If neither Azurite blob nor GitHub contains the file, return explicit 404
    raise HTTPException(
        status_code=404,
        detail=f"File not found in storage or repository: '{clean_path}'"
    )


from pydantic import BaseModel

class SaveFileRequest(BaseModel):
    path: str
    content: str

@structure_router.post("/{repo_name}/file")
async def save_repo_file(
    repo_name: str,
    body: SaveFileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not body.path or not body.path.strip():
        raise HTTPException(status_code=400, detail="Invalid empty file path")

    clean_path = body.path.replace("\\", "/").lstrip("./").lstrip("/")
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    from backend.models.fact_store import FactFile
    from backend.storage import get_storage, build_blob_key

    fact_file = (
        db.query(FactFile)
        .filter(FactFile.analysis_id == analysis.id, FactFile.path == clean_path)
        .first()
    )

    if fact_file and fact_file.blob_name:
        blob_name = fact_file.blob_name
    else:
        blob_name = build_blob_key(repo.id, f"snap_{analysis.id}", clean_path)

    # Persist payload into Azurite Blob Storage
    try:
        storage = get_storage()
        storage.put_object(blob_name, body.content)
    except Exception as e:
        logger.error(f"Failed to write blob {blob_name} to Azurite storage: {e}")
        raise HTTPException(status_code=500, detail=f"Storage write error: {str(e)}")

    # Update or insert FactFile record
    content_bytes = body.content.encode("utf-8")
    if fact_file:
        fact_file.blob_name = blob_name
        fact_file.size = len(content_bytes)
    else:
        fact_file = FactFile(
            id=f"{analysis.id}:{clean_path}",
            analysis_id=analysis.id,
            path=clean_path,
            blob_name=blob_name,
            size=len(content_bytes),
            language=None,
        )
        db.add(fact_file)

    db.commit()

    return {
        "status": "saved",
        "path": clean_path,
        "content_length": len(body.content),
        "blob_name": blob_name,
    }
