"""
USES and REFERENCES Analyzer: extract property access, type usage, and references.

USES: Data flow / property access (e.g., obj.method, obj.property)
REFERENCES: Type references and imports (e.g., type annotations, implements)
"""
import ast
from typing import Dict, List, Optional, Set
from .base import BaseAnalyzer
from .resolution import SymbolIndex, resolve_reference
from ..parser.providers.base import ParsedFile
from ...rim.repository import RepositoryModel
from ...rim.relationship import Relationship
from ...rim.enums import EntityType, RelationshipType
from ...rim.identity import generate_entity_id, generate_relationship_id


class PythonUsesVisitor(ast.NodeVisitor):
    """Extract USES relationships from Python AST (property access, type hints)."""

    def __init__(self, file_path: str, repository: RepositoryModel, symbol_index: SymbolIndex):
        self.file_path = file_path
        self.repository = repository
        self.index = symbol_index
        self.relationships: List[Relationship] = []
        self.current_caller_id: Optional[str] = None
        self.namespace_stack: List[tuple] = []

    def _get_qualified_name(self, name: str) -> str:
        parts = []
        module_path = self.file_path.replace("/", ".").replace(".py", "")
        if module_path.endswith(".__init__"):
            module_path = module_path[:-9]
        if module_path:
            parts.append(module_path)
        parts.extend(ns_name for ns_name, _ in self.namespace_stack)
        if name:
            parts.append(name)
        return ".".join(parts)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        entity_type = EntityType.METHOD if self.namespace_stack else EntityType.FUNCTION
        qname = self._get_qualified_name(node.name)
        func_id = generate_entity_id(entity_type, self.file_path, qname)

        # Check return type annotation
        if node.returns:
            self._extract_type_reference(node.returns, func_id)

        # Check argument type annotations
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            if arg.annotation:
                self._extract_type_reference(arg.annotation, func_id)

        prev_caller = self.current_caller_id
        self.current_caller_id = func_id
        self.namespace_stack.append((node.name, entity_type))

        self.generic_visit(node)

        self.namespace_stack.pop()
        self.current_caller_id = prev_caller

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        qname = self._get_qualified_name(node.name)
        class_id = generate_entity_id(EntityType.CLASS, self.file_path, qname)

        # Check type annotations in class variables
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and item.annotation:
                self._extract_type_reference(item.annotation, class_id)

        self.namespace_stack.append((node.name, EntityType.CLASS))
        self.generic_visit(node)
        self.namespace_stack.pop()

    def visit_Attribute(self, node: ast.Attribute):
        """Extract USES from property access: obj.property"""
        if self.current_caller_id:
            attr_name = node.attr
            # Try to resolve the attribute
            target_id = resolve_reference(self.repository, self.file_path, attr_name, self.current_caller_id, self.index)
            if target_id:
                rel = Relationship(
                    id=generate_relationship_id(RelationshipType.USES, self.current_caller_id, target_id),
                    type=RelationshipType.USES,
                    source_id=self.current_caller_id,
                    target_id=target_id,
                    metadata={"property": attr_name}
                )
                self.relationships.append(rel)

        self.generic_visit(node)

    def _extract_type_reference(self, type_node: ast.AST, source_id: str):
        """Extract type name from annotation and create REFERENCES relationship."""
        type_name = None
        if isinstance(type_node, ast.Name):
            type_name = type_node.id
        elif isinstance(type_node, ast.Subscript) and isinstance(type_node.value, ast.Name):
            type_name = type_node.value.id

        if type_name:
            target_id = resolve_reference(self.repository, self.file_path, type_name, None, self.index)
            if target_id:
                rel = Relationship(
                    id=generate_relationship_id(RelationshipType.REFERENCES, source_id, target_id),
                    type=RelationshipType.REFERENCES,
                    source_id=source_id,
                    target_id=target_id,
                    metadata={"type_name": type_name}
                )
                self.relationships.append(rel)


