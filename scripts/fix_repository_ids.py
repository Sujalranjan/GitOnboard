#!/usr/bin/env python3
"""
Migration script to fix repository IDs in LOCAL mode.

This script addresses the repository import issue where all repos shared
github_repo_id="local", causing new imports to overwrite existing repos.

The fix generates unique IDs per repository: local-{owner}-{repo}
"""

import os
import sys
import logging
from urllib.parse import urlparse

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database import SessionLocal
from backend.models.repository import Repository
from backend.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_repo_url(url: str) -> tuple[str, str]:
    """
    Parse GitHub URL to extract owner and repo name.

    Examples:
      https://github.com/owner/repo -> ('owner', 'repo')
      https://github.com/owner/repo.git -> ('owner', 'repo')
    """
    # Remove trailing slash and .git suffix
    url = url.rstrip('/').rstrip('.git')

    # Parse URL
    parsed = urlparse(url)
    parts = parsed.path.strip('/').split('/')

    if len(parts) >= 2:
        owner = parts[-2]
        repo_name = parts[-1]
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        return owner, repo_name

    raise ValueError(f"Cannot parse GitHub URL: {url}")


def migrate_repo_ids():
    """
    Migrate existing repositories to use unique github_repo_ids in LOCAL mode.

    For PROD mode, this script is a no-op (github_repo_id comes from GitHub API).
    """
    db = SessionLocal()

    try:
        # Only apply migration in LOCAL mode
        if settings.deployment_type != "LOCAL":
            logger.info(f"Deployment type is {settings.deployment_type} (not LOCAL). Skipping migration.")
            return

        # Find all repos with github_repo_id = "local" or None
        repos_to_fix = db.query(Repository).filter(
            (Repository.github_repo_id == "local") |
            (Repository.github_repo_id == None)
        ).all()

        if not repos_to_fix:
            logger.info("✓ No repositories need migration.")
            return

        logger.info(f"Found {len(repos_to_fix)} repositories to migrate:")

        migrated_count = 0
        errors = []

        for repo in repos_to_fix:
            try:
                # Parse URL to get owner and repo name
                owner, repo_name = parse_repo_url(repo.url)

                # Generate new unique ID
                new_id = f"local-{owner}-{repo_name}"
                old_id = repo.github_repo_id

                # Update repository
                repo.github_repo_id = new_id
                logger.info(f"  ✓ Repo {repo.id}: {repo.url}")
                logger.info(f"      github_repo_id: '{old_id}' → '{new_id}'")

                migrated_count += 1

            except Exception as e:
                error_msg = f"  ✗ Repo {repo.id}: {repo.url} - Error: {e}"
                logger.error(error_msg)
                errors.append((repo.id, error_msg))

        # Commit changes
        if migrated_count > 0:
            db.commit()
            logger.info(f"✓ Successfully migrated {migrated_count} repositories")

        if errors:
            logger.error(f"✗ {len(errors)} repositories had errors:")
            for repo_id, error_msg in errors:
                logger.error(error_msg)
            logger.error("These repositories were NOT updated.")
            return False

        logger.info("✓ Migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def verify_migration():
    """
    Verify that migration was successful.
    Print summary of repository IDs.
    """
    db = SessionLocal()

    try:
        repos = db.query(Repository).all()

        logger.info("\n=== Repository ID Verification ===")
        logger.info(f"Total repositories: {len(repos)}\n")

        for repo in repos:
            logger.info(f"Repo ID {repo.id}:")
            logger.info(f"  URL: {repo.url}")
            logger.info(f"  github_repo_id: {repo.github_repo_id}")
            logger.info(f"  User ID: {repo.user_id}")

            # Check for issues
            if not repo.github_repo_id:
                logger.warning("  ⚠️  github_repo_id is None or empty!")
            elif settings.deployment_type == "LOCAL" and not repo.github_repo_id.startswith("local-"):
                logger.warning(f"  ⚠️  github_repo_id '{repo.github_repo_id}' doesn't follow LOCAL mode pattern!")
            else:
                logger.info("  ✓ ID format is correct")

            logger.info(" ")

        # Check for duplicate github_repo_ids per user
        logger.info("=== Duplicate Check ===")
        from sqlalchemy import func
        duplicates = db.query(
            Repository.user_id,
            Repository.github_repo_id,
            func.count(Repository.id).label('count')
        ).group_by(
            Repository.user_id,
            Repository.github_repo_id
        ).having(func.count(Repository.id) > 1).all()

        if duplicates:
            logger.error("✗ Found duplicate github_repo_ids:")
            for user_id, repo_id, count in duplicates:
                logger.error(f"  user_id={user_id}, github_repo_id='{repo_id}': {count} repositories")
        else:
            logger.info("✓ No duplicate github_repo_ids found")

    finally:
        db.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Repository ID Migration Script")
    logger.info("=" * 60)
    logger.info(" ")

    # Run migration
    success = migrate_repo_ids()

    if success is False:
        logger.error("Migration failed! Please review errors above.")
        sys.exit(1)

    # Verify results
    verify_migration()

    logger.info("=" * 60)
    logger.info("Migration complete!")
    logger.info("=" * 60)
