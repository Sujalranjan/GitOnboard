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
        # Get all repository IDs and UUID hashes from database
        repos = db.query(Repository).all()
        db_identifiers = set()
        for r in repos:
            db_identifiers.add(str(r.id))
            if r.repository_hash:
                db_identifiers.add(str(r.repository_hash))

        print(f"[Database] Found {len(repos)} repositories in database")

        # Get storage and list all repository folders
        storage = get_storage()
        all_blobs = list(storage.list_objects(prefix="repositories/"))

        # Extract unique repository prefixes from blob paths
        blob_prefixes = set()
        for blob_name in all_blobs:
            # blob_name format: "repositories/{hash_or_id}/snapshots/..."
            parts = blob_name.split("/")
            if len(parts) >= 2 and parts[0] == "repositories":
                blob_prefixes.add(parts[1])

        print(f"[Blob Storage] Found {len(blob_prefixes)} repository prefixes: {sorted(blob_prefixes)}")

        # Find orphaned repository prefixes (in blobs but not in database)
        orphaned_prefixes = blob_prefixes - db_identifiers

        if not orphaned_prefixes:
            print("\n✅ No orphaned repositories found!")
            return

        print(f"\n⚠️  Found {len(orphaned_prefixes)} orphaned repository prefixes: {sorted(orphaned_prefixes)}")

        # Show what will be deleted
        for prefix_key in sorted(orphaned_prefixes):
            prefix = f"repositories/{prefix_key}/"
            blobs_to_delete = [b for b in all_blobs if b.startswith(prefix)]
            print(f"\n  Repository {prefix_key}:")
            print(f"    - Blobs to delete: {len(blobs_to_delete)}")

        # Confirm before deletion
        user_input = input(f"\nDelete {len(orphaned_prefixes)} orphaned repositories? (yes/no): ").strip().lower()

        if user_input != "yes":
            print("Cancelled.")
            return

        # Delete orphaned blobs
        total_deleted = 0
        for prefix_key in sorted(orphaned_prefixes):
            prefix = f"repositories/{prefix_key}/"
            print(f"\nDeleting repository {prefix_key}...")
            deleted_count = storage.delete_prefix(prefix)
            print(f"  ✓ Deleted {deleted_count} blobs")
            total_deleted += deleted_count

        print(f"\n✅ Cleanup complete! Deleted {total_deleted} blobs total")

    finally:
        db.close()


if __name__ == "__main__":
    cleanup_orphaned_blobs()
