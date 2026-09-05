"""
Symbol resolution utilities for cross-file analysis.

Provides canonical entity lookups for resolving imports, references, and calls
across files and modules. Builds indexes to enable quick mapping from local names
to canonical entity IDs.
"""
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from ...rim.repository import RepositoryModel
from ...rim.enums import EntityType, RelationshipType


class SymbolIndex:
    """Build and query indices for fast symbol resolution."""

    def __init__(self, repository: RepositoryModel):
        self.repo = repository
        self.symbols_by_name: Dict[str, List[str]] = {}  # name → [entity_ids]
        self.symbols_by_file: Dict[str, List[str]] = {}  # file_path → [entity_ids]
        self.file_by_path: Dict[str, str] = {}  # file_path → entity_id
        self.modules_by_name: Dict[str, str] = {}  # "module.name" → entity_id
        self.build()

    def build(self):
        """Scan repository entities and build lookup indices."""
        for entity_id, entity in self.repo.entities.items():
            if entity.type == EntityType.FILE:
                path = entity.qualified_name
                self.file_by_path[path] = entity_id
                self.symbols_by_file[path] = []
            elif entity.type == EntityType.MODULE:
                name = entity.qualified_name
                self.modules_by_name[name] = entity_id

        for entity_id, entity in self.repo.entities.items():
            if entity.type not in (EntityType.FILE, EntityType.MODULE, EntityType.DIRECTORY):
                # Add to file index
                file_path = entity.metadata.get("file_id")
                if file_path and file_path in self.symbols_by_file:
                    self.symbols_by_file[file_path].append(entity_id)

                # Add to name index
                if entity.name not in self.symbols_by_name:
                    self.symbols_by_name[entity.name] = []
                self.symbols_by_name[entity.name].append(entity_id)

    def lookup_symbol(self, file_path: str, name: str) -> Optional[str]:
        """Look up a symbol by name in the context of a file.

        First tries local scope (in the same file), then file scope, then global.
        """
        if name in self.symbols_by_name:
            candidates = self.symbols_by_name[name]
            # Prefer symbols from the same file
            for entity_id in candidates:
                entity = self.repo.entities.get(entity_id)
                if entity and entity.metadata.get("file_id") == file_path:
                    return entity_id
            # Fall back to any matching symbol
            if candidates:
                return candidates[0]
        return None

    def lookup_module(self, module_path: str) -> Optional[str]:
        """Look up a module by path or name."""
        # Try exact match first
        if module_path in self.modules_by_name:
            return self.modules_by_name[module_path]

        # Try file path
        if module_path in self.file_by_path:
            return self.file_by_path[module_path]

        # Try common variations
        for variation in [
            module_path.replace(".js", "").replace(".ts", "").replace(".tsx", ""),
            module_path.replace("/", "."),
            module_path.replace(".", "/"),
        ]:
            if variation in self.modules_by_name:
                return self.modules_by_name[variation]
            if variation in self.file_by_path:
                return self.file_by_path[variation]

        return None


def resolve_import_target(
    repository: RepositoryModel,
    importer_path: str,
    module_spec: str,
    index: Optional[SymbolIndex] = None
) -> Optional[str]:
    """Resolve an import statement to a target entity.

    Args:
        repository: The RIM repository
        importer_path: File path doing the importing
        module_spec: Module being imported (e.g., "./auth", "react", "lodash")
        index: Optional pre-built SymbolIndex for performance

    Returns:
        Entity ID of the target file/module, or None if unresolvable
    """
    if not index:
        index = SymbolIndex(repository)

    # Handle relative imports
    if module_spec.startswith("."):
        base_dir = str(Path(importer_path).parent)
        if module_spec.startswith("./"):
            target_path = str(Path(base_dir) / module_spec[2:])
        elif module_spec.startswith("../"):
            target_path = str(Path(base_dir).parent / module_spec[3:])
        else:
            return None

        # Try with common extensions
        for ext in [".ts", ".tsx", ".js", ".jsx", ".py"]:
            candidate = target_path if target_path.endswith(ext) else target_path + ext
            if candidate in index.file_by_path:
                return index.file_by_path[candidate]

        # Try index files
        for ext in [".ts", ".tsx", ".js", ".jsx", ".py"]:
            candidate = target_path + f"/index{ext}" if not target_path.endswith(ext) else None
            if candidate and candidate in index.file_by_path:
                return index.file_by_path[candidate]
    else:
        # Handle absolute/package imports
        return index.lookup_module(module_spec)

    return None


def resolve_reference(
    repository: RepositoryModel,
    file_path: str,
    name: str,
    local_scope: Optional[str] = None,
    index: Optional[SymbolIndex] = None
) -> Optional[str]:
    """Resolve a reference to a symbol in the source code.

    Implements multi-strategy fallback:
    1. Local scope (if provided)
    2. File scope (symbols declared in same file)
    3. Imported modules (check IMPORTS relationships)
    4. Global scope (any matching symbol)

    Args:
        repository: The RIM repository
        file_path: File containing the reference
        name: Symbol name being referenced
        local_scope: Optional entity ID of local scope (function, class)
        index: Optional pre-built SymbolIndex for performance

    Returns:
        Entity ID of the resolved symbol, or None
    """
    if not index:
        index = SymbolIndex(repository)

    # Strategy 1: Local scope (if we're inside a function/class)
    if local_scope:
        entity = repository.entities.get(local_scope)
        if entity:
            # Check if it's a parameter or local variable (would need more info)
            pass

    # Strategy 2: File scope
    file_id = index.file_by_path.get(file_path)
    if file_id:
        for entity_id in index.symbols_by_file.get(file_path, []):
            entity = repository.entities.get(entity_id)
            if entity and entity.name == name:
                return entity_id

    # Strategy 3: Check imports
    file_id = index.file_by_path.get(file_path)
    if file_id:
        for rel_id, rel in repository.relationships.items():
            if rel.source_id == file_id and rel.type == RelationshipType.IMPORTS:
                # This file imports module X. Check if X exports the symbol
                module_id = rel.target_id
                module = repository.entities.get(module_id)
                if module:
                    # Look for exports from this module
                    for cand_id, cand in repository.entities.items():
                        if (cand.name == name and
                            cand.metadata.get("file_id") == module.qualified_name):
                            return cand_id

    # Strategy 4: Global scope
    for entity_id in index.symbols_by_name.get(name, []):
        return entity_id

    return None
