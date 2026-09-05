"""
File Eligibility & Classification for Repository Analysis

Determines whether a file should be analyzed as source code or excluded as
dependency/generated/cache/build artifact.

Uses centralized classification logic to ensure consistent filtering.
"""

import re
from enum import Enum
from pathlib import Path
from typing import Optional, Set


class FileCategory(Enum):
    """Classification of files discovered during repository scanning."""
    SOURCE = "source"              # Developer-authored source code (.py, .js, .ts, etc.)
    CONFIG = "config"              # Configuration/metadata (package.json, pyproject.toml, etc.)
    TEST = "test"                  # Test files
    GENERATED = "generated"        # Generated/minified/compiled (.min.js, *.map, etc.)
    DEPENDENCY = "dependency"      # node_modules/, venv/, .eggs/, etc.
    BUILD = "build"                # Build output (dist/, build/, .next/, out/, etc.)
    CACHE = "cache"                # Caches (.pytest_cache/, .mypy_cache/, etc.)
    VCS = "vcs"                    # Version control (.git/)
    IDE = "ide"                    # IDE/editor files (.vscode/, .idea/, etc.)
    IGNORED = "ignored"            # Explicitly ignored
    UNSUPPORTED = "unsupported"    # File type not analyzable


class FileEligibility:
    """
    Centralized file eligibility decision-making.

    Determines whether a discovered file should be:
    - Analyzed as source code (SOURCE, CONFIG, TEST)
    - Skipped due to being dependency/build/generated
    - Classified for separate handling
    """

    # ====================
    # TIER 1: DIRECTORIES TO EXCLUDE (recursive)
    # ====================
    EXCLUDE_DIRS: Set[str] = {
        # Python
        ".venv", "venv", "env", ".env", ".venv", "ENV", ".Python",
        "__pycache__", ".pytest_cache", ".tox", ".nox", ".hypothesis",
        ".mypy_cache", ".dmypy.json", ".pyre", ".pytype",
        ".ruff_cache", "htmlcov", ".eggs",
        "site-packages", "dist-info", "egg-info",

        # JavaScript/Node
        "node_modules",
        ".next", ".nuxt", ".cache", ".parcel-cache",
        ".turbo", ".turbopack", ".webpack", ".babel-cache",
        ".rollup.cache", ".rts2_cache_*",
        ".eslintcache", ".stylelintcache", ".tsdist",
        ".jest", ".vitest", ".mocha",
        ".nyc_output", "coverage",
        "jest", "playwright-report", "blob-report", "test-results",

        # Build output
        "dist", "build", "out", "coverage", "htmlcov",
        "target", ".docusaurus", "_site", "_book", "site",
        ".vuepress",

        # IDE/Editors
        ".vscode", ".idea", ".vim", ".sublime-*",
        ".DS_Store",

        # Git
        ".git", ".github", ".gitignore",

        # CI/CD
        ".circleci", ".gitlab-ci", ".travis",

        # Lock files & package managers
        "node_modules",

        # Docker
        ".docker",
    }

    # ====================
    # TIER 2: GENERATED FILE PATTERNS
    # ====================
    GENERATED_PATTERNS: Set[str] = {
        r".*\.min\.js$",         # Minified JavaScript
        r".*\.min\.css$",        # Minified CSS
        r".*\.map$",             # Source maps
        r".*\.bundle\.js$",      # Bundled JS
        r".*\.chunk\.js$",       # Chunk files (*.chunk.js)
        r"^chunk\.[a-f0-9]+\.js$",  # Chunk files with hash (chunk.123abc.js)
        r".*\.bundle\.css$",     # Bundled CSS
        r".*\.bundle\.map$",     # Bundle source maps
    }

    # ====================
    # TIER 3: SOURCE FILE EXTENSIONS (must be in a valid directory)
    # ====================
    SOURCE_EXTENSIONS: Set[str] = {
        # Python
        ".py", ".pyi",
        # JavaScript/TypeScript
        ".js", ".jsx", ".mjs", ".cjs",
        ".ts", ".tsx", ".mts", ".cts",
        # Web
        ".html", ".css", ".scss", ".sass", ".less",
        # Other
        ".go", ".rs", ".java", ".cs", ".php", ".rb",
        ".c", ".cpp", ".h", ".hpp",
        ".sh", ".bash",
    }

    # ====================
    # TIER 4: CONFIG/METADATA FILES (allowed in any non-ignored directory)
    # ====================
    CONFIG_FILES: Set[str] = {
        # Python
        "setup.py", "setup.cfg", "pyproject.toml", "Pipfile",
        "requirements.txt", "requirements-dev.txt", "requirements-*.txt",
        "tox.ini", "pytest.ini", ".flake8", ".pylintrc",
        "mypy.ini", "black.toml", "isort.cfg", "poetry.lock",

        # JavaScript
        "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "tsconfig.json", "tsconfig.*.json",
        ".eslintrc.json", ".eslintrc.js", ".eslintrc.yaml", ".eslintrc.yml",
        ".prettierrc", ".prettierrc.json", ".prettierrc.yaml", ".prettierrc.yml",
        "jest.config.js", "vitest.config.js", "eslint.config.js",
        "babel.config.js", "webpack.config.js", "rollup.config.js",
        "vite.config.js", "next.config.js", "nuxt.config.js",
        ".editorconfig",

        # Docker
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".dockerignore",

        # General
        ".gitignore", ".gitattributes", ".gitmodules",
        "Makefile",
        ".github/workflows/*.yml", ".github/workflows/*.yaml",
        ".gitlab-ci.yml", ".circleci/config.yml", "Jenkinsfile",
        "azure-pipelines.yml",

        # Documentation
        "README.md", "CHANGELOG.md", "LICENSE", "LICENSE.md",
    }

    # ====================
    # TEST FILE PATTERNS
    # ====================
    TEST_PATTERNS: Set[str] = {
        r".*_test\.py$",
        r".*test_.*\.py$",
        r"test/.*\.py$",
        r"tests/.*\.py$",
        r".*\.test\.js$",
        r".*\.test\.ts$",
        r".*\.test\.jsx$",
        r".*\.test\.tsx$",
        r".*\.spec\.js$",
        r".*\.spec\.ts$",
        r".*\.spec\.jsx$",
        r".*\.spec\.tsx$",
        r"test/.*\.js$",
        r"tests/.*\.js$",
        r"__tests__/.*\.js$",
        r"__tests__/.*\.ts$",
    }

    @classmethod
    def classify_file(cls, rel_path: str) -> FileCategory:
        """
        Classify a file based on its path and characteristics.

        Args:
            rel_path: Relative file path from repository root

        Returns:
            FileCategory indicating how this file should be handled
        """
        path = Path(rel_path)

        # 1. Check if it's a generated file (BEFORE directory checks, since generated files are often in build dirs)
        if cls._is_generated_file(rel_path):
            return FileCategory.GENERATED

        # 2. Check if path is in an excluded directory
        parts = path.parts
        for part in parts:
            if cls._should_exclude_dir(part):
                # Determine which category of excluded
                if part in {"node_modules"}:
                    return FileCategory.DEPENDENCY
                elif part in {".git", ".github"}:
                    return FileCategory.VCS
                elif part in {".vscode", ".idea", ".vim", ".sublime-*"}:
                    return FileCategory.IDE
                elif cls._is_build_dir(part):
                    return FileCategory.BUILD
                elif cls._is_cache_dir(part):
                    return FileCategory.CACHE
                elif part == "__pycache__":
                    return FileCategory.CACHE
                else:
                    return FileCategory.IGNORED

        # 3. Check if it's a config file (by exact name match)
        if path.name in cls.CONFIG_FILES:
            return FileCategory.CONFIG

        # 4. Check if it's a config/metadata by pattern
        if cls._is_config_file_pattern(rel_path):
            return FileCategory.CONFIG

        # 5. Check if it's a test file
        if cls._is_test_file(rel_path):
            return FileCategory.TEST

        # 6. Check if it's a source file (by extension)
        if path.suffix.lower() in cls.SOURCE_EXTENSIONS:
            return FileCategory.SOURCE

        # 7. If it has no extension and is not a known file, it's unsupported
        if not path.suffix:
            return FileCategory.UNSUPPORTED

        # 8. Default: unsupported
        return FileCategory.UNSUPPORTED

    @classmethod
    def is_analyzable_as_source(cls, rel_path: str) -> bool:
        """
        Determine if a file should be parsed/analyzed as source code.

        Returns True only for SOURCE, CONFIG, and TEST files in non-ignored directories.
        """
        category = cls.classify_file(rel_path)
        return category in {FileCategory.SOURCE, FileCategory.CONFIG, FileCategory.TEST}

    @classmethod
    def _should_exclude_dir(cls, dir_name: str) -> bool:
        """Check if a directory component should be excluded."""
        if dir_name in cls.EXCLUDE_DIRS:
            return True
        # Handle wildcard patterns like .rts2_cache_*
        for pattern in cls.EXCLUDE_DIRS:
            if "*" in pattern:
                regex = pattern.replace("*", ".*").replace(".", r"\.")
                if re.match(f"^{regex}$", dir_name):
                    return True
        return False

    @classmethod
    def _is_generated_file(cls, rel_path: str) -> bool:
        """Check if file matches generated file patterns."""
        path = Path(rel_path)
        filename = path.name

        # Check all patterns
        for pattern in cls.GENERATED_PATTERNS:
            if re.match(pattern, rel_path.lower()):
                return True

        # Check filename-level patterns
        if re.match(r"^chunk\.[a-f0-9]+\.js$", filename):
            return True

        return False

    @classmethod
    def _is_test_file(cls, rel_path: str) -> bool:
        """Check if file matches test file patterns."""
        for pattern in cls.TEST_PATTERNS:
            if re.match(pattern, rel_path):
                return True
        return False

    @classmethod
    def _is_build_dir(cls, dir_name: str) -> bool:
        """Check if directory is a build output directory."""
        build_dirs = {"dist", "build", "out", "coverage", "htmlcov", "target",
                      ".docusaurus", "_site", "_book", "site", ".vuepress",
                      ".next", ".nuxt"}
        return dir_name in build_dirs

    @classmethod
    def _is_cache_dir(cls, dir_name: str) -> bool:
        """Check if directory is a cache directory."""
        cache_dirs = {".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache",
                      ".parcel-cache", ".turbo", ".turbopack", ".webpack",
                      ".babel-cache", ".rollup.cache", ".eslintcache",
                      ".stylelintcache", ".tsdist", ".jest", ".vitest",
                      ".mocha", ".nyc_output", ".hypothesis", "jest",
                      "playwright-report", "blob-report", "test-results",
                      "__pycache__"}
        return dir_name in cache_dirs

    @classmethod
    def _is_config_file_pattern(cls, rel_path: str) -> bool:
        """Check if file matches config file patterns."""
        path = Path(rel_path)

        # Exact filename matches
        if path.name in cls.CONFIG_FILES:
            return True

        # tsconfig.*.json pattern
        if path.name.startswith("tsconfig.") and path.name.endswith(".json"):
            return True

        # requirements-*.txt pattern
        if path.name.startswith("requirements-") and path.name.endswith(".txt"):
            return True

        # .eslintrc.* pattern
        if path.name.startswith(".eslintrc"):
            return True

        # .prettierrc.* pattern
        if path.name.startswith(".prettierrc"):
            return True

        # .github/workflows/*.yml pattern
        if ".github/workflows/" in rel_path and rel_path.endswith((".yml", ".yaml")):
            return True

        return False

    @classmethod
    def _matches_any_pattern(cls, path: str, patterns: Set[str]) -> bool:
        """Check if path matches any pattern in the set."""
        for pattern in patterns:
            if "*" in pattern:
                regex = pattern.replace("*", ".*").replace(".", r"\.")
                if re.match(f"^.*{regex}$", path):
                    return True
        return False
