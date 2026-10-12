import hashlib
from typing import Dict, Optional
from pathlib import Path

from .providers.base import ParsedFile, LanguageProvider
from .providers.python import PythonProvider
from .providers.typescript import TypeScriptProvider, JavaScriptProvider
from .providers.java import JavaProvider
from ..scanner.manifest import RepositoryManifest

class ASTParserManager:
    """
    Manages parsing of files and caches parsed ASTs to avoid redundant work.
    """
    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir).resolve()
        
        self.providers: Dict[str, LanguageProvider] = {
            "Python": PythonProvider(),
            "TypeScript": TypeScriptProvider(),
            "JavaScript": JavaScriptProvider(),
            "Java": JavaProvider(),
        }
        
        # Cache keyed by relative file path
        self._cache: Dict[str, ParsedFile] = {}

    def get_provider(self, language: str) -> Optional[LanguageProvider]:
        return self.providers.get(language)

    def parse_file(self, rel_path: str, language: str) -> Optional[ParsedFile]:
        if rel_path in self._cache:
            return self._cache[rel_path]
            
        provider = self.get_provider(language)
        if not provider:
            return None
            
        full_path = self.target_dir / rel_path
        if not full_path.exists():
            return None
            
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                raw_source = f.read()
        except Exception:
            return None

        from backend.intelligence.notebook import resolve_source_document
        doc = resolve_source_document(rel_path, raw_source)
        if doc.conversion_error:
            # Notebook conversion failed; do not attempt fake Python parsing
            return None

        parsed_file = provider.parse(rel_path, doc.source)
        self._cache[rel_path] = parsed_file
        return parsed_file
        
    def parse_manifest(self, manifest: RepositoryManifest) -> Dict[str, ParsedFile]:
        results = {}
        for f in manifest.files:
            if f.language in self.providers:
                parsed = self.parse_file(f.path, f.language)
                if parsed:
                    results[f.path] = parsed
        return results
