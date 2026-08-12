import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.intelligence.engine.scanner.manifest import RepositoryManifest, RepositoryMetadata
from backend.intelligence.engine.scanner.detector import LanguageDetector, FrameworkDetector
from backend.intelligence.engine.scanner.scanner import RepositoryScanner

def test_language_detector():
    assert LanguageDetector.detect_language("main.py") == "Python"
    assert LanguageDetector.detect_language("app.js") == "JavaScript"
    assert LanguageDetector.detect_language("unknown.xyz") == "Unknown"
    assert LanguageDetector.detect_language("Dockerfile") == "Dockerfile"

def test_framework_detector(tmp_path):
    # Create fake pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("dependencies = ['fastapi', 'uvicorn']")
    
    frameworks = FrameworkDetector.detect_frameworks(str(tmp_path))
    assert "FastAPI" in frameworks
    assert "Flask" not in frameworks
    
    # Add requirements.txt with flask
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("flask==2.0.1\ndjango>=3.2")
    
    frameworks = FrameworkDetector.detect_frameworks(str(tmp_path))
    assert "FastAPI" in frameworks
    assert "Flask" in frameworks
    assert "Django" in frameworks

@patch("subprocess.run")
def test_repository_scanner_git_metadata(mock_run, tmp_path):
    # Mock subprocess.run for git commands
    def side_effect(*args, **kwargs):
        cmd = args[0]
        mock = MagicMock()
        mock.returncode = 0
        if "rev-parse" in cmd and "--is-inside-work-tree" in cmd:
            mock.stdout = "true\n"
        elif "rev-parse" in cmd and "HEAD" in cmd and "--abbrev-ref" not in cmd:
            mock.stdout = "abc123def456\n"
        elif "log" in cmd:
            mock.stdout = "2023-10-01T12:00:00Z\n"
        elif "--abbrev-ref" in cmd:
            mock.stdout = "main\n"
        elif "config" in cmd:
            mock.stdout = "https://github.com/test/repo.git\n"
        return mock
        
    mock_run.side_effect = side_effect
    
    # Create some dummy files to test size aggregation
    (tmp_path / "main.py").write_text("print('hello')") # 14 bytes
    (tmp_path / "utils.py").write_text("def a(): pass") # 13 bytes
    (tmp_path / "script.js").write_text("console.log('hi')") # 17 bytes (but Python total is 27)
    
    scanner = RepositoryScanner(str(tmp_path))
    manifest = scanner.scan()
    
    # Verify Git metadata
    assert manifest.metadata.commit_hash == "abc123def456"
    assert manifest.metadata.commit_timestamp == "2023-10-01T12:00:00Z"
    assert manifest.metadata.branch == "main"
    assert manifest.metadata.remote_url == "https://github.com/test/repo.git"
    
    # Verify primary language
    assert manifest.primary_language == "Python"
    assert "Python" in manifest.languages
    assert "JavaScript" in manifest.languages
