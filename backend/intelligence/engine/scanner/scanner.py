import os
import subprocess
from pathlib import Path
from typing import Set, Dict
from collections import defaultdict

from .manifest import RepositoryManifest, RepositoryFile, Package, RepositoryMetadata
from .detector import LanguageDetector, FrameworkDetector

class RepositoryScanner:
    """
    Scans a repository directory to build a RepositoryManifest.
    Respects common ignore patterns.
    """
    
    DEFAULT_IGNORES = {
        ".git", "node_modules", "venv", ".venv", "env", ".env", 
        "__pycache__", "build", "dist", ".idea", ".vscode"
    }

    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir).resolve()
        
    def _get_git_metadata(self) -> RepositoryMetadata:
        metadata = RepositoryMetadata()
        try:
            # Check if it's a git repo
            subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=self.target_dir, check=True, capture_output=True)
            
            # Get commit hash
            commit_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.target_dir, capture_output=True, text=True)
            if commit_res.returncode == 0:
                metadata.commit_hash = commit_res.stdout.strip()
                
            # Get commit timestamp
            time_res = subprocess.run(["git", "log", "-1", "--format=%cI"], cwd=self.target_dir, capture_output=True, text=True)
            if time_res.returncode == 0:
                metadata.commit_timestamp = time_res.stdout.strip()
                
            # Get branch
            branch_res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.target_dir, capture_output=True, text=True)
            if branch_res.returncode == 0:
                metadata.branch = branch_res.stdout.strip()
                
            # Get remote URL
            remote_res = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=self.target_dir, capture_output=True, text=True)
            if remote_res.returncode == 0:
                metadata.remote_url = remote_res.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
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
                if file.startswith("."):
                    continue
                    
                full_path = root_path / file
                rel_path = str(full_path.relative_to(self.target_dir)).replace("\\", "/")
                
                try:
                    size = full_path.stat().st_size
                except Exception:
                    size = 0
                    
                lang = LanguageDetector.detect_language(rel_path)
                if lang != "Unknown":
                    language_set.add(lang)
                    language_sizes[lang] += size
                    
                repo_file = RepositoryFile(
                    path=rel_path,
                    name=file,
                    extension=full_path.suffix.lower(),
                    size=size,
                    language=lang
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
