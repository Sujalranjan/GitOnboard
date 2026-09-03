#!/usr/bin/env python3
"""
Diagnostic script to test the import flow end-to-end.
Simulates importing two different repositories and logs every step.
"""

import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.services.github import check_repo_limits

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_import_flow():
    """
    Test importing two different repositories and verify they're stored correctly.
    """
    db = SessionLocal()

    try:
        # Create or get test user
        user = db.query(User).filter(User.email == "test@example.com").first()
        if not user:
            user = User(
                github_id="test-user",
                username="testuser",
                email="test@example.com"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Created test user ID={user.id}")
        else:
            logger.info(f"Using existing test user ID={user.id}")

        print("\n" + "=" * 60)
        print("IMPORT FLOW DIAGNOSTIC TEST")
        print("=" * 60 + "\n")

        # Test 1: Import first repo
        print("TEST 1: Importing first repository")
        print("-" * 40)

        owner1 = "owner"
        repo_name1 = "test-repo-1"
        url1 = f"https://github.com/{owner1}/{repo_name1}"

        logger.info(f"[TEST1] Getting repo limits for {owner1}/{repo_name1}")
        limit_data1 = await check_repo_limits(owner1, repo_name1)
        logger.info(f"[TEST1] check_repo_limits returned: {limit_data1}")

        existing_repo1 = db.query(Repository).filter(
            Repository.user_id == user.id,
            Repository.github_repo_id == limit_data1["github_repo_id"]
        ).first()

        if not existing_repo1:
            logger.info(f"[TEST1] No existing repo found, creating new one")
            repo1 = Repository(
                github_repo_id=limit_data1["github_repo_id"],
                url=url1,
                default_branch=limit_data1["default_branch"],
                user_id=user.id
            )
            db.add(repo1)
            db.commit()
            db.refresh(repo1)
            logger.info(f"[TEST1] Created repo ID={repo1.id}, github_repo_id='{repo1.github_repo_id}'")
        else:
            repo1 = existing_repo1
            logger.info(f"[TEST1] Found existing repo ID={repo1.id}")

        print(f"✓ Repo 1: ID={repo1.id}, URL={repo1.url}, github_repo_id='{repo1.github_repo_id}'")
        print()

        # Test 2: Import second repo
        print("TEST 2: Importing second repository")
        print("-" * 40)

        owner2 = "owner"
        repo_name2 = "test-repo-2"
        url2 = f"https://github.com/{owner2}/{repo_name2}"

        logger.info(f"[TEST2] Getting repo limits for {owner2}/{repo_name2}")
        limit_data2 = await check_repo_limits(owner2, repo_name2)
        logger.info(f"[TEST2] check_repo_limits returned: {limit_data2}")

        existing_repo2 = db.query(Repository).filter(
            Repository.user_id == user.id,
            Repository.github_repo_id == limit_data2["github_repo_id"]
        ).first()

        if not existing_repo2:
            logger.info(f"[TEST2] No existing repo found, creating new one")
            repo2 = Repository(
                github_repo_id=limit_data2["github_repo_id"],
                url=url2,
                default_branch=limit_data2["default_branch"],
                user_id=user.id
            )
            db.add(repo2)
            db.commit()
            db.refresh(repo2)
            logger.info(f"[TEST2] Created repo ID={repo2.id}, github_repo_id='{repo2.github_repo_id}'")
        else:
            repo2 = existing_repo2
            logger.info(f"[TEST2] Found existing repo ID={repo2.id}")

        print(f"✓ Repo 2: ID={repo2.id}, URL={repo2.url}, github_repo_id='{repo2.github_repo_id}'")
        print()

        # Verification
        print("VERIFICATION")
        print("-" * 40)

        all_repos = db.query(Repository).filter(Repository.user_id == user.id).all()
        print(f"Total repos for user: {len(all_repos)}\n")

        for repo in all_repos:
            analyses = db.query(Analysis).filter(Analysis.repository_id == repo.id).all()
            print(f"Repo ID: {repo.id}")
            print(f"  URL: {repo.url}")
            print(f"  github_repo_id: '{repo.github_repo_id}'")
            print(f"  Analyses: {len(analyses)}")
            print()

        # Final checks
        print("CHECKS")
        print("-" * 40)

        if len(all_repos) >= 2:
            print("✅ Multiple repos stored in database")
        else:
            print(f"❌ Only {len(all_repos)} repo(s) in database - FAILURE!")
            return False

        if repo1.github_repo_id != repo2.github_repo_id:
            print("✅ Repos have different github_repo_ids")
        else:
            print(f"❌ Repos have SAME github_repo_id - FAILURE!")
            return False

        if repo1.url != repo2.url:
            print("✅ Repos have different URLs")
        else:
            print(f"❌ Repos have SAME URL - FAILURE!")
            return False

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Import flow is working correctly!")
        print("=" * 60)
        return True

    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = asyncio.run(test_import_flow())
    sys.exit(0 if success else 1)
