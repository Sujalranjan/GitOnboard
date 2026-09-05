"""
Tests for file eligibility and classification.

Validates that:
- .next/ files are excluded
- node_modules/ files are excluded
- .git/ files are excluded
- __pycache__/ files are excluded
- dist/, build/, coverage/ are excluded
- Generated files (*.min.js, *.map, etc.) are excluded
- Valid Python/JS/TS source files are included
- Test files are properly classified
- Config files are properly classified
- Unsupported files are excluded
"""

import pytest
from backend.intelligence.engine.scanner.eligibility import FileEligibility, FileCategory


class TestFileEligibilityDirectoryExclusion:
    """Test that specified directories are excluded."""

    def test_next_directory_excluded(self):
        """Test that .next/ directory is excluded."""
        assert FileEligibility.classify_file("frontend/.next/dev/server/chunks/ssr/foo.js") == FileCategory.BUILD
        assert FileEligibility.classify_file("frontend/.next/build/file.json") == FileCategory.BUILD
        assert not FileEligibility.is_analyzable_as_source("frontend/.next/dev/server/chunks/ssr/foo.js")

    def test_node_modules_excluded(self):
        """Test that node_modules/ is excluded as dependency."""
        assert FileEligibility.classify_file("node_modules/package/index.js") == FileCategory.DEPENDENCY
        assert FileEligibility.classify_file("node_modules/deep/nested/package/lib/index.js") == FileCategory.DEPENDENCY
        assert not FileEligibility.is_analyzable_as_source("node_modules/package/index.js")

    def test_git_directory_excluded(self):
        """Test that .git/ is excluded."""
        assert FileEligibility.classify_file(".git/objects/abc123") == FileCategory.VCS
        assert FileEligibility.classify_file(".git/HEAD") == FileCategory.VCS
        assert not FileEligibility.is_analyzable_as_source(".git/objects/abc123")

    def test_pycache_excluded(self):
        """Test that __pycache__/ is excluded."""
        assert FileEligibility.classify_file("backend/__pycache__/module.cpython-39.pyc") == FileCategory.CACHE
        assert not FileEligibility.is_analyzable_as_source("backend/__pycache__/module.cpython-39.pyc")

    def test_pytest_cache_excluded(self):
        """Test that .pytest_cache/ is excluded."""
        assert FileEligibility.classify_file(".pytest_cache/v/cache/nodeids") == FileCategory.CACHE
        assert not FileEligibility.is_analyzable_as_source(".pytest_cache/v/cache/nodeids")

    def test_mypy_cache_excluded(self):
        """Test that .mypy_cache/ is excluded."""
        assert FileEligibility.classify_file(".mypy_cache/3.9/module.data.json") == FileCategory.CACHE
        assert not FileEligibility.is_analyzable_as_source(".mypy_cache/3.9/module.data.json")

    def test_ruff_cache_excluded(self):
        """Test that .ruff_cache/ is excluded."""
        assert FileEligibility.classify_file(".ruff_cache/cache_file") == FileCategory.CACHE
        assert not FileEligibility.is_analyzable_as_source(".ruff_cache/cache_file")

    def test_dist_excluded(self):
        """Test that dist/ is excluded as build output."""
        assert FileEligibility.classify_file("dist/bundle.js") == FileCategory.BUILD
        assert FileEligibility.classify_file("dist/deep/nested/file.js") == FileCategory.BUILD
        assert not FileEligibility.is_analyzable_as_source("dist/bundle.js")

    def test_build_excluded(self):
        """Test that build/ is excluded as build output."""
        assert FileEligibility.classify_file("build/output.o") == FileCategory.BUILD
        assert not FileEligibility.is_analyzable_as_source("build/output.o")

    def test_coverage_excluded(self):
        """Test that coverage/ is excluded."""
        assert FileEligibility.classify_file("coverage/index.html") == FileCategory.BUILD
        assert not FileEligibility.is_analyzable_as_source("coverage/index.html")

    def test_venv_excluded(self):
        """Test that venv/ and .venv/ are excluded."""
        assert FileEligibility.classify_file("venv/lib/python3.9/site-packages/module.py") in {FileCategory.DEPENDENCY, FileCategory.IGNORED}
        assert FileEligibility.classify_file(".venv/lib/python3.9/site-packages/module.py") in {FileCategory.DEPENDENCY, FileCategory.IGNORED}

    def test_ide_directories_excluded(self):
        """Test that IDE directories are excluded."""
        assert FileEligibility.classify_file(".vscode/settings.json") == FileCategory.IDE
        assert FileEligibility.classify_file(".idea/workspace.xml") == FileCategory.IDE

    def test_nested_directory_exclusion(self):
        """Test that exclusions work for nested paths."""
        assert FileEligibility.classify_file("backend/services/.next/app.js") == FileCategory.BUILD
        assert FileEligibility.classify_file("src/node_modules/lib.js") == FileCategory.DEPENDENCY


