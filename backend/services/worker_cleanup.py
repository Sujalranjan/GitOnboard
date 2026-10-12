"""
Cleanup routines for orphaned Azure blobs and database records
to prevent desynchronization during failed or deleted analysis runs.
"""
from __future__ import annotations

import logging
from backend.database import SessionLocal
from backend.models.repository import Analysis, AnalysisJob

logger = logging.getLogger(__name__)


def cleanup_orphaned_blobs(repo_id: int, snapshot_id: str = ""):
    """
    Remove orphaned blobs from Azure if repository/analysis is deleted.
    Prevents desynchronization between database and blob storage.
    """
    try:
        from backend.storage import get_storage
        storage = get_storage()
        container_client = storage.service_client.get_container_client(storage.container_name)

        # If snapshot_id is empty, search all snapshots for this repo
        if snapshot_id:
            prefix = f"repositories/{repo_id}/snapshots/{snapshot_id}"
        else:
            prefix = f"repositories/{repo_id}/snapshots/"

        blobs_to_delete = list(container_client.list_blobs(name_starts_with=prefix))

        if blobs_to_delete:
            logger.info(f"[DESYNC_CLEANUP] Found {len(blobs_to_delete)} orphaned blobs for repo {repo_id}")

            # Delete blobs
            for blob in blobs_to_delete:
                try:
                    container_client.delete_blob(blob.name)
                    logger.debug(f"[DESYNC_CLEANUP] Deleted blob: {blob.name}")
                except Exception as blob_err:
                    logger.warning(f"[DESYNC_CLEANUP] Failed to delete blob {blob.name}: {blob_err}")

            logger.info(f"[DESYNC_CLEANUP] Cleaned up {len(blobs_to_delete)} orphaned blobs from Azure")
        else:
            logger.info(f"[DESYNC_CLEANUP] No orphaned blobs found for repo {repo_id}")

    except Exception as e:
        logger.error(f"[DESYNC_CLEANUP] Failed to clean up orphaned blobs: {e}", exc_info=True)


def cleanup_orphaned_database_records(analysis_id: int, job_id: int):
    """
    Remove orphaned database records if blob upload or analysis fails.
    Prevents desynchronization between database and blob storage.
    """
    db = None
    try:
        db = SessionLocal()

        logger.info(f"[DESYNC_CLEANUP] Cleaning orphaned database records for Analysis {analysis_id}")

        # Delete job
        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).delete()

        # Delete analysis (and related fact store records via cascade)
        db.query(Analysis).filter(Analysis.id == analysis_id).delete()

        db.commit()
        logger.info(f"[DESYNC_CLEANUP] Deleted orphaned Analysis {analysis_id} and Job {job_id} from database")

    except Exception as e:
        logger.error(f"[DESYNC_CLEANUP] Failed to clean up database records: {e}", exc_info=True)
        if db:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass
