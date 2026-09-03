#!/usr/bin/env python3
"""
Complete data reset script.
Removes ALL repositories, analyses, symbols, embeddings, and blob storage data.
WARNING: This is DESTRUCTIVE and cannot be undone!
"""

import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisArtifact, AnalysisJob
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship, FactRoute
from backend.storage import get_storage
from sqlalchemy import func, text

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def count_records(db):
    """Count all data that will be deleted"""
    print("\n=== DATA TO BE DELETED ===\n")

    repos_count = db.query(Repository).count()
    analyses_count = db.query(Analysis).count()
    artifacts_count = db.query(AnalysisArtifact).count()
    jobs_count = db.query(AnalysisJob).count()
    fact_files_count = db.query(FactFile).count()
    symbols_count = db.query(FactSymbol).count()
    relationships_count = db.query(FactRelationship).count()
    routes_count = db.query(FactRoute).count()

    print(f"Repositories:         {repos_count}")
    print(f"Analyses:             {analyses_count}")
    print(f"Analysis Artifacts:   {artifacts_count}")
    print(f"Analysis Jobs:        {jobs_count}")
    print(f"Fact Files:           {fact_files_count}")
    print(f"Fact Symbols:         {symbols_count}")
    print(f"Fact Relationships:   {relationships_count}")
    print(f"Fact Routes:          {routes_count}")

    total_db = (repos_count + analyses_count + artifacts_count + jobs_count +
                fact_files_count + symbols_count + relationships_count + routes_count)
    print(f"\nTotal DB Records:     {total_db}")

    return {
        "repos": repos_count,
        "analyses": analyses_count,
        "artifacts": artifacts_count,
        "jobs": jobs_count,
        "fact_files": fact_files_count,
        "symbols": symbols_count,
        "relationships": relationships_count,
        "routes": routes_count,
        "total": total_db
    }


def count_blob_objects(storage):
    """Count objects in blob storage"""
    try:
        all_blobs = storage.list_objects("repos/")
        print(f"\nBlob Storage Objects: {len(all_blobs)}")
        return len(all_blobs)
    except Exception as e:
        logger.warning(f"Could not count blob objects: {e}")
        return 0


def confirm_deletion():
    """Ask for confirmation before deleting"""
    print("\n" + "=" * 60)
    print("⚠️  WARNING: THIS WILL DELETE ALL DATA!")
    print("=" * 60)
    print("\nThis will permanently delete:")
    print("  • All repositories")
    print("  • All analyses and analysis jobs")
    print("  • All analysis artifacts")
    print("  • All fact files and symbols")
    print("  • All embeddings")
    print("  • All blob storage files")
    print("\nThis action CANNOT be undone!")
    print("\nType 'YES DELETE ALL' to confirm (case-sensitive):")

    confirmation = input("> ").strip()
    return confirmation == "YES DELETE ALL"


def reset_all_data():
    """Delete all data from database and blob storage"""
    db = SessionLocal()
    storage = get_storage()

    try:
        # Count data first
        counts = count_records(db)
        blob_count = count_blob_objects(storage)

        if counts["total"] == 0 and blob_count == 0:
            print("\n✅ Database and blob storage are already empty!")
            return True

        # Ask for confirmation
        if not confirm_deletion():
            print("\n❌ Deletion cancelled.")
            return False

        print("\n" + "=" * 60)
        print("STARTING DELETION...")
        print("=" * 60 + "\n")

        # Delete from database (in dependency order)
        logger.info("Deleting fact routes...")
        db.query(FactRoute).delete()
        db.commit()
        logger.info(f"✓ Deleted {counts['routes']} routes")

        logger.info("Deleting fact relationships...")
        db.query(FactRelationship).delete()
        db.commit()
        logger.info(f"✓ Deleted {counts['relationships']} relationships")

        logger.info("Deleting fact symbols...")
        db.query(FactSymbol).delete()
        db.commit()
        logger.info(f"✓ Deleted {counts['symbols']} symbols")

        logger.info("Deleting fact files...")
        db.query(FactFile).delete()
        db.commit()
        logger.info(f"✓ Deleted {counts['fact_files']} fact files")

        logger.info("Deleting analysis jobs...")
        db.query(AnalysisJob).delete()
        db.commit()
        logger.info(f"✓ Deleted {counts['jobs']} analysis jobs")

        logger.info("Deleting analysis artifacts...")
        db.query(AnalysisArtifact).delete()
        db.commit()
        logger.info(f"✓ Deleted {counts['artifacts']} artifacts")

        logger.info("Deleting analyses...")
        db.query(Analysis).delete()
        db.commit()
        logger.info(f"✓ Deleted {counts['analyses']} analyses")

        logger.info("Deleting repositories...")
        db.query(Repository).delete()
        db.commit()
        logger.info(f"✓ Deleted {counts['repos']} repositories")

        # Delete from blob storage
        if blob_count > 0:
            logger.info("Deleting blob storage objects...")
            all_blobs = storage.list_objects("repos/")
            deleted_count = 0
            for blob_key in all_blobs:
                try:
                    storage.delete_object(blob_key)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete blob {blob_key}: {e}")

            logger.info(f"✓ Deleted {deleted_count}/{blob_count} blob objects")

        # Verify deletion
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60 + "\n")

        final_repos = db.query(Repository).count()
        final_analyses = db.query(Analysis).count()
        final_artifacts = db.query(AnalysisArtifact).count()
        final_jobs = db.query(AnalysisJob).count()
        final_fact_files = db.query(FactFile).count()
        final_symbols = db.query(FactSymbol).count()
        final_relationships = db.query(FactRelationship).count()
        final_routes = db.query(FactRoute).count()
        final_blobs = len(storage.list_objects("repos/"))

        print(f"Repositories:        {final_repos} (was {counts['repos']})")
        print(f"Analyses:            {final_analyses} (was {counts['analyses']})")
        print(f"Analysis Artifacts:  {final_artifacts} (was {counts['artifacts']})")
        print(f"Analysis Jobs:       {final_jobs} (was {counts['jobs']})")
        print(f"Fact Files:          {final_fact_files} (was {counts['fact_files']})")
        print(f"Fact Symbols:        {final_symbols} (was {counts['symbols']})")
        print(f"Fact Relationships:  {final_relationships} (was {counts['relationships']})")
        print(f"Fact Routes:         {final_routes} (was {counts['routes']})")
        print(f"Blob Objects:        {final_blobs} (was {blob_count})")

        total_deleted = counts["total"] + blob_count
        if final_repos == 0 and final_analyses == 0 and final_blobs == 0:
            print("\n" + "=" * 60)
            print(f"✅ CLEANUP COMPLETE - Deleted {total_deleted} total records/objects")
            print("=" * 60)
            print("\n✅ Database and blob storage are now CLEAN!")
            print("✅ Ready to import new repositories!\n")
            return True
        else:
            print("\n❌ Some data may not have been deleted:")
            if final_repos > 0:
                print(f"  - {final_repos} repositories still remain")
            if final_analyses > 0:
                print(f"  - {final_analyses} analyses still remain")
            if final_blobs > 0:
                print(f"  - {final_blobs} blob objects still remain")
            return False

    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        print(f"\n❌ Cleanup failed: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE AND BLOB STORAGE RESET TOOL")
    print("=" * 60)

    success = reset_all_data()
    sys.exit(0 if success else 1)