class TestFileEligibilitySourceFiles:
    """Test that valid source files are included."""

    def test_python_source_included(self):
        """Test that .py files are classified as source."""
        assert FileEligibility.classify_file("backend/models/user.py") == FileCategory.SOURCE
        assert FileEligibility.classify_file("app.py") == FileCategory.SOURCE
        assert FileEligibility.is_analyzable_as_source("backend/models/user.py")

    def test_javascript_source_included(self):
        """Test that .js/.jsx files are classified as source."""
        assert FileEligibility.classify_file("frontend/components/Button.js") == FileCategory.SOURCE
        assert FileEligibility.classify_file("frontend/pages/Home.jsx") == FileCategory.SOURCE
        assert FileEligibility.is_analyzable_as_source("frontend/components/Button.js")

    def test_typescript_source_included(self):
        """Test that .ts/.tsx files are classified as source."""
        assert FileEligibility.classify_file("frontend/types/index.ts") == FileCategory.SOURCE
        assert FileEligibility.classify_file("frontend/components/Card.tsx") == FileCategory.SOURCE
        assert FileEligibility.is_analyzable_as_source("frontend/types/index.ts")

    def test_go_source_included(self):
        """Test that .go files are classified as source."""
        assert FileEligibility.classify_file("services/handler.go") == FileCategory.SOURCE
        assert FileEligibility.is_analyzable_as_source("services/handler.go")

    def test_rust_source_included(self):
        """Test that .rs files are classified as source."""
        assert FileEligibility.classify_file("src/main.rs") == FileCategory.SOURCE
        assert FileEligibility.is_analyzable_as_source("src/main.rs")

    def test_java_source_included(self):
        """Test that .java files are classified as source."""
        assert FileEligibility.classify_file("src/main/java/Main.java") == FileCategory.SOURCE
        assert FileEligibility.is_analyzable_as_source("src/main/java/Main.java")


class TestFileEligibilityGeneratedFiles:
    """Test that generated files are excluded."""

    def test_minified_js_excluded(self):
        """Test that *.min.js files are classified as generated."""
        assert FileEligibility.classify_file("dist/app.min.js") == FileCategory.GENERATED
        assert FileEligibility.classify_file("frontend/lib/utils.min.js") == FileCategory.GENERATED
        assert not FileEligibility.is_analyzable_as_source("dist/app.min.js")

    def test_minified_css_excluded(self):
        """Test that *.min.css files are classified as generated."""
        assert FileEligibility.classify_file("dist/styles.min.css") == FileCategory.GENERATED
        assert not FileEligibility.is_analyzable_as_source("dist/styles.min.css")

    def test_source_maps_excluded(self):
        """Test that *.map files are classified as generated."""
        assert FileEligibility.classify_file("dist/app.js.map") == FileCategory.GENERATED
        assert FileEligibility.classify_file("app.min.css.map") == FileCategory.GENERATED
        assert not FileEligibility.is_analyzable_as_source("dist/app.js.map")

    def test_bundle_files_excluded(self):
        """Test that *.bundle.js files are classified as generated."""
        assert FileEligibility.classify_file("dist/main.bundle.js") == FileCategory.GENERATED
        assert not FileEligibility.is_analyzable_as_source("dist/main.bundle.js")

    def test_chunk_files_excluded(self):
        """Test that *.chunk.js files are classified as generated."""
        assert FileEligibility.classify_file("dist/chunk.123abc.js") == FileCategory.GENERATED
        assert FileEligibility.classify_file("frontend/.next/chunks/file.chunk.js") == FileCategory.GENERATED
        assert not FileEligibility.is_analyzable_as_source("dist/chunk.123abc.js")


class TestFileEligibilityConfigFiles:
    """Test that config/metadata files are properly classified."""

    def test_package_json_is_config(self):
        """Test that package.json is classified as config."""
        assert FileEligibility.classify_file("package.json") == FileCategory.CONFIG
        assert FileEligibility.classify_file("frontend/package.json") == FileCategory.CONFIG
        assert FileEligibility.is_analyzable_as_source("package.json")

    def test_pyproject_toml_is_config(self):
        """Test that pyproject.toml is classified as config."""
        assert FileEligibility.classify_file("pyproject.toml") == FileCategory.CONFIG
        assert FileEligibility.is_analyzable_as_source("pyproject.toml")

    def test_requirements_txt_is_config(self):
        """Test that requirements.txt is classified as config."""
        assert FileEligibility.classify_file("requirements.txt") == FileCategory.CONFIG
        assert FileEligibility.classify_file("requirements-dev.txt") == FileCategory.CONFIG
        assert FileEligibility.is_analyzable_as_source("requirements.txt")

    def test_tsconfig_is_config(self):
        """Test that tsconfig.json is classified as config."""
        assert FileEligibility.classify_file("tsconfig.json") == FileCategory.CONFIG
        assert FileEligibility.classify_file("tsconfig.base.json") == FileCategory.CONFIG
        assert FileEligibility.is_analyzable_as_source("tsconfig.json")

    def test_dockerfile_is_config(self):
        """Test that Dockerfile is classified as config."""
        assert FileEligibility.classify_file("Dockerfile") == FileCategory.CONFIG
        assert FileEligibility.is_analyzable_as_source("Dockerfile")

    def test_setup_py_is_config(self):
        """Test that setup.py is classified as config."""
        assert FileEligibility.classify_file("setup.py") == FileCategory.CONFIG
        assert FileEligibility.is_analyzable_as_source("setup.py")

    def test_next_config_is_config(self):
        """Test that next.config.js is classified as config."""
        assert FileEligibility.classify_file("next.config.js") == FileCategory.CONFIG
        assert FileEligibility.is_analyzable_as_source("next.config.js")


