import httpx
import logging
import io
import zipfile
import tempfile
import os
import shutil
from pathlib import Path
from fastapi import HTTPException
from backend.config import settings

logger = logging.getLogger(__name__)

async def get_github_client(token: str = None) -> httpx.AsyncClient:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return httpx.AsyncClient(headers=headers, timeout=10.0)

async def check_repo_limits(owner: str, repo: str, token: str = None):
    """Pre-flight check for repository size."""
    # Skip GitHub API calls in LOCAL mode
    if settings.deployment_type == "LOCAL":
        return {
            "github_repo_id": "local",
            "default_branch": "main",
            "size_kb": 1024
        }

    async with await get_github_client(token) as client:
        resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}")

        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Repository not found or you don't have access.")
        elif resp.status_code == 401:
            raise HTTPException(status_code=401, detail="GitHub token expired or invalid.")
        elif resp.status_code == 403:
            raise HTTPException(status_code=403, detail="GitHub API rate limit exceeded.")

        resp.raise_for_status()
        data = resp.json()

        size_kb = data.get("size", 0)
        # Size limit 500MB
        if size_kb > 500 * 1024:
            raise HTTPException(status_code=400, detail=f"Repository size ({size_kb / 1024:.1f}MB) exceeds 500MB limit.")

        return {
            "github_repo_id": str(data.get("id")),
            "default_branch": data.get("default_branch"),
            "size_kb": size_kb
        }

async def download_repo_zipball(owner: str, repo: str, branch: str, target_dir: str, token: str = None):
    """Downloads zipball and extracts to target_dir. Returns file count and commit metadata."""
    import subprocess

    logger.info(f"download_repo_zipball called: owner={owner}, repo={repo}, deployment_type={settings.deployment_type}")

    # In LOCAL mode, use git clone to avoid GitHub API calls
    if settings.deployment_type == "LOCAL":
        logger.info(f"LOCAL mode: Using git clone for {owner}/{repo}")
        os.makedirs(target_dir, exist_ok=True)

        try:
            git_url = f"https://github.com/{owner}/{repo}.git"
            # Clone the repository (without history for speed)
            result = subprocess.run(
                ["git", "clone", "--depth=1", "--branch", branch, git_url, target_dir],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                logger.warning(f"Git clone failed: {result.stderr}, falling back to empty repo")
                return {"file_count": 0, "commit_info": {
                    "hash": "local_clone_failed",
                    "timestamp": None,
                    "branch": branch,
                    "remote_url": git_url
                }}

            # Count files (excluding .git)
            file_count = 0
            for root, dirs, files in os.walk(target_dir):
                # Skip .git directory
                dirs[:] = [d for d in dirs if d != '.git']
                file_count += len([f for f in files if not f.startswith('.')])

            logger.info(f"Git clone successful: {file_count} files downloaded")
            return {"file_count": file_count, "commit_info": {
                "hash": "local_clone",
                "timestamp": None,
                "branch": branch,
                "remote_url": git_url
            }}
        except Exception as e:
            logger.warning(f"LOCAL mode git clone error: {e}, returning empty")
            return {"file_count": 0, "commit_info": {
                "hash": "local_clone_error",
                "timestamp": None,
                "branch": branch,
                "remote_url": f"https://github.com/{owner}/{repo}.git"
            }}

    url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    logger.info(f"Downloading zipball from {url}")

    commit_info = {
        "hash": None,
        "timestamp": None,
        "branch": branch,
        "remote_url": f"https://github.com/{owner}/{repo}.git"
    }

    async with await get_github_client(token) as client:
        # Fetch commit metadata first
        try:
            commit_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}")
            if commit_resp.status_code == 200:
                data = commit_resp.json()
                commit_info["hash"] = data.get("sha")
                commit_info["timestamp"] = data.get("commit", {}).get("author", {}).get("date")
        except Exception as e:
            logger.warning(f"Failed to fetch commit metadata: {e}")

        # Stream the download because it might be up to 500MB
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            
        try:
            async with client.stream("GET", url, follow_redirects=True) as response:
                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail="Repository zipball not found.")
                response.raise_for_status()
                with open(tmp_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
            
            logger.info("Extracting zipball...")
            file_count = 0
            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                # The root folder in github zipballs is usually Owner-Repo-CommitSha
                root_folder = zip_ref.namelist()[0].split('/')[0]
                
                for member in zip_ref.namelist():
                    if member.endswith('/'):
                        continue # Skip directories
                        
                    # Ignore common large generated directories
                    parts = member.split('/')
                    if any(ignore in parts for ignore in ['node_modules', 'dist', 'build', 'vendor', 'target', 'bin', '.git']):
                        continue
                        
                    # Extract single file to target_dir, removing the top-level folder
                    target_file = os.path.join(target_dir, os.path.relpath(member, root_folder))
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    
                    with zip_ref.open(member) as source, open(target_file, "wb") as target:
                        shutil.copyfileobj(source, target)
                    file_count += 1
                    
                    if file_count > 50000:
                        raise HTTPException(status_code=400, detail="Repository exceeds 50,000 files limit.")
                        
            return {"file_count": file_count, "commit_info": commit_info}
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

async def fetch_file_content(owner: str, repo: str, branch: str, filepath: str, token: str = None) -> str:
    """Fetch raw file content from GitHub API"""
    # Skip GitHub API calls in LOCAL mode
    if settings.deployment_type == "LOCAL":
        logger.info(f"LOCAL mode: Skipping GitHub file fetch for {owner}/{repo}/{filepath}")
        return ""

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filepath}?ref={branch}"
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Source code is unavailable because the repository could not be accessed. Previous analysis results are still available.")
        resp.raise_for_status()
        return resp.text
