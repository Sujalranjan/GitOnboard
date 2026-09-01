from .base import BaseAnalyzer
from .registry import AnalyzerRegistry
from .symbol import SymbolAnalyzer
from .imports import ImportAnalyzer
from .type import TypeAnalyzer
from .callgraph import CallGraphAnalyzer
from .uses import UsesAnalyzer
from .route import RouteAnalyzer
from .database import DatabaseAnalyzer
from .config import ConfigAnalyzer
from .dependency import DependencyAnalyzer
from .test import TestAnalyzer

def get_default_registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    registry.register(ConfigAnalyzer())
    registry.register(DependencyAnalyzer())
    registry.register(SymbolAnalyzer())
    registry.register(ImportAnalyzer())
    registry.register(TypeAnalyzer())
    registry.register(CallGraphAnalyzer())
    registry.register(UsesAnalyzer())
    registry.register(RouteAnalyzer())
    registry.register(DatabaseAnalyzer())
    registry.register(TestAnalyzer())
    return registry

__all__ = ["BaseAnalyzer", "AnalyzerRegistry", "get_default_registry"]
