import inspect
import importlib
import pkgutil
from typing import Dict, List, Type
from .interfaces import Analyzer
from .exceptions import PluginRegistrationError

class AnalyzerRegistry:
    def __init__(self):
        self._analyzers: Dict[str, Type[Analyzer]] = {}

    def register(self, analyzer_class: Type[Analyzer]) -> None:
        """Register an analyzer class."""
        if not inspect.isclass(analyzer_class) or not issubclass(analyzer_class, Analyzer) or inspect.isabstract(analyzer_class):
            raise PluginRegistrationError(f"{getattr(analyzer_class, '__name__', str(analyzer_class))} must be a concrete Analyzer.")
        
        try:
            instance = analyzer_class()
            name = instance.name
        except Exception as e:
            raise PluginRegistrationError(f"Failed to instantiate analyzer {analyzer_class.__name__}: {e}")

        if name in self._analyzers:
            raise PluginRegistrationError(f"Analyzer with name '{name}' is already registered.")
            
        self._analyzers[name] = analyzer_class

    def unregister(self, name: str) -> None:
        """Unregister an analyzer by name."""
        if name in self._analyzers:
            del self._analyzers[name]
        else:
            raise PluginRegistrationError(f"Analyzer '{name}' not found.")

    def get_all(self) -> List[Type[Analyzer]]:
        """Return a list of all registered analyzer classes."""
        return list(self._analyzers.values())
        
    def discover(self, package: str) -> None:
        """Dynamically load analyzers from a given package."""
        try:
            package_module = importlib.import_module(package)
            if hasattr(package_module, "__path__"):
                for _, name, _ in pkgutil.iter_modules(package_module.__path__):
                    full_name = f"{package}.{name}"
                    module = importlib.import_module(full_name)
                    for _, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, Analyzer) and not inspect.isabstract(obj):
                            try:
                                self.register(obj)
                            except PluginRegistrationError:
                                pass # Might already be registered or failed to init
        except ImportError as e:
            raise PluginRegistrationError(f"Failed to discover plugins in {package}: {e}")
