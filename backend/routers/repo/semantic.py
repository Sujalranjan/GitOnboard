import logging
import uuid
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.models.repository import Repository, Analysis, AnalysisArtifact
from backend.dependencies.auth import get_current_user
from backend.routers.repo.services.models import get_or_build_model
from backend.routers.repo.services.tasks import get_task_status, set_task_status

logger = logging.getLogger(__name__)

CHROMA_BASE_DIR = Path("/tmp/chroma")

semantic_router = APIRouter(tags=["semantic"])

@semantic_router.get("/{repo_name}/semantic-status")
def semantic_status_repo(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repos_dir = CHROMA_BASE_DIR
    target_dir = repos_dir / f"{current_user.id}_{repo_name}"
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Repository not found")
        
    state_file = target_dir / "semantic_index_state.json"
    return {"has_index": state_file.exists()}

@semantic_router.post("/{repo_name}/semantic-index", include_in_schema=False)
def semantic_index_repo(repo_name: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_status = get_task_status(repo_name, "semantic_index", current_user, db)
    if current_status == "processing":
        return {"status": "processing"}
        
    set_task_status(repo_name, "semantic_index", "processing", current_user, db)
    
    def background_semantic_index():
        from backend.database import SessionLocal
        bg_db = SessionLocal()
        try:
            import chromadb
            query_layer = get_or_build_model(repo_name, bg_db, current_user)
            target_dir = CHROMA_BASE_DIR / f"{current_user.id}_{repo_name}"
            chroma_dir = target_dir / "chroma"
            chroma_dir.mkdir(parents=True, exist_ok=True)
            state_file = target_dir / "semantic_index_state.json"
            state = {}
            if state_file.exists():
                try:
                    with open(state_file, "r") as f:
                        state = json.load(f)
                except Exception:
                    state = {}
            client = chromadb.PersistentClient(path=str(chroma_dir.absolute()))
            collection = client.get_or_create_collection(name="semantic_index")
            current_files = {}
            for f in query_layer.get_files():
                from backend.intelligence.rim.enums import EntityType
                is_supported = f.metadata.get("is_supported", False) or f.type == EntityType.FILE
                if is_supported:
                    path = f.location.repository_path
                    try:
                        mtime = (target_dir / path).stat().st_mtime
                        current_files[path] = mtime
                    except Exception:
                        pass
            deleted_files = set(state.keys()) - set(current_files.keys())
            modified_files = set()
            new_files = set(current_files.keys()) - set(state.keys())
            for f in current_files:
                if f in state and current_files[f] > state[f]:
                    modified_files.add(f)
            files_to_process = new_files | modified_files
            files_to_delete_chunks = deleted_files | modified_files
            status = "up to date"
            if not state:
                status = "indexed"
            elif files_to_process or files_to_delete_chunks:
                status = "updated"
            if not files_to_process and not files_to_delete_chunks:
                set_task_status(repo_name, "semantic_index", "completed", current_user, bg_db)
                return
            if files_to_delete_chunks:
                for f in files_to_delete_chunks:
                    try:
                        collection.delete(where={"file_path": f})
                    except Exception:
                        pass
            documents = []
            metadatas = []
            ids = []
            from backend.intelligence.parser import LanguageParser
            parser = LanguageParser()
            
            for rel_str in files_to_process:
                pf = target_dir / rel_str
                ext = pf.suffix.lower()
                if not parser.supports_extension(ext):
                    continue
                    
                try:
                    with open(pf, "r", encoding="utf-8") as f:
                        source = f.read()
                    tree, _ = parser.parse_source(source, ext)
                    parsed_entities = parser.extract_entities(tree, source, rel_str, "")
                    
                    for cls in parsed_entities.get("classes", []):
                        if cls.get("source_segment"):
                            documents.append(cls["source_segment"])
                            metadatas.append({
                                "file_path": rel_str,
                                "type": "class",
                                "name": cls["name"]
                            })
                            ids.append(str(uuid.uuid4()))
                            
                    for fn in parsed_entities.get("functions", []):
                        if fn.get("source_segment"):
                            documents.append(fn["source_segment"])
                            metadatas.append({
                                "file_path": rel_str,
                                "type": "function",
                                "name": fn["name"]
                            })
                            ids.append(str(uuid.uuid4()))
                            
                    for md in parsed_entities.get("methods", []):
                        if md.get("source_segment"):
                            documents.append(md["source_segment"])
                            metadatas.append({
                                "file_path": rel_str,
                                "type": "function",
                                "name": md["name"]
                            })
                            ids.append(str(uuid.uuid4()))
                except Exception:
                    pass
            if documents:
                batch_size = 2000
                for i in range(0, len(documents), batch_size):
                    collection.upsert(
                        documents=documents[i:i+batch_size],
                        metadatas=metadatas[i:i+batch_size],
                        ids=ids[i:i+batch_size]
                    )
            for f in deleted_files:
                if f in state:
                    del state[f]
            for f in files_to_process:
                state[f] = current_files[f]
            try:
                with open(state_file, "w") as f:
                    json.dump(state, f, indent=2)
            except Exception:
                pass
            set_task_status(repo_name, "semantic_index", "completed", current_user, bg_db)
        except Exception as e:
            logger.error(f"Semantic index failed: {e}")
            set_task_status(repo_name, "semantic_index", "failed", current_user, bg_db)
        finally:
            bg_db.close()

    background_tasks.add_task(background_semantic_index)
    return {"status": "processing"}

def get_chroma_collection(repo_name: str, current_user: User, db: Session):
    repos_dir = CHROMA_BASE_DIR
    target_dir = repos_dir / f"{current_user.id}_{repo_name}"
    chroma_dir = target_dir / "chroma"
    
    if not chroma_dir.exists():
        repo = db.query(Repository).filter(Repository.user_id == current_user.id).filter(Repository.url.endswith(repo_name) | Repository.url.endswith(f"{repo_name}.git")).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        latest_analysis = db.query(Analysis).filter(Analysis.repository_id == repo.id).order_by(Analysis.created_at.desc()).first()
        if not latest_analysis:
            raise HTTPException(status_code=404, detail="No analysis found")
            
        semantic_artifact = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == latest_analysis.id, AnalysisArtifact.type == "semantic_index_db").first()
        if not semantic_artifact or not semantic_artifact.blob_data:
            raise HTTPException(status_code=404, detail="Semantic index not found in analysis artifacts")
            
        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / "chroma_temp.zip"
        with open(zip_path, "wb") as f:
            f.write(semantic_artifact.blob_data)
            
        import shutil
        shutil.unpack_archive(str(zip_path), str(chroma_dir), 'zip')
        
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(chroma_dir.absolute()))
        return client.get_collection(name="semantic_index")
    except Exception as e:
        logger.error(f"Failed to load Chroma collection: {e}")
        raise HTTPException(status_code=500, detail="Semantic index not found or corrupted")

@semantic_router.get("/{repo_name}/semantic-search")
def semantic_search_repo(repo_name: str, q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not q or len(q.strip()) == 0:
        return {"results": []}
        
    collection = get_chroma_collection(repo_name, current_user, db)
        
    try:
        query_results = collection.query(query_texts=[q], n_results=10)
        results = []
        if query_results and query_results["metadatas"] and len(query_results["metadatas"]) > 0:
            for idx, meta in enumerate(query_results["metadatas"][0]):
                results.append({
                    "file_path": meta["file_path"],
                    "match_type": meta["type"],
                    "match_name": meta["name"],
                    "distance": query_results["distances"][0][idx] if query_results["distances"] else 0
                })
        return {"results": results}
    except Exception as e:
        logger.error(f"Failed to search: {e}")
        raise HTTPException(status_code=500, detail="Failed to search")
