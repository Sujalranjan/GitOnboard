"""
CallGraph Analyzer: extracts CALLS, EXTENDS, IMPLEMENTS relationships.

Supports Python (ast-based) and TypeScript/JavaScript (tree-sitter).
Uses symbol resolution to handle cross-file references.
"""
import ast
from typing import Dict, List, Optional
from .base import BaseAnalyzer
from .resolution import SymbolIndex, resolve_reference, resolve_import_target
from ..parser.providers.base import ParsedFile
from ...rim.repository import RepositoryModel
from ...rim.relationship import Relationship
from ...rim.enums import EntityType, RelationshipType
from ...rim.identity import generate_entity_id, generate_relationship_id


class PythonCallGraphVisitor(ast.NodeVisitor):
    """Extract calls and class relationships from Python AST."""

    def __init__(self, file_path: str, repository: RepositoryModel, symbol_index: SymbolIndex):
        self.file_path = file_path
        self.repository = repository
        self.index = symbol_index
        self.relationships: List[Relationship] = []
        self.current_caller_id: Optional[str] = None
        self.namespace_stack: List[tuple] = []  # (name, entity_type)

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

    def visit_ClassDef(self, node: ast.ClassDef):
        qname = self._get_qualified_name(node.name)
        class_id = generate_entity_id(EntityType.CLASS, self.file_path, qname)

        # Extract EXTENDS relationships (base classes)
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_name = base.id
                base_id = resolve_reference(self.repository, self.file_path, base_name, None, self.index)
                if base_id:
                    rel = Relationship(
                        id=generate_relationship_id(RelationshipType.INHERITS, class_id, base_id),
                        type=RelationshipType.INHERITS,
                        source_id=class_id,
                        target_id=base_id,
                    )
                    self.relationships.append(rel)

        self.namespace_stack.append((node.name, EntityType.CLASS))
        self.generic_visit(node)
        self.namespace_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        entity_type = EntityType.METHOD if self.namespace_stack else EntityType.FUNCTION
        qname = self._get_qualified_name(node.name)
        func_id = generate_entity_id(entity_type, self.file_path, qname)

        prev_caller = self.current_caller_id
        self.current_caller_id = func_id
        self.namespace_stack.append((node.name, entity_type))

        self.generic_visit(node)

        self.namespace_stack.pop()
        self.current_caller_id = prev_caller

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def visit_Call(self, node: ast.Call):
        if self.current_caller_id:
            callee_name = None
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name:
                # Try to resolve the callee
                callee_id = resolve_reference(self.repository, self.file_path, callee_name, self.current_caller_id, self.index)

                if not callee_id:
                    # Fallback: assume same module
                    module_path = self.file_path.replace("/", ".").replace(".py", "")
                    if module_path.endswith(".__init__"):
                        module_path = module_path[:-9]
                    callee_qname = f"{module_path}.{callee_name}" if module_path else callee_name
                    callee_id = generate_entity_id(EntityType.FUNCTION, self.file_path, callee_qname)

                rel = Relationship(
                    id=generate_relationship_id(RelationshipType.CALLS, self.current_caller_id, callee_id),
                    type=RelationshipType.CALLS,
                    source_id=self.current_caller_id,
                    target_id=callee_id,
                    metadata={"call_name": callee_name}
                )
                self.relationships.append(rel)

        self.generic_visit(node)


