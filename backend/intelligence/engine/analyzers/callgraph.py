import ast
from typing import Dict, List
from .base import BaseAnalyzer
from ..parser.providers.base import ParsedFile
from ...rim.repository import RepositoryModel
from ...rim.relationship import Relationship
from ...rim.enums import EntityType, RelationshipType
from ...rim.identity import generate_entity_id, generate_relationship_id

class PythonCallGraphVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.relationships: List[Relationship] = []
        self.current_caller_id: str = None
        self.namespace_stack: List[str] = []

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

    def visit_ClassDef(self, node: ast.ClassDef):
        self.namespace_stack.append(node.name)
        self.generic_visit(node)
        self.namespace_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        entity_type = EntityType.METHOD if self.namespace_stack else EntityType.FUNCTION
        qname = self._get_qualified_name(node.name)
        caller_id = generate_entity_id(entity_type, self.file_path, qname)
        
        prev_caller = self.current_caller_id
        self.current_caller_id = caller_id
        self.namespace_stack.append(node.name)
        
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


class CallGraphAnalyzer(BaseAnalyzer):
    name = "CallGraphAnalyzer"
    supported_languages = ["Python"]

    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        for file_path, parsed in asts.items():
            if parsed.language not in self.supported_languages or not parsed.ast:
                continue
                
            visitor = PythonCallGraphVisitor(file_path)
            visitor.visit(parsed.ast)
            
            for rel in visitor.relationships:
                # In a strict environment, we'd ensure target_id exists in repository.entities.
                # Since cross-file calls are hard to resolve perfectly without a binder, 
                # we just insert the relationship. 
                repository.relationships[rel.id] = rel
