#!/usr/bin/env python3
"""
Cleanup orphaned blob storage folders for deleted repositories.

This script removes blob storage data for repository IDs that no longer exist
in the PostgreSQL database.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import SessionLocal
from backend.models.repository import Repository
from backend.storage import get_storage


def cleanup_orphaned_blobs():
    """Remove blob storage for repositories that don't exist in database."""

    db = SessionLocal()
    try:
        # Get all repository IDs from database
        repos = db.query(Repository.id).all()
        db_repo_ids = {r[0] for r in repos}

        print(f"[Database] Found {len(db_repo_ids)} repositories: {sorted(db_repo_ids)}")

        # Get storage and list all repository folders
        storage = get_storage()
        all_blobs = list(storage.list_objects(prefix="repositories/"))

        # Extract unique repository IDs from blob paths
        blob_repo_ids = set()
        for blob_name in all_blobs:
            # blob_name format: "repositories/1/snapshots/..."
            parts = blob_name.split("/")
            if len(parts) >= 2 and parts[0] == "repositories":
                try:
                    repo_id = int(parts[1])
                    blob_repo_ids.add(repo_id)
                except ValueError:
                    pass

        print(f"[Blob Storage] Found {len(blob_repo_ids)} repository IDs: {sorted(blob_repo_ids)}")

        # Find orphaned repository IDs (in blobs but not in database)
        orphaned_ids = blob_repo_ids - db_repo_ids

        if not orphaned_ids:
            print("\n✅ No orphaned repositories found!")
            return

        print(f"\n⚠️  Found {len(orphaned_ids)} orphaned repository IDs: {sorted(orphaned_ids)}")

        # Show what will be deleted
        for repo_id in sorted(orphaned_ids):
            prefix = f"repositories/{repo_id}/"
            blobs_to_delete = [b for b in all_blobs if b.startswith(prefix)]
            print(f"\n  Repository {repo_id}:")
            print(f"    - Blobs to delete: {len(blobs_to_delete)}")

        # Confirm before deletion
        user_input = input(f"\nDelete {len(orphaned_ids)} orphaned repositories? (yes/no): ").strip().lower()

        if user_input != "yes":
            print("Cancelled.")
            return

        # Delete orphaned blobs
        total_deleted = 0
        for repo_id in sorted(orphaned_ids):
            prefix = f"repositories/{repo_id}/"
            print(f"\nDeleting repository {repo_id}...")
            deleted_count = storage.delete_prefix(prefix)
            print(f"  ✓ Deleted {deleted_count} blobs")
            total_deleted += deleted_count

        print(f"\n✅ Cleanup complete! Deleted {total_deleted} blobs total")

    finally:
        db.close()


if __name__ == "__main__":
    cleanup_orphaned_blobs()