class TypeScriptCallGraphVisitor:
    """Extract calls and relationships from tree-sitter AST (TS/JS)."""

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

    def visit(self, node, depth=0):
        """Traverse the AST and extract relationships."""
        import logging
        logger = logging.getLogger(__name__)

        if depth == 0:
            logger.debug(f"[TS Visitor] Starting traversal from {node.type}")

        if node.type == 'class_declaration':
            self._handle_class_declaration(node)
        elif node.type == 'function_declaration':
            self._handle_function_declaration(node)
        elif node.type == 'lexical_declaration':
            self._handle_lexical_declaration(node)
        elif node.type == 'call_expression' and self.current_caller_id:
            self._handle_call_expression(node)
        elif node.type in ('jsx_self_closing_element', 'jsx_opening_element') and self.current_caller_id:
            self._handle_jsx_element(node)

        # Recurse
        for child in node.children:
            self.visit(child, depth + 1)

    def _handle_class_declaration(self, node):
        """Extract class and potential extends/implements."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return

        class_name = self._get_text(name_node)
        module_path = self.file_path.rsplit(".", 1)[0].replace("/", ".")
        qname = f"{module_path}.{class_name}"
        class_id = generate_entity_id(EntityType.CLASS, self.file_path, qname)

        # Check for superclass
        superclass = node.child_by_field_name('superclass')
        if superclass:
            superclass_name = self._get_text(superclass).strip()
            base_id = resolve_reference(self.repository, self.file_path, superclass_name, None, self.index)
            if base_id:
                rel = Relationship(
                    id=generate_relationship_id(RelationshipType.INHERITS, class_id, base_id),
                    type=RelationshipType.INHERITS,
                    source_id=class_id,
                    target_id=base_id,
                )
                self.relationships.append(rel)

        # Traverse class body
        class_body = node.child_by_field_name('body')
        if class_body:
            prev_caller = self.current_caller_id
            for child in class_body.children:
                if child.type == 'method_definition':
                    method_name_node = child.child_by_field_name('name')
                    if method_name_node:
                        method_name = self._get_text(method_name_node)
                        method_qname = f"{module_path}.{class_name}.{method_name}"
                        self.current_caller_id = generate_entity_id(EntityType.METHOD, self.file_path, method_qname)
                        self.visit(child)
                        self.current_caller_id = prev_caller
                else:
                    self.visit(child)
        else:
            for child in node.children:
                self.visit(child)

    def _handle_function_declaration(self, node):
        """Extract function declarations."""
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
        """Extract arrow/function expressions and their calls."""
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

    def _handle_call_expression(self, node):
        """Extract function calls."""
        func_node = node.child_by_field_name('function')
        if not func_node:
            return

        callee_name = self._get_text(func_node).strip()
        # Handle method calls (obj.method) and simple calls
        if "." in callee_name:
            parts = callee_name.rsplit(".", 1)
            callee_name = parts[-1]
        if "(" in callee_name:
            callee_name = callee_name.split("(")[0]

        # Resolve the callee
        callee_id = resolve_reference(self.repository, self.file_path, callee_name, self.current_caller_id, self.index)

        if not callee_id:
            # Fallback: assume same module
            module_path = self.file_path.rsplit(".", 1)[0].replace("/", ".")
            callee_qname = f"{module_path}.{callee_name}"
            callee_id = generate_entity_id(EntityType.FUNCTION, self.file_path, callee_qname)

        if self.current_caller_id:
            rel = Relationship(
                id=generate_relationship_id(RelationshipType.CALLS, self.current_caller_id, callee_id),
                type=RelationshipType.CALLS,
                source_id=self.current_caller_id,
                target_id=callee_id,
                metadata={"call_name": callee_name}
            )
            self.relationships.append(rel)

    def _handle_jsx_element(self, node):
        """Extract JSX component rendering: <ComponentName />."""
        # For jsx_self_closing_element and jsx_opening_element,
        # the first child is the tag name identifier
        tag_node = None
        for child in node.children:
            if child.type in ('identifier', 'jsx_identifier', 'type_identifier'):
                tag_node = child
                break

        if not tag_node:
            return

        component_name = self._get_text(tag_node).strip()

        # Skip built-in HTML elements (lowercase)
        if component_name[0].islower():
            return

        # Resolve component to its definition
        component_id = resolve_reference(self.repository, self.file_path, component_name, self.current_caller_id, self.index)

        if not component_id:
            # Fallback: assume same module
            module_path = self.file_path.rsplit(".", 1)[0].replace("/", ".")
            component_qname = f"{module_path}.{component_name}"
            component_id = generate_entity_id(EntityType.FUNCTION, self.file_path, component_qname)

        if self.current_caller_id:
            rel = Relationship(
                id=generate_relationship_id(RelationshipType.RENDERS, self.current_caller_id, component_id),
                type=RelationshipType.RENDERS,
                source_id=self.current_caller_id,
                target_id=component_id,
                metadata={"component": component_name}
            )
            self.relationships.append(rel)


class CallGraphAnalyzer(BaseAnalyzer):
    name = "CallGraphAnalyzer"
    supported_languages = ["Python", "TypeScript", "JavaScript"]

    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"[CallGraphAnalyzer] Starting with {len(repository.relationships)} existing relationships")
        index = SymbolIndex(repository)

        for file_path, parsed in asts.items():
            if parsed.language not in self.supported_languages or not parsed.ast:
                logger.debug(f"[CallGraphAnalyzer] Skipping {file_path}: lang={parsed.language}, has_ast={bool(parsed.ast)}")
                continue

            logger.debug(f"[CallGraphAnalyzer] Processing {file_path}: ast_type={type(parsed.ast).__name__}")

            try:
                if parsed.language == "Python":
                    visitor = PythonCallGraphVisitor(file_path, repository, index)
                    visitor.visit(parsed.ast)
                    logger.info(f"[CallGraphAnalyzer] Python {file_path}: extracted {len(visitor.relationships)} relationships")
                    for rel in visitor.relationships:
                        repository.relationships[rel.id] = rel

                elif parsed.language in ("TypeScript", "JavaScript"):
                    visitor = TypeScriptCallGraphVisitor(file_path, parsed.source, repository, index)
                    visitor.visit(parsed.ast.root_node)
                    logger.info(f"[CallGraphAnalyzer] TS/JS {file_path}: extracted {len(visitor.relationships)} relationships")
                    for rel in visitor.relationships:
                        repository.relationships[rel.id] = rel
            except Exception as e:
                logger.error(f"[CallGraphAnalyzer] Error processing {file_path}: {e}", exc_info=True)

        logger.info(f"[CallGraphAnalyzer] Complete with {len(repository.relationships)} total relationships")
