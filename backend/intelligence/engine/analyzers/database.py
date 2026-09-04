import ast
from typing import Dict, List
from .base import BaseAnalyzer
from ..parser.providers.base import ParsedFile
from ...rim.repository import RepositoryModel
from ...rim.entity import Entity
from ...rim.relationship import Relationship
from ...rim.enums import EntityType, RelationshipType
from ...rim.location import SourceLocation
from ...rim.identity import generate_entity_id, generate_relationship_id

class PythonDatabaseVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.entities: List[Entity] = []
        self.relationships: List[Relationship] = []

    def _get_qualified_name(self, name: str) -> str:
        parts = []
        module_path = self.file_path.replace("/", ".").replace(".py", "")
        if module_path.endswith(".__init__"):
            module_path = module_path[:-9]
        if module_path:
            parts.append(module_path)
        if name:
            parts.append(name)
        return ".".join(parts)

    def visit_ClassDef(self, node: ast.ClassDef):
        # Extremely simplistic heuristic: SQLAlchemy classes usually inherit from Base, Model, etc.
        # Or have __tablename__
        is_model = False
        table_name = node.name.lower() + "s"
        
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        is_model = True
                        if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                            table_name = item.value.value
                            
        if is_model:
            table_id = generate_entity_id(EntityType.TABLE, "database", table_name)

            self.entities.append(Entity(
                id=table_id,
                type=EntityType.TABLE,
                name=table_name,
                location=SourceLocation(repository_path=self.file_path, start_line=node.lineno, end_line=node.lineno, language="Python"),
                metadata={"orm_class": node.name, "file_id": self.file_path}
            ))
            
            class_qname = self._get_qualified_name(node.name)
            class_id = generate_entity_id(EntityType.CLASS, self.file_path, class_qname)
            self.relationships.append(Relationship(
                id=generate_relationship_id(RelationshipType.USES, class_id, table_id),
                type=RelationshipType.USES,
                source_id=class_id,
                target_id=table_id
            ))
            
        self.generic_visit(node)


class DatabaseAnalyzer(BaseAnalyzer):
    name = "DatabaseAnalyzer"
    supported_languages = ["Python"]

    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        for file_path, parsed in asts.items():
            if parsed.language not in self.supported_languages or not parsed.ast:
                continue
                
            visitor = PythonDatabaseVisitor(file_path)
            visitor.visit(parsed.ast)
            
            for ent in visitor.entities:
                repository.entities[ent.id] = ent
            for rel in visitor.relationships:
                repository.relationships[rel.id] = rel
