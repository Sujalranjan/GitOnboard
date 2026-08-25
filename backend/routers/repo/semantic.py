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
    from backend.routers.repo.services.analysis import get_latest_analysis
    try:
        repo, latest_analysis = get_latest_analysis(repo_name, db, current_user)
    except HTTPException:
        return {"has_index": False}
    target_dir = CHROMA_BASE_DIR / f"user_{current_user.id}" / f"repo_{repo.id}" / f"analysis_{latest_analysis.id}"
    if not target_dir.exists() or not target_dir.is_dir():
        return {"has_index": False}
        
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
            from backend.routers.repo.services.analysis import get_latest_analysis
            repo, latest_analysis = get_latest_analysis(repo_name, bg_db, current_user)
            query_layer = get_or_build_model(repo_name, bg_db, current_user)
            target_dir = CHROMA_BASE_DIR / f"user_{current_user.id}" / f"repo_{repo.id}" / f"analysis_{latest_analysis.id}"
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
                    except Exception:
                        mtime = 0
                    current_files[path] = mtime
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
    from backend.routers.repo.services.analysis import get_latest_analysis
    repo, latest_analysis = get_latest_analysis(repo_name, db, current_user)
    target_dir = CHROMA_BASE_DIR / f"user_{current_user.id}" / f"repo_{repo.id}" / f"analysis_{latest_analysis.id}"
    chroma_dir = target_dir / "chroma"
    
    if not chroma_dir.exists():
        semantic_artifact = db.query(AnalysisArtifact).filter(
            AnalysisArtifact.analysis_id == latest_analysis.id,
            AnalysisArtifact.type == "semantic_index_db"
        ).first()
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

    try:
        # Load Chroma collection
        collection = None
        try:
            collection = get_chroma_collection(repo_name, current_user, db)
        except Exception as e:
            logger.warning(f"Could not load Chroma collection for hybrid search: {e}")

        # Fetch latest analysis for Fact Store integration
        from backend.routers.repo.services.analysis import get_latest_analysis
        analysis_id = None
        try:
            _, latest = get_latest_analysis(repo_name, db, current_user)
            if latest:
                analysis_id = latest.id
        except Exception:
            pass

        # Execute Hybrid Retrieval (Lexical + Semantic + Fact Store + RRF + Structural Expansion)
        from backend.intelligence.retrieval import HybridRetriever
        retriever = HybridRetriever(
            db=db,
            analysis_id=analysis_id,
            chroma_collection=collection,
            rrf_k=60,
            lexical_weight=1.0,
            semantic_weight=1.0,
            exact_weight=1.2
        )

        retrieved_items = retriever.retrieve(query=q, top_k=15, expand_with_fact_store=True)

        results = []
        for item in retrieved_items:
            results.append({
                "symbol_id": item.get("symbol_id") or item.get("id"),
                "file_path": item.get("file_path", ""),
                "match_type": item.get("match_type", item.get("type", "symbol")),
                "match_name": item.get("match_name", item.get("name", "")),
                "line_start": item.get("line_start"),
                "line_end": item.get("line_end"),
                "distance": item.get("distance", 0.0),
                "rrf_score": item.get("_rrf_score", 0.0),
                "route": item.get("route"),
                "capability": item.get("capability"),
                "expansion_reason": item.get("expansion_reason"),
            })

        return {"results": results}
    except Exception as e:
        logger.error(f"Failed to execute hybrid search: {e}", exc_info=True)
        # Fallback to direct collection query if available
        try:
            collection = get_chroma_collection(repo_name, current_user, db)
            query_results = collection.query(query_texts=[q], n_results=10)
            results = []
            if query_results and query_results.get("metadatas") and len(query_results["metadatas"]) > 0:
                for idx, meta in enumerate(query_results["metadatas"][0]):
                    results.append({
                        "file_path": meta.get("file_path", ""),
                        "match_type": meta.get("type", "symbol"),
                        "match_name": meta.get("name", ""),
                        "distance": query_results["distances"][0][idx] if query_results.get("distances") else 0
                    })
            return {"results": results}
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to search")

