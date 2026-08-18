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
                content = pyproject_file.read_text(encoding="utf-8")
                all_deps = []
                try:
                    import tomllib
                    parsed = tomllib.loads(content)
                    
                    top_deps = parsed.get("dependencies", [])
                    project_deps = parsed.get("project", {}).get("dependencies", [])
                    poetry_deps = parsed.get("tool", {}).get("poetry", {}).get("dependencies", {})
                    
                    for d in [top_deps, project_deps, poetry_deps]:
                        if isinstance(d, list):
                            all_deps.extend(d)
                        elif isinstance(d, dict):
                            all_deps.extend(d.keys())
                except Exception:
                    pass
                
                for dep in all_deps:
                    dep = str(dep).lower()
                    if "fastapi" in dep: frameworks.add("FastAPI")
                    if "flask" in dep: frameworks.add("Flask")
                    if "django" in dep: frameworks.add("Django")
            except Exception:
                pass
                    
        # Check package.json

        pkg_file = target / "package.json"
        if pkg_file.exists():
            try:
                import json
                pkg_data = json.loads(pkg_file.read_text(encoding="utf-8"))
                deps = {}
                if isinstance(pkg_data.get("dependencies"), dict):
                    deps.update(pkg_data["dependencies"])
                if isinstance(pkg_data.get("devDependencies"), dict):
                    deps.update(pkg_data["devDependencies"])
                if isinstance(pkg_data.get("peerDependencies"), dict):
                    deps.update(pkg_data["peerDependencies"])
                
                js_framework_map = {
                    "react": "React",
                    "react-dom": "React",
                    "next": "Next.js",
                    "vue": "Vue",
                    "nuxt": "Nuxt",
                    "@angular/core": "Angular",
                    "svelte": "Svelte",
                    "@sveltejs/kit": "SvelteKit",
                    "express": "Express",
                    "nestjs": "NestJS",
                    "@nestjs/core": "NestJS",
                    "fastify": "Fastify",
                    "vite": "Vite",
                    "tailwindcss": "Tailwind CSS",
                    "redux": "Redux",
                    "@reduxjs/toolkit": "Redux",
                    "zustand": "Zustand",
                    "@tanstack/react-query": "TanStack Query",
                    "react-router": "React Router",
                    "react-router-dom": "React Router",
                    "remix": "Remix",
                    "@remix-run/react": "Remix",
                    "gatsby": "Gatsby",
                }
                for dep_name in deps.keys():
                    dep_lower = dep_name.lower()
                    if dep_lower in js_framework_map:
                        frameworks.add(js_framework_map[dep_lower])
            except Exception:
                pass

        return sorted(list(frameworks))

