from typing import List, Optional
from ..scanner.scanner import RepositoryScanner
from ..parser.manager import ASTParserManager
from ..analyzers.registry import AnalyzerRegistry
from ...rim.repository import RepositoryModel
from ...rim.metadata import RepositoryMetadata
from ...rim.validation import RIMValidator
from pathlib import Path

class AnalysisEngine:
    """
    Orchestrates the deterministic extraction pipeline.
    """
    def __init__(self, target_dir: str, registry: AnalyzerRegistry):
        self.target_dir = str(Path(target_dir).resolve())
        self.registry = registry
        
    def run(self, repo_name: str, commit_info: Optional[dict] = None) -> RepositoryModel:
        # 1. Scan Repository
        scanner = RepositoryScanner(self.target_dir)
        manifest = scanner.scan()
        
        # Inject GitHub commit info if provided (since we use zipballs without .git dirs)
        if commit_info:
            manifest.metadata.commit_hash = commit_info.get("hash")
            manifest.metadata.commit_timestamp = commit_info.get("timestamp")
            manifest.metadata.branch = commit_info.get("branch")
            manifest.metadata.remote_url = commit_info.get("remote_url")
        
        # Initialize RIM
        model = RepositoryModel(
            metadata=RepositoryMetadata(
                name=repo_name,
                path=self.target_dir,
                languages=manifest.languages,
                commit=manifest.metadata.commit_hash or "",
                branch=manifest.metadata.branch or "",
                metadata={
                    "primary_language": manifest.primary_language,
                    "frameworks": manifest.frameworks,
                    "commit_timestamp": manifest.metadata.commit_timestamp,
                    "remote_url": manifest.metadata.remote_url
                }
            )
        )
        
        # 2. Parse ASTs
        parser_manager = ASTParserManager(self.target_dir)
        asts = parser_manager.parse_manifest(manifest)
        
        # 3. Execute Analyzers
        # Analyzers should ideally be topologically sorted based on dependencies.
        # For now, we assume the registry order is safe (e.g., SymbolAnalyzer first).
        for analyzer in self.registry.get_all():
            analyzer.analyze(model, asts)
            
        # 4. Validate RIM
        validator = RIMValidator(model)
        if not validator.validate():
            # In production, we'd log warnings or raise an error
            pass
            
        return model
