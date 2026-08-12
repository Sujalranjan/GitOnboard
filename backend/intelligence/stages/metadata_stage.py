import logging
from pathlib import Path
from typing import Dict, Any, List

from ..repository_model import RepositoryModel
from ..query_layer import QueryLayer

logger = logging.getLogger(__name__)

KNOWN_FRAMEWORKS = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "sqlalchemy": "SQLAlchemy",
    "react": "React",
    "next": "Next.js",
    "express": "Express",
    "celery": "Celery",
    "redis": "Redis",
    "tensorflow": "TensorFlow",
    "torch": "PyTorch",
    "pydantic": "Pydantic"
}

ENTRYPOINT_PATTERNS = ["main.py", "app.py", "server.py", "manage.py", "run.py", "index.js", "index.ts"]

class RepositoryMetadataStage:
    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir)

    def run(self, model: RepositoryModel) -> None:
        query_layer = QueryLayer(model)
        
        # 1. README Extraction
        readme_summary = self._extract_readme()
        
        # 2. Framework Detection
        frameworks = self._detect_frameworks(model)
        scanner_frameworks = model.metadata.metadata.get("frameworks", [])
        merged_frameworks = sorted(list(set(frameworks + scanner_frameworks)))
        
        # 3. Project Type Detection
        project_type = self._detect_project_type(merged_frameworks, model)
        
        # 4. Language Profiling
        languages = self._profile_languages(model)
        primary_language = model.metadata.metadata.get("primary_language", "Unknown")
        
        # 5. Entrypoint Detection
        entrypoints = self._detect_entrypoints(model)
        
        # 6. Architecture Summary
        architecture = self._summarize_architecture(model)
        
        # 7. Module Enrichment
        modules = self._enrich_top_modules(model, query_layer)
        
        model.analyses.enriched_metadata = {
            "schema_version": 2,
            "repository": {
                "name": model.metadata.repository_name,
                "languages": languages,
                "primary_language": primary_language,
                "frameworks": merged_frameworks,
                "project_type": project_type,
                "commit": model.metadata.commit,
                "branch": model.metadata.branch
            },
            "entrypoints": entrypoints,
            "architecture": architecture,
            "modules": modules,
            "statistics": {
                "files": len(model.entities.files),
                "python_files": sum(1 for f in model.entities.files.values() if f.is_python),
                "directories": len(model.entities.directories)
            },
            "readme_summary": readme_summary
        }
        
        model.analysis_status.enriched_metadata = True

    def _extract_readme(self) -> str | None:
        try:
            readme_path = self.target_dir / "README.md"
            if not readme_path.exists():
                return None
                
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Extract title (first line usually) and first non-empty paragraph
            lines = [line.strip() for line in content.split("\n") if line.strip()]
            if not lines:
                return None
                
            extracted = []
            features_section = []
            in_features = False
            
            for line in lines:
                if len(extracted) < 2 and not in_features:
                    # Capture title and first paragraph
                    if not line.startswith("[!"): # Skip badges
                        extracted.append(line)
                elif "features" in line.lower() and line.startswith("#"):
                    in_features = True
                    features_section.append(line)
                elif in_features:
                    if line.startswith("#"):
                        break # End of features section
                    if len(features_section) < 10: # Cap features list
                        features_section.append(line)
            
            summary = "\n\n".join(extracted)
            if features_section:
                summary += "\n\n" + "\n".join(features_section)
                
            # Truncate to avoid blowing up tokens
            if len(summary) > 1500:
                summary = summary[:1500] + "..."
                
            return summary
        except Exception as e:
            logger.warning(f"Failed to parse README: {e}")
            return None

    def _detect_frameworks(self, model: RepositoryModel) -> List[str]:
        detected = set()
        for imp in model.entities.imports.values():
            base_module = imp.module_name.split(".")[0].lower()
            if base_module in KNOWN_FRAMEWORKS:
                detected.add(KNOWN_FRAMEWORKS[base_module])
        return sorted(list(detected))

    def _detect_project_type(self, frameworks: List[str], model: RepositoryModel) -> Dict[str, Any]:
        has_fastapi = "FastAPI" in frameworks
        has_django = "Django" in frameworks
        has_react = "React" in frameworks or "Next.js" in frameworks
        
        # Simple heuristics for confidence
        if has_fastapi and not has_react:
            return {"type": "FastAPI Backend", "confidence": 0.85}
        if has_django and not has_react:
            return {"type": "Django Backend", "confidence": 0.85}
        if has_react and not has_fastapi and not has_django:
            return {"type": "React Frontend", "confidence": 0.85}
        if has_fastapi and has_react:
            return {"type": "Fullstack Application (FastAPI/React)", "confidence": 0.90}
            
        python_count = sum(1 for f in model.entities.files.values() if f.is_python)
        if python_count > 0 and not frameworks:
            return {"type": "Python Library/Script", "confidence": 0.6}
            
        return {"type": "Unknown", "confidence": 0.1}

    def _profile_languages(self, model: RepositoryModel) -> Dict[str, int]:
        ext_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".java": "Java",
            ".c": "C",
            ".cpp": "C++",
            ".cs": "C#",
            ".go": "Go",
            ".rs": "Rust",
            ".rb": "Ruby",
            ".php": "PHP",
            ".swift": "Swift",
            ".kt": "Kotlin",
            ".html": "HTML",
            ".css": "CSS"
        }
        
        counts = {}
        for f in model.entities.files.values():
            lang = ext_map.get(f.extension.lower())
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
        
        # Sort by count desc
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5])

    def _detect_entrypoints(self, model: RepositoryModel) -> List[str]:
        entrypoints = []
        for f in model.entities.files.values():
            if f.name.lower() in ENTRYPOINT_PATTERNS:
                entrypoints.append(f.path)
        return entrypoints

    def _summarize_architecture(self, model: RepositoryModel) -> Dict[str, Any]:
        # Build deterministic generic layered architecture
        layers = set()
        
        for d in model.entities.directories.values():
            name = d.name.lower()
            if name in ["api", "controllers", "routes"]:
                layers.add("api")
            elif name in ["services", "core", "business"]:
                layers.add("services")
            elif name in ["models", "database", "repositories", "db", "orm"]:
                layers.add("database")
            elif name in ["components", "pages", "hooks", "views"]:
                layers.add("ui")
        
        ordered_layers = []
        if "ui" in layers: ordered_layers.append("ui")
        if "api" in layers: ordered_layers.append("api")
        if "services" in layers: ordered_layers.append("services")
        if "database" in layers: ordered_layers.append("database")
        
        if ordered_layers:
            return {
                "style": "component" if "ui" in layers else "layered",
                "components": ordered_layers
            }
        
        return {"style": "unknown", "components": []}

    def _enrich_top_modules(self, model: RepositoryModel, query_layer: QueryLayer) -> List[Dict[str, Any]]:
        if not model.analyses.metrics or "largest_modules" not in model.analyses.metrics:
            return []
            
        largest = model.analyses.metrics["largest_modules"]
        enriched = []
        
        for mod_stat in largest:
            file_id = mod_stat.get("module")
            if not file_id: continue
            
            f_node = query_layer.get_file(file_id)
            if not f_node: continue
            
            # Find exports
            funcs = [fn.name for fn in query_layer.get_functions_in_module(file_id) if not fn.name.startswith("_")]
            classes = [cls.name for cls in query_layer.get_classes_in_file(file_id) if not cls.name.startswith("_")]
            exports = (funcs + classes)[:8] # Cap at 8
            
            # Find purpose
            purpose = "Unknown"
            source = "none"
            
            # Fallback 1: Class docstring (if exists) or function docstrings
            docstrings = [fn.docstring for fn in query_layer.get_functions_in_module(file_id) if fn.docstring]
            class_docs = [cls.docstring for cls in query_layer.get_classes_in_file(file_id) if cls.docstring]
            all_docs = docstrings + class_docs
            if all_docs:
                purpose = all_docs[0].split("\n")[0][:100] + "..." # First line of first docstring
                source = "docstring"
            else:
                # Fallback 2: Filename heuristics
                name = f_node.name.lower()
                if "auth" in name:
                    purpose = "Authentication and authorization"
                    source = "filename"
                elif "db" in name or "model" in name:
                    purpose = "Database schema and ORM models"
                    source = "filename"
                elif "api" in name or "router" in name:
                    purpose = "API routes and endpoints"
                    source = "filename"
                elif "util" in name or "helper" in name:
                    purpose = "Utility functions"
                    source = "filename"
                elif "service" in name:
                    purpose = "Business logic and services"
                    source = "filename"
                elif len(exports) > 0:
                    purpose = f"Provides {exports[0]} and {len(exports)-1} other entities"
                    source = "exports"
            
            enriched.append({
                "name": f_node.name,
                "path": f_node.path,
                "purpose": purpose,
                "purpose_source": source,
                "exports": exports
            })
            
        return enriched
