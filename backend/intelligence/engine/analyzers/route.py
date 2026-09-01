"""
Route Analyzer: extract route definitions from Python (FastAPI/Flask) and Next.js.

Detects:
- Python decorators: @app.get(), @router.post(), etc.
- Next.js file-based routes: app/*/page.tsx, pages/*.tsx
- Next.js API routes: app/api/*/route.ts
"""
import ast
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from .base import BaseAnalyzer
from ..parser.providers.base import ParsedFile
from ...rim.repository import RepositoryModel
from ...rim.entity import Entity
from ...rim.relationship import Relationship
from ...rim.enums import EntityType, RelationshipType
from ...rim.location import SourceLocation
from ...rim.identity import generate_entity_id, generate_relationship_id


class PythonRouteVisitor(ast.NodeVisitor):
    """Extract FastAPI/Flask route decorators."""

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

    def visit_FunctionDef(self, node: ast.FunctionDef):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                func = decorator.func
                method = None

                # Check for @app.get(), @router.post(), etc.
                if isinstance(func, ast.Attribute) and func.attr in ("get", "post", "put", "delete", "patch"):
                    method = func.attr.upper()

                if method and decorator.args:
                    arg = decorator.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        path = arg.value

                        route_name = f"{method} {path}"
                        route_id = generate_entity_id(EntityType.ROUTE, self.file_path, route_name)

                        self.entities.append(Entity(
                            id=route_id,
                            type=EntityType.ROUTE,
                            name=route_name,
                            location=SourceLocation(
                                repository_path=self.file_path,
                                start_line=node.lineno,
                                end_line=node.lineno,
                                language="Python"
                            ),
                            metadata={"method": method, "path": path, "framework": "FastAPI/Flask"}
                        ))

                        func_qname = self._get_qualified_name(node.name)
                        func_id = generate_entity_id(EntityType.FUNCTION, self.file_path, func_qname)

                        self.relationships.append(Relationship(
                            id=generate_relationship_id(RelationshipType.EXPOSES, func_id, route_id),
                            type=RelationshipType.EXPOSES,
                            source_id=func_id,
                            target_id=route_id
                        ))

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)


class NextJsRouteExtractor:
    """Extract Next.js file-based routes."""

    @staticmethod
    def extract_route(file_path: str) -> Optional[Tuple[str, str, str]]:
        """Extract route path from Next.js file.

        Returns:
            (route_path, route_type, framework) or None if not a route file
        """
        path_parts = file_path.split("/")

        # Check for app directory routes (Next.js 13+)
        if "app" in path_parts:
            app_idx = path_parts.index("app")
            route_parts = path_parts[app_idx + 1:]

            if not route_parts:
                return None

            file_name = route_parts[-1]
            dir_parts = route_parts[:-1]

            if file_name == "page.tsx" or file_name == "page.js" or file_name == "page.jsx" or file_name == "page.ts":
                # Page route
                route_path = "/" + "/".join(dir_parts) if dir_parts else "/"
                # Convert [param] to :param, [...slug] to *
                route_path = re.sub(r"\[\.\.\.(\w+)\]", "*", route_path)
                route_path = re.sub(r"\[(\w+)\]", r":\1", route_path)
                return (route_path, "PAGE", "Next.js")

            elif file_name == "route.ts" or file_name == "route.js":
                # API route
                route_path = "/" + "/".join(dir_parts) if dir_parts else "/"
                route_path = re.sub(r"\[\.\.\.(\w+)\]", "*", route_path)
                route_path = re.sub(r"\[(\w+)\]", r":\1", route_path)
                return (route_path, "API", "Next.js")

            elif file_name == "layout.tsx" or file_name == "layout.js":
                # Layout file (not a direct route but affects routing)
                route_path = "/" + "/".join(dir_parts) if dir_parts else "/"
                return (route_path, "LAYOUT", "Next.js")

        # Check for pages directory routes (Next.js 12 and earlier)
        elif "pages" in path_parts:
            pages_idx = path_parts.index("pages")
            route_parts = path_parts[pages_idx + 1:]

            if not route_parts:
                return None

            file_name = route_parts[-1]
            if file_name in ("index.tsx", "index.js", "index.jsx", "index.ts"):
                # Index route
                dir_parts = route_parts[:-1]
                route_path = "/" + "/".join(dir_parts) if dir_parts else "/"
            elif file_name.endswith(".tsx") or file_name.endswith(".js"):
                # Regular route
                route_parts[-1] = file_name.rsplit(".", 1)[0]
                route_path = "/" + "/".join(route_parts)
                # Convert [param] to :param
                route_path = re.sub(r"\[(\w+)\]", r":\1", route_path)
            else:
                return None

            return (route_path, "PAGE", "Next.js")

        return None


class RouteAnalyzer(BaseAnalyzer):
    """Extract route definitions from Python and Next.js."""

    name = "RouteAnalyzer"
    supported_languages = ["Python", "TypeScript", "JavaScript"]

    def analyze(self, repository: RepositoryModel, asts: Dict[str, ParsedFile]) -> None:
        for file_path, parsed in asts.items():
            if not parsed.ast:
                continue

            # Python routes
            if parsed.language == "Python":
                visitor = PythonRouteVisitor(file_path)
                visitor.visit(parsed.ast)
                for ent in visitor.entities:
                    repository.entities[ent.id] = ent
                for rel in visitor.relationships:
                    repository.relationships[rel.id] = rel

            # Next.js routes (TS/JS)
            elif parsed.language in ("TypeScript", "JavaScript"):
                result = NextJsRouteExtractor.extract_route(file_path)
                if result:
                    route_path, route_type, framework = result

                    route_name = f"{route_type} {route_path}"
                    route_id = generate_entity_id(EntityType.ROUTE, file_path, route_name)

                    # Create route entity
                    repository.entities[route_id] = Entity(
                        id=route_id,
                        type=EntityType.ROUTE,
                        name=route_name,
                        location=SourceLocation(
                            repository_path=file_path,
                            start_line=1,
                            end_line=1,
                            language=parsed.language
                        ),
                        metadata={
                            "path": route_path,
                            "route_type": route_type,
                            "framework": framework,
                            "file": file_path
                        }
                    )

                    # Create EXPOSES relationship to default export (if we can find it)
                    file_id = generate_entity_id(EntityType.FILE, file_path, file_path)
                    rel = Relationship(
                        id=generate_relationship_id(RelationshipType.EXPOSES, file_id, route_id),
                        type=RelationshipType.EXPOSES,
                        source_id=file_id,
                        target_id=route_id
                    )
                    repository.relationships[rel.id] = rel
