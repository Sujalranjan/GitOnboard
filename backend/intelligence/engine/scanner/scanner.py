import os
import subprocess
from pathlib import Path
from typing import Set, Dict
from collections import defaultdict

from .manifest import RepositoryManifest, RepositoryFile, Package, RepositoryMetadata
from .detector import LanguageDetector, FrameworkDetector
from .eligibility import FileEligibility, FileCategory

class RepositoryScanner:
    """
    Scans a repository directory to build a RepositoryManifest.
    Uses centralized file eligibility to exclude dependencies, build artifacts, caches, etc.
    Preserves ALL discovered files in manifest but marks them with their category.
    """

    # Comprehensive exclusions (prevents os.walk from traversing these directories)
    DEFAULT_IGNORES = {
        # Original
        ".git", "node_modules", "venv", ".venv", "env", ".env",
        "__pycache__", "build", "dist", ".idea", ".vscode",

        # Extended: Python caches
        ".pytest_cache", ".mypy_cache", ".ruff_cache", ".pyre", ".pytype",
        ".tox", ".nox", ".hypothesis", ".coverage", "htmlcov",
        ".eggs", "site-packages",

        # Extended: JavaScript/Node
        ".next", ".nuxt", ".cache", ".parcel-cache", ".turbo", ".turbopack",
        ".webpack", ".babel-cache", ".rollup.cache", ".rts2_cache_*",
        ".eslintcache", ".stylelintcache", ".tsdist", ".jest", ".vitest",
        ".mocha", ".nyc_output", "jest", "playwright-report", "blob-report",
        "test-results", "coverage",

        # Extended: Build output
        "out", "target", ".docusaurus", "_site", "_book", "site", ".vuepress",

        # Extended: IDE/Editors
        ".vim", ".sublime-*", ".DS_Store",

        # Extended: CI/CD
        ".circleci", ".gitlab-ci", ".travis",
    }

    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir).resolve()
        # Convert to string for subprocess (handles Windows paths correctly)
        self.target_dir_str = str(self.target_dir)
        
    def _get_git_metadata(self) -> RepositoryMetadata:
        metadata = RepositoryMetadata()
        try:
            # Check if directory exists first
            if not self.target_dir.exists():
                return metadata

            # Try to check if it's a git repo (fail silently if git unavailable)
            try:
                subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=self.target_dir_str, check=True, capture_output=True, timeout=5)
            except (subprocess.CalledProcessError, FileNotFoundError, OSError):
                # Git not available or not a git repo - return minimal metadata
                return metadata

            # Get commit hash
            commit_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.target_dir_str, capture_output=True, text=True, timeout=5)
            if commit_res.returncode == 0:
                metadata.commit_hash = commit_res.stdout.strip()

            # Get commit timestamp
            time_res = subprocess.run(["git", "log", "-1", "--format=%cI"], cwd=self.target_dir_str, capture_output=True, text=True, timeout=5)
            if time_res.returncode == 0:
                metadata.commit_timestamp = time_res.stdout.strip()

            # Get branch
            branch_res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.target_dir_str, capture_output=True, text=True, timeout=5)
            if branch_res.returncode == 0:
                metadata.branch = branch_res.stdout.strip()

            # Get remote URL
            remote_res = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=self.target_dir_str, capture_output=True, text=True, timeout=5)
            if remote_res.returncode == 0:
                metadata.remote_url = remote_res.stdout.strip()
        except Exception:
            # Silently fail - git metadata is optional
            pass

        return metadata

    def scan(self) -> RepositoryManifest:
        manifest = RepositoryManifest()
        manifest.metadata = self._get_git_metadata()
        manifest.frameworks = FrameworkDetector.detect_frameworks(str(self.target_dir))
        
        language_set: Set[str] = set()
        language_sizes: Dict[str, int] = defaultdict(int)
        
        for root, dirs, files in os.walk(self.target_dir):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in self.DEFAULT_IGNORES]
            
            root_path = Path(root)
            
            # Detect packages (simple heuristic: look for package.json, requirements.txt, Cargo.toml)
            if "package.json" in files:
                rel_path = str(root_path.relative_to(self.target_dir)).replace("\\", "/")
                manifest.packages.append(Package(path=rel_path if rel_path != "." else "/", name=root_path.name, type="npm"))
            elif "requirements.txt" in files or "pyproject.toml" in files:
                rel_path = str(root_path.relative_to(self.target_dir)).replace("\\", "/")
                manifest.packages.append(Package(path=rel_path if rel_path != "." else "/", name=root_path.name, type="pip"))
            elif "Cargo.toml" in files:
                rel_path = str(root_path.relative_to(self.target_dir)).replace("\\", "/")
                manifest.packages.append(Package(path=rel_path if rel_path != "." else "/", name=root_path.name, type="cargo"))
            elif "pom.xml" in files:
                rel_path = str(root_path.relative_to(self.target_dir)).replace("\\", "/")
                manifest.packages.append(Package(path=rel_path if rel_path != "." else "/", name=root_path.name, type="maven"))
                
            for file in files:
                full_path = root_path / file
                rel_path = str(full_path.relative_to(self.target_dir)).replace("\\", "/")

                try:
                    size = full_path.stat().st_size
                except Exception:
                    size = 0

                # Classify the file
                category = FileEligibility.classify_file(rel_path)

                lang = LanguageDetector.detect_language(rel_path)
                if lang != "Unknown":
                    language_set.add(lang)
                    language_sizes[lang] += size

                repo_file = RepositoryFile(
                    path=rel_path,
                    name=file,
                    extension=full_path.suffix.lower(),
                    size=size,
                    language=lang,
                    category=category.value
                )
                manifest.files.append(repo_file)
                
        manifest.languages = sorted(list(language_set))
        if language_sizes:
            # Prefer code languages over text/docs
            code_sizes = {k: v for k, v in language_sizes.items() if LanguageDetector.is_code_language(k)}
            
            if code_sizes:
                manifest.primary_language = max(code_sizes.items(), key=lambda x: x[1])[0]
            else:
                manifest.primary_language = max(language_sizes.items(), key=lambda x: x[1])[0]
            
        return manifest
