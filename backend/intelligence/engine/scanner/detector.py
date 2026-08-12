import os
from pathlib import Path
from typing import Dict, Optional, List

class LanguageDetector:
    """
    Detects programming languages based on file extensions or names.
    """
    EXTENSION_MAP = {
        ".py": {"name": "Python", "code": True},
        ".js": {"name": "JavaScript", "code": True},
        ".jsx": {"name": "JavaScript", "code": True},
        ".ts": {"name": "TypeScript", "code": True},
        ".tsx": {"name": "TypeScript", "code": True},
        ".go": {"name": "Go", "code": True},
        ".java": {"name": "Java", "code": True},
        ".rs": {"name": "Rust", "code": True},
        ".cs": {"name": "C#", "code": True},
        ".php": {"name": "PHP", "code": True},
        ".rb": {"name": "Ruby", "code": True},
        ".json": {"name": "JSON", "code": False},
        ".yml": {"name": "YAML", "code": False},
        ".yaml": {"name": "YAML", "code": False},
        ".md": {"name": "Markdown", "code": False},
        ".toml": {"name": "TOML", "code": False},
        ".xml": {"name": "XML", "code": False},
        ".html": {"name": "HTML", "code": True},
        ".css": {"name": "CSS", "code": True},
        ".sql": {"name": "SQL", "code": True},
        ".sh": {"name": "Shell", "code": True}
    }

    FILE_NAME_MAP = {
        "Dockerfile": {"name": "Dockerfile", "code": True},
        "Makefile": {"name": "Makefile", "code": True}
    }

    @classmethod
    def detect_language(cls, path: str) -> str:
        """
        Return the detected language for a given file path.
        Returns 'Unknown' if it cannot be determined.
        """
        p = Path(path)
        if p.name in cls.FILE_NAME_MAP:
            return cls.FILE_NAME_MAP[p.name]["name"]
            
        ext = p.suffix.lower()
        if ext in cls.EXTENSION_MAP:
            return cls.EXTENSION_MAP[ext]["name"]
            
        return "Unknown"

    @classmethod
    def is_code_language(cls, lang_name: str) -> bool:
        """Return True if the language name is considered source code."""
        for val in cls.EXTENSION_MAP.values():
            if val["name"] == lang_name:
                return val["code"]
        for val in cls.FILE_NAME_MAP.values():
            if val["name"] == lang_name:
                return val["code"]
        return False

class FrameworkDetector:
    """
    Detects frameworks based on dependency files.
    """
    @classmethod
    def detect_frameworks(cls, target_dir: str) -> List[str]:
        frameworks = set()
        target = Path(target_dir)
        
        # Check requirements.txt
        req_file = target / "requirements.txt"
        if req_file.exists():
            try:
                import re
                lines = req_file.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    line = line.strip().lower()
                    if re.match(r'^fastapi([\s><=]|$)', line): frameworks.add("FastAPI")
                    if re.match(r'^flask([\s><=]|$)', line): frameworks.add("Flask")
                    if re.match(r'^django([\s><=]|$)', line): frameworks.add("Django")
            except Exception:
                pass
                
        # Check pyproject.toml
        pyproject_file = target / "pyproject.toml"
        if pyproject_file.exists():
            try:
                import tomllib
                content = pyproject_file.read_text(encoding="utf-8")
                parsed = tomllib.loads(content)
                
                # Check [project.dependencies]
                deps = parsed.get("project", {}).get("dependencies", [])
                
                # Check [tool.poetry.dependencies]
                poetry_deps = parsed.get("tool", {}).get("poetry", {}).get("dependencies", {})
                
                all_deps = list(deps) + list(poetry_deps.keys())
                
                for dep in all_deps:
                    dep = dep.lower()
                    if dep.startswith("fastapi"): frameworks.add("FastAPI")
                    if dep.startswith("flask"): frameworks.add("Flask")
                    if dep.startswith("django"): frameworks.add("Django")
            except Exception:
                pass
                
        return sorted(list(frameworks))
