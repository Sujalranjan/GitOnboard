import json
from typing import Dict
from pathlib import Path
from .base import BaseAnalyzer
from ..parser.providers.base import ParsedFile
from ...rim.repository import RepositoryModel
from ...rim.entity import Entity
from ...rim.enums import EntityType
from ...rim.location import SourceLocation
from ...rim.identity import generate_entity_id

class ConfigAnalyzer(BaseAnalyzer):
    name = "ConfigAnalyzer"
    supported_languages = ["JSON", "Dockerfile"]

    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        for file_path, parsed in asts.items():
            if file_path.endswith("package.json"):
                self._analyze_package_json(repository, parsed)
            elif file_path.endswith("Dockerfile"):
                self._analyze_dockerfile(repository, parsed)

    def _analyze_package_json(self, repository: RepositoryModel, parsed: ParsedFile):
        try:
            data = json.loads(parsed.source)
            # Create a PACKAGE entity
            pkg_name = data.get("name", "unknown_package")
            pkg_id = generate_entity_id(EntityType.PACKAGE, parsed.file_path, pkg_name)
            
            repository.entities[pkg_id] = Entity(
                id=pkg_id,
                type=EntityType.PACKAGE,
                name=pkg_name,
                location=SourceLocation(repository_path=parsed.file_path, start_line=1, end_line=1, language="JSON"),
                metadata={"version": data.get("version", ""), "scripts": data.get("scripts", {}), "file_id": parsed.file_path}
            )
            
            # Dependencies will be extracted by DependencyAnalyzer
        except Exception:
            pass

    def _analyze_dockerfile(self, repository: RepositoryModel, parsed: ParsedFile):
        # Very simple docker extraction
        image_name = parsed.file_path.split("/")[-2] if "/" in parsed.file_path else "root_image"
        doc_id = generate_entity_id(EntityType.DOCKER_SERVICE, parsed.file_path, image_name)
        
        repository.entities[doc_id] = Entity(
            id=doc_id,
            type=EntityType.DOCKER_SERVICE,
            name=image_name,
            location=SourceLocation(repository_path=parsed.file_path, start_line=1, end_line=1, language="Dockerfile"),
            metadata={"source": parsed.source, "file_id": parsed.file_path}
        )
