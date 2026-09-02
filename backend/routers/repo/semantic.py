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

@semantic_router.get("/{repo_name}/semantic-status", include_in_schema=False)
def semantic_status_repo(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), skip_logging: bool = True):
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
    """Check if semantic index is already built during analysis. If so, return immediately."""
    try:
        from backend.routers.repo.services.analysis import get_latest_analysis
        repo, latest_analysis = get_latest_analysis(repo_name, db, current_user)

        # Check if semantic_index_db artifact already exists
        existing_artifact = db.query(AnalysisArtifact).filter(
            AnalysisArtifact.analysis_id == latest_analysis.id,
            AnalysisArtifact.type == "semantic_index_db"
        ).first()

        if existing_artifact:
            logger.info(f"Semantic index already built for {repo_name}")
            set_task_status(repo_name, "semantic_index", "completed", current_user, db)
            return {"status": "completed", "source": "pre_built"}
    except Exception as e:
        logger.debug(f"Could not check existing semantic index: {e}")

    current_status = get_task_status(repo_name, "semantic_index", current_user, db)
    if current_status == "processing":
        return {"status": "processing"}

    set_task_status(repo_name, "semantic_index", "processing", current_user, db)
    
    def background_semantic_index():
        from backend.database import SessionLocal
        from backend.config import settings
        bg_db = SessionLocal()
        try:
            import chromadb
            from backend.routers.repo.services.analysis import get_latest_analysis
            from backend.models.fact_store import FactSymbol, FactFile

            repo, latest_analysis = get_latest_analysis(repo_name, bg_db, current_user)
            logger.info(f"Building semantic index for {repo_name} (analysis_id={latest_analysis.id})")

            target_dir = CHROMA_BASE_DIR / f"user_{current_user.id}" / f"repo_{repo.id}" / f"analysis_{latest_analysis.id}"
            chroma_dir = target_dir / "chroma"
            chroma_dir.mkdir(parents=True, exist_ok=True)

            client = chromadb.PersistentClient(path=str(chroma_dir.absolute()))
            collection = client.get_or_create_collection(name="semantic_index")

            # Index entities from FactStore database (persistent data, not deleted files)
            documents = []
            metadatas = []
            ids = []

            # Get all symbols from FactStore for this analysis
            symbols = bg_db.query(FactSymbol).filter(FactSymbol.analysis_id == latest_analysis.id).all()
            logger.info(f"Found {len(symbols)} symbols to index for analysis {latest_analysis.id}")
            for sym in symbols:
                doc = f"{sym.name}"  # Simple name for embedding
                documents.append(doc)
                metadatas.append({
                    "file_path": sym.file.path if sym.file else "unknown",
                    "type": "symbol",
                    "name": sym.name,
                })
                ids.append(str(uuid.uuid4()))

            # Get all files from FactStore for this analysis
            files = bg_db.query(FactFile).filter(FactFile.analysis_id == latest_analysis.id).all()
            logger.info(f"Found {len(files)} files to index for analysis {latest_analysis.id}")
            for file_obj in files:
                doc = file_obj.path
                documents.append(doc)
                metadatas.append({
                    "file_path": file_obj.path,
                    "type": "file",
                    "name": file_obj.path,
                })
                ids.append(str(uuid.uuid4()))

            # Upsert to Chroma
            total_docs = len(documents)
            logger.info(f"Total documents to index: {total_docs}")
            if documents:
                batch_size = 2000
                for i in range(0, len(documents), batch_size):
                    collection.upsert(
                        documents=documents[i:i+batch_size],
                        metadatas=metadatas[i:i+batch_size],
                        ids=ids[i:i+batch_size]
                    )
                logger.info(f"Successfully indexed {total_docs} documents to Chroma for {repo_name}")
            else:
                logger.warning(f"No documents to index for {repo_name} (analysis {latest_analysis.id})")

            set_task_status(repo_name, "semantic_index", "completed", current_user, bg_db)
        except Exception as e:
            logger.error(f"Semantic index build failed for {repo_name}: {str(e)}", exc_info=True)
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

