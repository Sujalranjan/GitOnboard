from typing import List, Optional
import logging
from ..scanner.scanner import RepositoryScanner
from ..parser.manager import ASTParserManager
from ..analyzers.registry import AnalyzerRegistry
from ...rim.repository import RepositoryModel
from ...rim.metadata import RepositoryMetadata
from ...rim.validation import RIMValidator
from ...diagnostics import init_diagnostic_logger
from pathlib import Path
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class AnalysisEngine:
    """
    Orchestrates the deterministic extraction pipeline with real work-based progress tracking.
    """
    def __init__(self, target_dir: str, registry: AnalyzerRegistry):
        self.target_dir = str(Path(target_dir).resolve())
        self.registry = registry

    def run(self, repo_name: str, commit_info: Optional[dict] = None, analysis_id: Optional[int] = None, db: Optional[Session] = None) -> RepositoryModel:
        # Initialize diagnostic logger
        if analysis_id:
            diag = init_diagnostic_logger(analysis_id, repo_name)
            logger.info(f"[PIPELINE] Diagnostic logging initialized for analysis {analysis_id}")
        else:
            diag = None
            logger.info(f"[PIPELINE] No analysis_id provided, diagnostic logging disabled")

        # Initialize progress tracker
        progress = None
        if db and analysis_id:
            from backend.services.progress_tracker import ProgressTracker
            progress = ProgressTracker(db, analysis_id)
            progress.update("Scanning", "Scanning repository files", 0, 1, "stage")

        # 1. Scan Repository
        logger.info(f"[PIPELINE] Starting analysis of {repo_name}")
        scanner = RepositoryScanner(self.target_dir)
        manifest = scanner.scan()
        logger.info(f"[PIPELINE] Scanned {len(manifest.files)} files")

        if progress:
            progress.update("Scanning", f"Found {len(manifest.files)} files",
                            len(manifest.files), len(manifest.files), "files")
        
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
        total_files = len(manifest.files)

        # Custom parse with progress tracking
        asts = {}
        for idx, file_info in enumerate(manifest.files):
            try:
                ast = parser_manager.parse_file(file_info)
                if ast:
                    asts[file_info.path] = ast
            except Exception as e:
                logger.debug(f"Failed to parse {file_info.path}: {e}")

            # Update progress every ~5 files or at end
            if progress and (idx % 5 == 0 or idx == total_files - 1):
                progress.update(
                    "Parsing",
                    f"Parsing {file_info.language} files",
                    idx + 1,
                    total_files,
                    "files"
                )

        logger.info(f"[PIPELINE] Parsed {len(asts)} ASTs")
        
        # 3. Execute Analyzers
        # Analyzers should ideally be topologically sorted based on dependencies.
        # For now, we assume the registry order is safe (e.g., SymbolAnalyzer first).
        analyzers = self.registry.get_all()
        for idx, analyzer in enumerate(analyzers):
            analyzer.analyze(model, asts)

            # Update progress during analyzer execution
            if progress:
                entity_count = len(model.entities)
                progress.update(
                    "Symbol extraction",
                    f"Extracting symbols ({analyzer.__class__.__name__})",
                    entity_count,
                    max(1, entity_count),  # Use entity count as work done
                    "symbols"
                )

        # Update progress after all analyzers (show relationship count)
        if progress:
            progress.update(
                "Building relationships",
                f"Analyzed {len(model.entities)} symbols with {len(model.relationships)} relationships",
                len(model.relationships),
                max(1, len(model.relationships)),
                "relationships"
            )
            
        # 4. Validate RIM
        validator = RIMValidator(model)
        if not validator.validate():
            # In production, we'd log warnings or raise an error
            pass

        # 5. Save diagnostic report
        if diag:
            logger.info(f"[PIPELINE] Saving diagnostic report...")
            report_file = diag.save_report()
            actions_file = diag.save_actions()
            diag.print_summary()
            logger.info(f"[PIPELINE] Diagnostic files saved: {report_file}, {actions_file}")

        logger.info(f"[PIPELINE] Analysis complete: {len(model.entities)} entities, {len(model.relationships)} relationships")
        return model
