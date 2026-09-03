#!/usr/bin/env python3
"""
Cleanup script to remove orphaned blob files from Azure Blob Storage.

This script removes blobs that reference repositories no longer in the database.
It's safe to run after the repository ID migration.

Usage:
  python scripts/cleanup_orphaned_blobs.py --dry-run    # Show what would be deleted
  python scripts/cleanup_orphaned_blobs.py --confirm    # Actually delete files
"""

import os
import sys
import logging
import argparse

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database import SessionLocal
from backend.models.repository import Repository
from backend.storage import get_storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_repo_id_from_blob_key(blob_key: str) -> str:
    """
    Extract repository ID from blob storage key.

    Examples:
      "repos/1/file.py" → "1"
      "repos/123/analysis.json" → "123"
      "repos/mixed/data" → "mixed" (for local mode repos)
    """
    parts = blob_key.split('/')
    if len(parts) >= 2 and parts[0] == 'repos':
        return parts[1]
    return None


def cleanup_orphaned_blobs(dry_run: bool = True):
    """
    Find and remove orphaned blob files.

    Args:
      dry_run: If True, only print what would be deleted (default)
               If False, actually delete the files
    """
    db = SessionLocal()
    storage = get_storage()

    try:
        # Get all valid repository IDs
        repos = db.query(Repository).all()
        valid_repo_ids = {str(r.id) for r in repos}
        logger.info(f"Found {len(valid_repo_ids)} valid repositories in database")
        logger.info(f"Valid repo IDs: {sorted(valid_repo_ids)}")
        logger.info()

        # List all blobs
        logger.info("Scanning blob storage for orphaned files...")
        all_blobs = storage.list_objects("repos/")
        logger.info(f"Found {len(all_blobs)} total blobs in storage\n")

        # Find orphaned blobs
        orphaned_blobs = []
        for blob_key in all_blobs:
            repo_id = extract_repo_id_from_blob_key(blob_key)
            if repo_id and repo_id not in valid_repo_ids:
                orphaned_blobs.append(blob_key)

        if not orphaned_blobs:
            logger.info("✓ No orphaned blobs found!")
            return True

        # Report findings
        logger.warning(f"Found {len(orphaned_blobs)} orphaned blob(s):")

        for i, blob_key in enumerate(orphaned_blobs, 1):
            logger.warning(f"  {i}. {blob_key}")

        logger.info(" ")

        if dry_run:
            logger.info(f"DRY RUN: Would delete {len(orphaned_blobs)} blobs")
            logger.info("Run with --confirm to actually delete files")
            return True

        # Actually delete
        logger.warning(f"DELETING {len(orphaned_blobs)} orphaned blob(s)...")
        deleted_count = 0
        errors = []

        for blob_key in orphaned_blobs:
            try:
                storage.delete_object(blob_key)
                logger.info(f"  ✓ Deleted: {blob_key}")
                deleted_count += 1
            except Exception as e:
                error_msg = f"  ✗ Failed to delete {blob_key}: {e}"
                logger.error(error_msg)
                errors.append((blob_key, error_msg))

        logger.info(" ")
        logger.info(f"✓ Successfully deleted {deleted_count}/{len(orphaned_blobs)} blobs")

        if errors:
            logger.error(f"✗ {len(errors)} deletion(s) failed:")
            for blob_key, error_msg in errors:
                logger.error(error_msg)
            return False

        logger.info("✓ Cleanup completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Cleanup failed with error: {e}")
        return False
    finally:
        db.close()


def verify_after_cleanup():
    """
    Verify blob storage consistency after cleanup.
    """
    db = SessionLocal()
    storage = get_storage()

    try:
        # Get valid repo IDs
        repos = db.query(Repository).all()
        valid_repo_ids = {str(r.id) for r in repos}

        # List all blobs
        all_blobs = storage.list_objects("repos/")

        logger.info("\n=== Blob Storage Verification ===")
        logger.info(f"Repositories in database: {len(valid_repo_ids)}")
        logger.info(f"Blob directories in storage: {len(set(b.split('/')[1] for b in all_blobs if '/' in b))}")

        # Check for any remaining orphans
        remaining_orphans = 0
        for blob_key in all_blobs:
            repo_id = extract_repo_id_from_blob_key(blob_key)
            if repo_id and repo_id not in valid_repo_ids:
                logger.warning(f"  ⚠️  Orphaned blob still exists: {blob_key}")
                remaining_orphans += 1

        if remaining_orphans == 0:
            logger.info("✓ No orphaned blobs found - storage is clean!")
        else:
            logger.error(f"✗ {remaining_orphans} orphaned blob(s) still in storage")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cleanup orphaned blob files from Azure Blob Storage"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete files (default is dry-run)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify blob storage after cleanup"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Blob Storage Cleanup Script")
    logger.info("=" * 60)
    logger.info()

    if not args.confirm:
        logger.info("Running in DRY-RUN mode (no files will be deleted)")
        logger.info("Use --confirm flag to actually delete files\n")

    # Run cleanup
    success = cleanup_orphaned_blobs(dry_run=not args.confirm)

    # Verify if requested
    if success and (args.verify or args.confirm):
        verify_after_cleanup()

    logger.info("\n" + "=" * 60)
    if success:
        logger.info("Cleanup process completed!")
    else:
        logger.error("Cleanup process failed!")
        sys.exit(1)
    logger.info("=" * 60)
