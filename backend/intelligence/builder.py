import os
import ast
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .repository_model import (
    RepositoryModel, RepositoryMetadata, RepositoryEntities,
    FileNode, DirectoryNode, ModuleNode, ClassNode, FunctionNode,
    MethodNode, VariableNode, ImportNode
)
from .parser import LanguageParser

def generate_fingerprint(target_dir: Path) -> str:
    # A simple fingerprint using modified time of the top directory or just a static one for MVP
    # In a real scenario, this could be a hash of all file mtimes or commit hash.
    try:
        return str(target_dir.stat().st_mtime)
    except Exception:
        return str(uuid.uuid4())

class RepositoryBuilder:
    """Pure entity ingestion layer. Scans directory and parses AST exactly once."""

    # Only analyze code files
    CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx"}

    def __init__(self, repo_name: str, target_dir: Path):
        self.repo_name = repo_name
        self.target_dir = target_dir
        # Ignore common build/cache/version-control directories
        # Skip only system directories; store everything else including dot-folders
        self.ignored_dirs = {
            ".git", "node_modules", "venv", ".venv",
            "build", "dist", "out", "target",
            "__pycache__", ".pytest_cache", ".tox", ".mypy_cache",
            "coverage", ".coverage"
        }
        self.parser = LanguageParser()

    def build(self) -> RepositoryModel:
        metadata = RepositoryMetadata(
            repository_name=self.repo_name,
            repository_path=str(self.target_dir),
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
            repository_fingerprint=generate_fingerprint(self.target_dir)
        )
        
        entities = RepositoryEntities()
        
        for root, dirs, files in os.walk(self.target_dir):
            # Skip ignored directories only (not dot-folders — we store those to Azure)
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]

            rel_root = str(Path(root).relative_to(self.target_dir)).replace("\\", "/")
            if rel_root != ".":
                dir_id = rel_root
                entities.directories[dir_id] = DirectoryNode(
                    id=dir_id,
                    path=rel_root,
                    name=Path(root).name
                )

            for file in files:
                # Store ALL files to Azure, but only INDEX code files
                pf = Path(root) / file
                ext = pf.suffix.lower()
                rel_path = str(pf.relative_to(self.target_dir)).replace("\\", "/")
                file_id = rel_path

                try:
                    size = pf.stat().st_size
                except Exception:
                    size = 0

                # Only INDEX code files (skip hidden files, non-code files, and dot-folders)
                is_code_file = not file.startswith(".") and ext in self.CODE_EXTENSIONS
                is_in_dot_folder = any(part.startswith(".") for part in Path(rel_path).parts)
                should_index = is_code_file and not is_in_dot_folder
                is_python = ext == ".py"

                entities.files[file_id] = FileNode(
                    id=file_id,
                    path=rel_path,
                    name=file,
                    extension=ext,
                    size=size,
                    is_python=is_python
                )

                # Parse code files for symbols (only if not in dot-folder)
                if should_index and self.parser.supports_extension(ext):
                    self._parse_file(pf, file_id, ext, entities)
                    
        return RepositoryModel(metadata=metadata, entities=entities)

    def _parse_file(self, pf: Path, file_id: str, ext: str, entities: RepositoryEntities):
        # Determine module id
        parts = list(pf.relative_to(self.target_dir).parts)
        if ext == ".py":
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1][:-3]
        else:
            parts[-1] = parts[-1].rsplit(".", 1)[0]
            
        module_name = ".".join(parts) if parts else ""
        module_id = module_name
        
        if module_id and module_id not in entities.modules:
            entities.modules[module_id] = ModuleNode(
                id=module_id,
                name=module_name,
                file_id=file_id
            )
            
        try:
            with open(pf, "r", encoding="utf-8") as f:
                source = f.read()
            tree, _ = self.parser.parse_source(source, ext)
            parsed_entities = self.parser.extract_entities(tree, source, file_id, module_id)
            
            for imp in parsed_entities["imports"]:
                imp_id = f"{file_id}::import::{imp['module_name']}"
                entities.imports[imp_id] = ImportNode(
                    id=imp_id, file_id=file_id,
                    module_name=imp["module_name"], alias=imp["alias"]
                )
            for cls in parsed_entities["classes"]:
                entities.classes[cls["id"]] = ClassNode(
                    id=cls["id"], name=cls["name"], file_id=file_id,
                    module_id=module_id, line_number=cls["line_number"], docstring=cls["docstring"]
                )
            for fn in parsed_entities["functions"]:
                entities.functions[fn["id"]] = FunctionNode(
                    id=fn["id"], name=fn["name"], file_id=file_id, module_id=module_id,
                    line_number=fn["line_number"], docstring=fn["docstring"], parameters=fn["parameters"], is_async=fn["is_async"]
                )
            for md in parsed_entities["methods"]:
                entities.methods[md["id"]] = MethodNode(
                    id=md["id"], name=md["name"], class_id=md["class_id"], file_id=file_id,
                    module_id=module_id, line_number=md["line_number"], docstring=md["docstring"], parameters=md["parameters"], is_async=md["is_async"]
                )
            for vr in parsed_entities["variables"]:
                entities.variables[vr["id"]] = VariableNode(
                    id=vr["id"], name=vr["name"], file_id=file_id, line_number=vr["line_number"]
                )
        except Exception as e:
            print(f"Error parsing file {pf}: {e}")
