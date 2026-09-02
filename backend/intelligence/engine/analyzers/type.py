import ast
from typing import Dict, List
from .base import BaseAnalyzer
from ..parser.providers.base import ParsedFile
from ...rim.repository import RepositoryModel
from ...rim.relationship import Relationship
from ...rim.enums import EntityType, RelationshipType
from ...rim.identity import generate_entity_id, generate_relationship_id

class PythonTypeVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.relationships: List[Relationship] = []
        self.namespace_stack: List[str] = []
        self.imported_symbols: Dict[str, tuple[str, str, str]] = {}
        self.imported_modules: Dict[str, str] = {}
        
    def _get_qualified_name(self, name: str) -> str:
        parts = []
        module_path = self.file_path.replace("/", ".").replace(".py", "")
        if module_path.endswith(".__init__"):
            module_path = module_path[:-9]
        if module_path:
            parts.append(module_path)
        parts.extend(self.namespace_stack)
        parts.append(name)
        return ".".join(parts)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imported_modules[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.imported_symbols[alias.asname or alias.name] = (module, alias.name, full_name)
        self.generic_visit(node)

    def _extract_base_name(self, base_node: ast.AST) -> str:
        if isinstance(base_node, ast.Name):
            return base_node.id
        elif isinstance(base_node, ast.Attribute):
            val = self._extract_base_name(base_node.value)
            return f"{val}.{base_node.attr}" if val else base_node.attr
        return ""

    def visit_ClassDef(self, node: ast.ClassDef):
        class_qname = self._get_qualified_name(node.name)
        class_id = generate_entity_id(EntityType.CLASS, self.file_path, class_qname)

        for base in node.bases:
            base_name = self._extract_base_name(base)
            if not base_name:
                continue

            # Skip builtin and external base classes that won't have Entity records
            # (object, Exception, typing module bases, etc.)
            if base_name in ("object", "Exception", "BaseException"):
                continue
            if base_name.startswith("typing.") or base_name in ("ABC", "Generic"):
                continue

            # Only create INHERITS relationship if base is from an imported module
            # Local base classes defined in same file/scope can't be resolved yet
            base_id = None
            if base_name in self.imported_symbols:
                mod, sym_name, full_qname = self.imported_symbols[base_name]
                target_file = mod.replace(".", "/") + ".py"
                base_id = generate_entity_id(EntityType.CLASS, target_file, full_qname)
            elif "." in base_name:
                parts = base_name.split(".", 1)
                if parts[0] in self.imported_modules:
                    mod = self.imported_modules[parts[0]]
                    target_file = mod.replace(".", "/") + ".py"
                    base_id = generate_entity_id(EntityType.CLASS, target_file, f"{mod}.{parts[1]}")

            # Only create relationship if we can identify an imported base class
            if base_id:
                rel = Relationship(
                    id=generate_relationship_id(RelationshipType.INHERITS, class_id, base_id),
                    type=RelationshipType.INHERITS,
                    source_id=class_id,
                    target_id=base_id,
                    metadata={"base": base_name, "line": node.lineno}
                )
                self.relationships.append(rel)
                
        self.namespace_stack.append(node.name)
        self.generic_visit(node)
        self.namespace_stack.pop()

class TypeAnalyzer(BaseAnalyzer):
    name = "TypeAnalyzer"
    supported_languages = ["Python"]

    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        for file_path, parsed in asts.items():
            if parsed.language not in self.supported_languages or not parsed.ast:
                continue
                
            visitor = PythonTypeVisitor(file_path)
            visitor.visit(parsed.ast)
            
            for rel in visitor.relationships:
                repository.relationships[rel.id] = rel