class TestFileEligibilityTestFiles:
    """Test that test files are properly classified."""

    def test_python_test_files(self):
        """Test that Python test files are classified as test."""
        assert FileEligibility.classify_file("tests/test_models.py") == FileCategory.TEST
        assert FileEligibility.classify_file("backend/tests/models_test.py") == FileCategory.TEST
        assert FileEligibility.is_analyzable_as_source("tests/test_models.py")

    def test_javascript_test_files(self):
        """Test that JS test files are classified as test."""
        assert FileEligibility.classify_file("frontend/components/__tests__/Button.test.js") == FileCategory.TEST
        assert FileEligibility.classify_file("src/utils.spec.js") == FileCategory.TEST
        assert FileEligibility.is_analyzable_as_source("frontend/components/__tests__/Button.test.js")

    def test_typescript_test_files(self):
        """Test that TS test files are classified as test."""
        assert FileEligibility.classify_file("src/utils.test.ts") == FileCategory.TEST
        assert FileEligibility.classify_file("__tests__/integration.spec.ts") == FileCategory.TEST
        assert FileEligibility.is_analyzable_as_source("src/utils.test.ts")


class TestFileEligibilityUnsupported:
    """Test that unsupported files are properly classified."""

    def test_unsupported_extensions(self):
        """Test that files with unsupported extensions are classified as unsupported."""
        assert FileEligibility.classify_file("README.txt") == FileCategory.UNSUPPORTED
        assert FileEligibility.classify_file("image.png") == FileCategory.UNSUPPORTED
        assert FileEligibility.classify_file("video.mp4") == FileCategory.UNSUPPORTED
        assert not FileEligibility.is_analyzable_as_source("image.png")

    def test_markdown_files_unsupported(self):
        """Test that .md files are unsupported (not parsed as code)."""
        # Note: .md is not in SOURCE_EXTENSIONS, so it's unsupported
        assert FileEligibility.classify_file("README.md") in {FileCategory.UNSUPPORTED, FileCategory.CONFIG}


class TestFileEligibilityEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_file_in_excluded_dir_stays_excluded(self):
        """Test that source files in excluded directories are still excluded."""
        # A .py file inside node_modules should still be excluded
        assert FileEligibility.classify_file("node_modules/package/index.py") == FileCategory.DEPENDENCY

        # A .js file inside .next should still be excluded
        assert FileEligibility.classify_file("frontend/.next/server/file.js") == FileCategory.BUILD

    def test_double_nested_exclusion(self):
        """Test that multiple levels of excluded directories are handled."""
        # Nested .next inside dist
        assert FileEligibility.classify_file("dist/.next/file.js") == FileCategory.BUILD

    def test_case_sensitivity(self):
        """Test that patterns are case-insensitive where appropriate."""
        # File extensions should be case-insensitive
        assert FileEligibility.classify_file("script.PY") == FileCategory.SOURCE
        assert FileEligibility.classify_file("script.Py") == FileCategory.SOURCE

    def test_hidden_files_in_source_dirs(self):
        """Test that hidden files in source directories are still analyzed."""
        # Hidden Python file in source directory should be analyzable
        assert FileEligibility.classify_file("backend/.hidden.py") == FileCategory.SOURCE
        assert FileEligibility.is_analyzable_as_source("backend/.hidden.py")

    def test_config_file_in_subdirectory(self):
        """Test that config files in subdirectories are still classified as config."""
        assert FileEligibility.classify_file("frontend/config/tsconfig.json") == FileCategory.CONFIG
        assert FileEligibility.is_analyzable_as_source("frontend/config/tsconfig.json")


class TestFileEligibilityStats:
    """Test the eligibility decision counts."""

    def test_gitignore_style_path(self):
        """Test that typical .gitignore-style paths work correctly."""
        # These should be excluded
        excluded = [
            ".next/dev/server/chunks/ssr/foo.js",
            "node_modules/package/index.js",
            ".git/HEAD",
            "__pycache__/module.cpython.pyc",
            "dist/bundle.js",
            "dist/app.min.js",
            "coverage/index.html",
        ]
        for path in excluded:
            assert not FileEligibility.is_analyzable_as_source(path), f"Expected {path} to be excluded"

        # These should be included
        included = [
            "backend/models.py",
            "frontend/components/Button.tsx",
            "package.json",
            "tests/test_app.py",
            "src/utils.test.ts",
        ]
        for path in included:
            assert FileEligibility.is_analyzable_as_source(path), f"Expected {path} to be included"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