class TypeScriptUsesVisitor:
    """Extract USES/REFERENCES from tree-sitter AST (TS/JS)."""

    def __init__(self, file_path: str, source: str, repository: RepositoryModel, symbol_index: SymbolIndex):
        self.file_path = file_path
        self.source = source
        self.source_bytes = source.encode('utf-8')
        self.repository = repository
        self.index = symbol_index
        self.relationships: List[Relationship] = []
        self.current_caller_id: Optional[str] = None

    def _get_text(self, node) -> str:
        if not node:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

    def visit(self, node):
        """Traverse the AST and extract type/property relationships."""
        if node.type == 'class_declaration':
            self._handle_class_declaration(node)
        elif node.type == 'function_declaration':
            self._handle_function_declaration(node)
        elif node.type == 'lexical_declaration':
            self._handle_lexical_declaration(node)
        elif node.type == 'type_annotation' and self.current_caller_id:
            self._extract_type_reference(node)
        elif node.type == 'member_expression' and self.current_caller_id:
            self._handle_member_expression(node)

        # Recurse
        for child in node.children:
            self.visit(child)

    def _handle_class_declaration(self, node):
        """Extract type annotations in class."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return

        class_name = self._get_text(name_node)
        module_path = self.file_path.rsplit(".", 1)[0].replace("/", ".")
        qname = f"{module_path}.{class_name}"
        class_id = generate_entity_id(EntityType.CLASS, self.file_path, qname)

        # Traverse class body for type annotations
        class_body = node.child_by_field_name('body')
        if class_body:
            prev_caller = self.current_caller_id
            self.current_caller_id = class_id
            for child in class_body.children:
                self.visit(child)
            self.current_caller_id = prev_caller
        else:
            for child in node.children:
                self.visit(child)

    def _handle_function_declaration(self, node):
        """Extract type annotations in function."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return

        func_name = self._get_text(name_node)
        module_path = self.file_path.rsplit(".", 1)[0].replace("/", ".")
        qname = f"{module_path}.{func_name}"
        func_id = generate_entity_id(EntityType.FUNCTION, self.file_path, qname)

        prev_caller = self.current_caller_id
        self.current_caller_id = func_id

        for child in node.children:
            self.visit(child)

        self.current_caller_id = prev_caller

    def _handle_lexical_declaration(self, node):
        """Extract type annotations in variable declarations."""
        for child in node.children:
            if child.type == 'variable_declarator':
                name_node = child.child_by_field_name('name')
                value_node = child.child_by_field_name('value')

                if name_node and value_node and value_node.type in ('arrow_function', 'function'):
                    func_name = self._get_text(name_node)
                    module_path = self.file_path.rsplit(".", 1)[0].replace("/", ".")
                    qname = f"{module_path}.{func_name}"
                    func_id = generate_entity_id(EntityType.FUNCTION, self.file_path, qname)

                    prev_caller = self.current_caller_id
                    self.current_caller_id = func_id
                    self.visit(child)
                    self.current_caller_id = prev_caller
                else:
                    self.visit(child)
            else:
                self.visit(child)

    def _handle_member_expression(self, node):
        """Extract USES from member access: obj.property."""
        if not self.current_caller_id:
            return

        # Get property name (rightmost part)
        property_node = node.child_by_field_name('property')
        if property_node:
            prop_name = self._get_text(property_node).strip()
            target_id = resolve_reference(self.repository, self.file_path, prop_name, self.current_caller_id, self.index)
            if target_id:
                rel = Relationship(
                    id=generate_relationship_id(RelationshipType.USES, self.current_caller_id, target_id),
                    type=RelationshipType.USES,
                    source_id=self.current_caller_id,
                    target_id=target_id,
                    metadata={"property": prop_name}
                )
                self.relationships.append(rel)

    def _extract_type_reference(self, node):
        """Extract type name from type annotation."""
        # Get the type being referenced
        type_text = self._get_text(node).strip()
        # Remove the ":" prefix and any whitespace
        if type_text.startswith(":"):
            type_text = type_text[1:].strip()

        # Extract base type name (handle generics like Type<T>)
        if "<" in type_text:
            type_text = type_text.split("<")[0]

        type_name = type_text.split()[0] if type_text else None

        if type_name and self.current_caller_id:
            target_id = resolve_reference(self.repository, self.file_path, type_name, None, self.index)
            if target_id:
                rel = Relationship(
                    id=generate_relationship_id(RelationshipType.REFERENCES, self.current_caller_id, target_id),
                    type=RelationshipType.REFERENCES,
                    source_id=self.current_caller_id,
                    target_id=target_id,
                    metadata={"type_name": type_name}
                )
                self.relationships.append(rel)


class UsesAnalyzer(BaseAnalyzer):
    """Extract USES (property access) and REFERENCES (type usage) relationships."""

    name = "UsesAnalyzer"
    supported_languages = ["Python", "TypeScript", "JavaScript"]

    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        index = SymbolIndex(repository)

        for file_path, parsed in asts.items():
            if parsed.language not in self.supported_languages or not parsed.ast:
                continue

            if parsed.language == "Python":
                visitor = PythonUsesVisitor(file_path, repository, index)
                visitor.visit(parsed.ast)
                for rel in visitor.relationships:
                    repository.relationships[rel.id] = rel

            elif parsed.language in ("TypeScript", "JavaScript"):
                visitor = TypeScriptUsesVisitor(file_path, parsed.source, repository, index)
                visitor.visit(parsed.ast.root_node)
                for rel in visitor.relationships:
                    repository.relationships[rel.id] = rel
