"""
Phase 3A Upstream Corrections Unit Test Suite.
Verifies framework detection from package.json, TypeScript AST import parsing,
frontend .tsx/.jsx entrypoint detection, Fact Store doc content retrieval, and module context assembly.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.intelligence.engine.scanner.detector import FrameworkDetector
from backend.intelligence.parser import LanguageParser
from backend.intelligence.stages.metadata_stage import RepositoryMetadataStage, KNOWN_FRAMEWORKS, ENTRYPOINT_PATTERNS
from backend.summary.discovery import DocDiscovery
from backend.summary.generator import SummaryGenerator
from backend.summary.schemas import BudgetedDocContext
from backend.models.fact_store import FactFile


def test_package_json_framework_detection(tmp_path):
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(json.dumps({
        "name": "deep-guard-frontend",
        "dependencies": {
            "react": "^18.2.0",
            "react-dom": "^18.2.0",
            "tailwindcss": "^3.3.0"
        },
        "devDependencies": {
            "vite": "^4.4.5",
            "typescript": "^5.0.2"
        }
    }), encoding="utf-8")

    frameworks = FrameworkDetector.detect_frameworks(str(tmp_path))
    assert "React" in frameworks
    assert "Tailwind CSS" in frameworks
    assert "Vite" in frameworks


def test_typescript_ast_named_import_extraction():
    parser = LanguageParser()
    ts_code = """
    import React from "react";
    import { useState, useEffect } from 'react';
    import { AnalysisHistory } from "./components/AnalysisHistory";
    import axios from 'axios';
    """
    tree, lang = parser.parse_source(ts_code, ".tsx")
    entities = parser.extract_entities(tree, ts_code, "test.tsx", "test_mod")

    imported_modules = [imp["module_name"] for imp in entities["imports"]]
    assert "react" in imported_modules
    assert "./components/AnalysisHistory" in imported_modules
    assert "axios" in imported_modules



def test_frontend_entrypoint_patterns():
    assert "main.tsx" in ENTRYPOINT_PATTERNS
    assert "App.tsx" in ENTRYPOINT_PATTERNS
    assert "index.tsx" in ENTRYPOINT_PATTERNS
    assert "vite.config.ts" in ENTRYPOINT_PATTERNS
    assert "next.config.js" in ENTRYPOINT_PATTERNS


def test_fact_store_doc_content_retrieval():
    discovery = DocDiscovery()
    mock_db = MagicMock()
    
    mock_file = MagicMock(spec=FactFile)
    mock_file.path = "README.md"
    mock_file.is_documentation = True
    mock_file.blob_name = "blob_readme_123"
    mock_file.size = 150
    
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_file]
    
    with patch("backend.storage.get_storage") as mock_get_storage:
        mock_storage = MagicMock()
        mock_storage.get_object_text.return_value = "# Deep Guard\nFrontend security monitoring portal."
        mock_get_storage.return_value = mock_storage
        
        docs = discovery.discover_from_fact_store(mock_db, analysis_id=1)
        assert len(docs) == 1
        assert docs[0].path == "README.md"
        assert len(docs[0].content) > 0
        assert "Deep Guard" in docs[0].content
        assert docs[0].line_count >= 2


def test_summary_generator_module_fallback_context():
    mock_llm = MagicMock()
    generator = SummaryGenerator(llm_service=mock_llm)
    
    metadata = {
        "repository": {"name": "Deep-Guard-Frontend", "primary_language": "TypeScript"},
        "frameworks": ["React", "Vite"],
        "entrypoints": ["src/main.tsx"],
        "modules": []  # Empty from metadata
    }
    metrics = {
        "total_files": 90,
        "lines_of_code": 17554,
        "largest_modules": [
            {"module": "src/components/AnalysisHistory.tsx", "count": 13},
            {"module": "src/components/AccountSettings.tsx", "count": 8}
        ]
    }
    
    doc_context = BudgetedDocContext()
    context_str = generator.build_prompt_context(metadata, metrics, doc_context)
    
    assert "Deep-Guard-Frontend" in context_str
    assert "React" in context_str
    assert "src/main.tsx" in context_str
    assert "src/components/AnalysisHistory.tsx" in context_str
