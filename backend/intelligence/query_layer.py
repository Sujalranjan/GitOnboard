from typing import List, Dict, Optional, Any, Tuple
from .rim.repository import RepositoryModel
from .rim.entity import Entity
from .rim.enums import EntityType

class QueryLayer:
    """
    Unified bidirectional interface for accessing the RepositoryModel.

    Supports both forward and reverse queries on relationships:
    - Forward: what does X call/import/depend-on
    - Reverse: what calls/imports/depends-on X
    """

    def __init__(self, model: RepositoryModel):
        self.model = model
        self._build_indexes()

    def _build_indexes(self):
        # Entity Name -> List of Entity IDs
        self._func_name_idx: Dict[str, List[str]] = {}
        self._class_name_idx: Dict[str, List[str]] = {}

        # Structural indexes
        self._file_to_classes_idx: Dict[str, List[str]] = {}
        self._module_to_functions_idx: Dict[str, List[str]] = {}

        # Relationship reverse indexes for fast lookups
        self._reverse_relationships: Dict[Tuple[str, str], List[str]] = {}
        # Key: (rel_type, target_id), Value: List of source_ids

        for eid, entity in self.model.entities.items():
            if entity.type == EntityType.FUNCTION:
                self._func_name_idx.setdefault(entity.name, []).append(eid)
                module_id = entity.metadata.get("module_id", entity.location.repository_path)
                self._module_to_functions_idx.setdefault(module_id, []).append(eid)
            elif entity.type == EntityType.CLASS:
                self._class_name_idx.setdefault(entity.name, []).append(eid)
                file_id = entity.metadata.get("file_id", entity.location.repository_path)
                self._file_to_classes_idx.setdefault(file_id, []).append(eid)

        # Build reverse relationship index
        for rel_id, rel in self.model.relationships.items():
            key = (rel.type, rel.target_id)
            self._reverse_relationships.setdefault(key, []).append(rel.source_id)

    def find_function(self, name: str) -> List[Entity]:
        ids = self._func_name_idx.get(name, [])
        return [self.model.entities[eid] for eid in ids if eid in self.model.entities]

    def get_class(self, name: str) -> List[Entity]:
        ids = self._class_name_idx.get(name, [])
        return [self.model.entities[eid] for eid in ids if eid in self.model.entities]

    def get_file(self, file_id: str) -> Optional[Entity]:
        return self.model.entities.get(file_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Forward Query Methods
    # ──────────────────────────────────────────────────────────────────────────

    def get_dependencies(self, file_id: str) -> List[str]:
        """What files does this file depend on? (Forward DEPENDS_ON)"""
        return [r.target_id for r in self.model.relationships.values()
                if r.type == "DEPENDS_ON" and r.source_id == file_id]

    def get_calls(self, function_id: str) -> List[str]:
        """What functions does this function call? (Forward CALLS)"""
        return [r.target_id for r in self.model.relationships.values()
                if r.type == "CALLS" and r.source_id == function_id]

    def get_imports(self, entity_id: str) -> List[str]:
        """What does this entity import? (Forward IMPORTS)"""
        return [r.target_id for r in self.model.relationships.values()
                if r.type == "IMPORTS" and r.source_id == entity_id]

    def get_uses(self, entity_id: str) -> List[str]:
        """What does this entity use? (Forward USES)"""
        return [r.target_id for r in self.model.relationships.values()
                if r.type == "USES" and r.source_id == entity_id]

    def get_inherits(self, class_id: str) -> List[str]:
        """What does this class inherit from? (Forward INHERITS)"""
        return [r.target_id for r in self.model.relationships.values()
                if r.type == "INHERITS" and r.source_id == class_id]

    def get_implements(self, class_id: str) -> List[str]:
        """What interfaces/contracts does this class implement? (Forward IMPLEMENTS)"""
        return [r.target_id for r in self.model.relationships.values()
                if r.type == "IMPLEMENTS" and r.source_id == class_id]

    # ──────────────────────────────────────────────────────────────────────────
    # Reverse Query Methods (Bidirectional)
    # ──────────────────────────────────────────────────────────────────────────

    def get_called_by(self, function_id: str) -> List[str]:
        """What functions call this function? (Reverse CALLS)"""
        return [r.source_id for r in self.model.relationships.values()
                if r.type == "CALLS" and r.target_id == function_id]

    def get_callers(self, function_id: str) -> List[str]:
        """Alias for get_called_by. What functions call this function?"""
        return self.get_called_by(function_id)

    def get_depended_by(self, file_id: str) -> List[str]:
        """What files depend on this file? (Reverse DEPENDS_ON)"""
        return [r.source_id for r in self.model.relationships.values()
                if r.type == "DEPENDS_ON" and r.target_id == file_id]

    def get_dependent_files(self, file_id: str) -> List[str]:
        """Alias for get_depended_by. What files depend on this file?"""
        return self.get_depended_by(file_id)

    def get_imported_by(self, entity_id: str) -> List[str]:
        """What entities import this entity? (Reverse IMPORTS)"""
        return [r.source_id for r in self.model.relationships.values()
                if r.type == "IMPORTS" and r.target_id == entity_id]

    def get_importers(self, entity_id: str) -> List[str]:
        """Alias for get_imported_by. What entities import this entity?"""
        return self.get_imported_by(entity_id)

    def get_used_by(self, entity_id: str) -> List[str]:
        """What entities use this entity? (Reverse USES)"""
        return [r.source_id for r in self.model.relationships.values()
                if r.type == "USES" and r.target_id == entity_id]

    def get_users(self, entity_id: str) -> List[str]:
        """Alias for get_used_by. What entities use this entity?"""
        return self.get_used_by(entity_id)

    def get_extended_by(self, class_id: str) -> List[str]:
        """What classes extend this class? (Reverse INHERITS)"""
        return [r.source_id for r in self.model.relationships.values()
                if r.type == "INHERITS" and r.target_id == class_id]

    def get_subclasses(self, class_id: str) -> List[str]:
        """Alias for get_extended_by. What classes extend this class?"""
        return self.get_extended_by(class_id)

    def get_implementers(self, interface_id: str) -> List[str]:
        """What classes implement this interface? (Reverse IMPLEMENTS)"""
        return [r.source_id for r in self.model.relationships.values()
                if r.type == "IMPLEMENTS" and r.target_id == interface_id]

    def get_implementations(self, interface_id: str) -> List[str]:
        """Alias for get_implementers. What classes implement this interface?"""
        return self.get_implementers(interface_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Relationship Query Methods (Bidirectional, Direct + Metadata)
    # ──────────────────────────────────────────────────────────────────────────

    def get_forward_relationships(self, entity_id: str, rel_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all forward relationships from an entity.

        Args:
            entity_id: Source entity ID
            rel_type: Optional filter by relationship type

        Returns:
            List of relationship dictionaries with type and target
        """
        results = []
        for rel in self.model.relationships.values():
            if rel.source_id == entity_id:
                if rel_type is None or rel.type == rel_type:
                    results.append({
                        "type": rel.type,
                        "target_id": rel.target_id,
                        "metadata": rel.metadata,
                    })
        return results

    def get_reverse_relationships(self, entity_id: str, rel_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all reverse relationships to an entity.

        Args:
            entity_id: Target entity ID
            rel_type: Optional filter by relationship type

        Returns:
            List of relationship dictionaries with type and source
        """
        results = []
        for rel in self.model.relationships.values():
            if rel.target_id == entity_id:
                if rel_type is None or rel.type == rel_type:
                    results.append({
                        "type": rel.type,
                        "source_id": rel.source_id,
                        "metadata": rel.metadata,
                    })
        return results

    # ──────────────────────────────────────────────────────────────────────────
    # Structural Query Methods
    # ──────────────────────────────────────────────────────────────────────────

    def get_classes_in_file(self, file_id: str) -> List[Entity]:
        ids = self._file_to_classes_idx.get(file_id, [])
        return [self.model.entities[eid] for eid in ids if eid in self.model.entities]

    def get_functions_in_module(self, module_id: str) -> List[Entity]:
        ids = self._module_to_functions_idx.get(module_id, [])
        return [self.model.entities[eid] for eid in ids if eid in self.model.entities]

    def get_directories(self) -> List[Entity]:
        return [e for e in self.model.entities.values() if e.type == EntityType.DIRECTORY]

    def get_files(self) -> List[Entity]:
        return [e for e in self.model.entities.values() if e.type == EntityType.FILE]

    # ──────────────────────────────────────────────────────────────────────────
    # Search Methods
    # ──────────────────────────────────────────────────────────────────────────

    def search_entities(self, query: str) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        results = []
        for fn_name, fn_ids in self._func_name_idx.items():
            if query_lower in fn_name.lower():
                for eid in fn_ids:
                    fn = self.model.entities[eid]
                    results.append({"type": "function", "name": fn.name, "id": eid, "file": fn.location.repository_path})

        for cls_name, cls_ids in self._class_name_idx.items():
            if query_lower in cls_name.lower():
                for eid in cls_ids:
                    cls = self.model.entities[eid]
                    results.append({"type": "class", "name": cls.name, "id": eid, "file": cls.location.repository_path})

        return results
