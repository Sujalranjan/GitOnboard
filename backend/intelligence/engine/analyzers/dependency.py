import json
from typing import Dict
from .base import BaseAnalyzer
from ..parser.providers.base import ParsedFile
from ...rim.repository import RepositoryModel
from ...rim.entity import Entity
from ...rim.relationship import Relationship
from ...rim.enums import EntityType, RelationshipType
from ...rim.location import SourceLocation
from ...rim.identity import generate_entity_id, generate_relationship_id

class DependencyAnalyzer(BaseAnalyzer):
    name = "DependencyAnalyzer"
    supported_languages = ["JSON", "TOML", "XML", "Python"]

    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        for file_path, parsed in asts.items():
            if file_path.endswith("package.json"):
                self._analyze_package_json(repository, parsed)
            elif file_path.endswith("requirements.txt"):
                self._analyze_requirements_txt(repository, parsed)

    def _add_dependency(self, repository: RepositoryModel, parsed: ParsedFile, source_pkg_id: str, dep_name: str, version: str):
        dep_id = generate_entity_id(EntityType.DEPENDENCY, parsed.file_path, dep_name)
        
        if dep_id not in repository.entities:
            repository.entities[dep_id] = Entity(
                id=dep_id,
                type=EntityType.DEPENDENCY,
                name=dep_name,
                location=SourceLocation(repository_path=parsed.file_path, start_line=1, end_line=1, language="Unknown"),
                metadata={"version": version, "file_id": parsed.file_path}
            )
            
        rel_id = generate_relationship_id(RelationshipType.DEPENDS_ON, source_pkg_id, dep_id)
        repository.relationships[rel_id] = Relationship(
            id=rel_id,
            type=RelationshipType.DEPENDS_ON,
            source_id=source_pkg_id,
            target_id=dep_id
        )

    def _analyze_package_json(self, repository: RepositoryModel, parsed: ParsedFile):
        try:
            data = json.loads(parsed.source)
            pkg_name = data.get("name", "unknown_package")
            pkg_id = generate_entity_id(EntityType.PACKAGE, parsed.file_path, pkg_name)
            
            deps = data.get("dependencies", {})
            dev_deps = data.get("devDependencies", {})
            
            for dep_name, version in deps.items():
                self._add_dependency(repository, parsed, pkg_id, dep_name, version)
            for dep_name, version in dev_deps.items():
                self._add_dependency(repository, parsed, pkg_id, dep_name, version)
        except Exception:
            pass

    def _analyze_requirements_txt(self, repository: RepositoryModel, parsed: ParsedFile):
        pkg_id = generate_entity_id(EntityType.PACKAGE, parsed.file_path, "python_package")
        
        for line in parsed.source.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
                
            dep_name = line.split("==")[0].split(">=")[0].strip()
            self._add_dependency(repository, parsed, pkg_id, dep_name, line)
