"""
Example usage of Phase 2L inspection tools.
Shows how to use all 5 tools with real repository files.
"""
from pathlib import Path

from backend.intelligence.inspection import (
    inspect_file,
    inspect_symbol,
    read_symbol,
    read_lines,
    read_file,
)


def example_filesystem_mode():
    """
    Example 1: Using tools with filesystem (no database).
    Works with any worktree or repository on disk.
    """
    print("=" * 60)
    print("EXAMPLE 1: Filesystem Mode (no database)")
    print("=" * 60)

    # Find a Python file to inspect
    repo_root = Path("/home/dheeraj/repository_intelligence_platform/data/worktrees/GitOnboard")
    if not repo_root.exists():
        print("GitOnboard worktree not available, skipping filesystem example")
        return

    test_file = "backend/main.py"
    print(f"\nInspecting file: {test_file}")

    # Tool 1: inspect_file() - Get structure without reading full source
    print("\n1. inspect_file() - Get file structure")
    result = inspect_file(
        file_path=test_file,
        repo_root=str(repo_root),
    )
    if result.success:
        print(f"   File: {result.file_path}")
        print(f"   Language: {result.language}")
        print(f"   Total lines: {result.total_lines}")
        print(f"   File size: {result.file_size_kb} KB")
        print(f"   Symbols: {len(result.symbols)}")
        for sym in result.symbols[:3]:  # Show first 3
            print(f"      - {sym.name} ({sym.symbol_type}) @ lines {sym.line_start}-{sym.line_end}")
    else:
        print(f"   Error: {result.error}")

    # Tool 5: read_file() - Read entire file
    print("\n5. read_file() - Read entire file")
    result = read_file(
        file_path=test_file,
        repo_root=str(repo_root),
    )
    if result.success:
        print(f"   Read {result.total_lines} lines")
        print(f"   Estimated tokens: {result.estimated_tokens}")
        # Show first 10 lines
        lines = result.raw_text.split('\n')[:10]
        for i, line in enumerate(lines, 1):
            print(f"   {i:3d} | {line}")
    else:
        print(f"   Error: {result.error}")

    # Tool 4: read_lines() - Read specific line range
    print("\n4. read_lines() - Read lines 1-20")
    result = read_lines(
        file_path=test_file,
        start_line=1,
        end_line=20,
        repo_root=str(repo_root),
    )
    if result.success:
        print(f"   Read lines {result.line_start}-{result.line_end}")
        print(f"   Estimated tokens: {result.estimated_tokens}")
    else:
        print(f"   Error: {result.error}")


def example_with_database():
    """
    Example 2: Using tools with database (requires analysis).
    Demonstrates full functionality with symbol resolution.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Database Mode (with symbol resolution)")
    print("=" * 60)
    print("\nNote: Requires active database session and analysis_id")
    print("This would be used with:")
    print("  - from backend.database import SessionLocal")
    print("  - db = SessionLocal()")
    print("  - result = inspect_symbol('backend/app.py', 'func_name', db=db)")

    print("\nExample database-mode code:")
    print("""
from backend.database import SessionLocal
from backend.intelligence.inspection import inspect_symbol, read_symbol

db = SessionLocal()

# Tool 2: inspect_symbol() - Get metadata about a symbol
result = inspect_symbol(
    file_path="backend/app.py",
    symbol_name="create_app",
    db=db,
    repo_name="GitOnboard",
)

if result.success:
    print(f"Symbol: {result.qualified_name}")
    print(f"Type: {result.symbol_type}")
    print(f"Lines: {result.line_start}-{result.line_end}")
    print(f"Calls: {len(result.relationships.calls)}")
    print(f"Called by: {len(result.relationships.called_by)}")
else:
    print(f"Error: {result.error}")

# Tool 3: read_symbol() - Read exact source of symbol
result = read_symbol(
    file_path="backend/app.py",
    symbol_name="create_app",
    db=db,
    repo_name="GitOnboard",
)

if result.success:
    print(f"Symbol source ({result.line_start}-{result.line_end}):")
    print(result.source)
else:
    print(f"Error: {result.error}")

db.close()
    """)


def example_language_detection():
    """
    Example 3: Language detection for different file types.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Language Detection")
    print("=" * 60)

    from backend.intelligence.inspection.utils import detect_language

    test_files = [
        "main.py",
        "index.js",
        "app.ts",
        "Button.jsx",
        "App.tsx",
        "README.md",
    ]

    for filename in test_files:
        lang = detect_language(filename)
        print(f"   {filename:20s} → {lang}")


def example_error_handling():
    """
    Example 4: Error handling for edge cases.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Error Handling")
    print("=" * 60)

    repo_root = Path("/home/dheeraj/repository_intelligence_platform/data/worktrees/GitOnboard")
    if not repo_root.exists():
        print("GitOnboard worktree not available, skipping error example")
        return

    # Error 1: File not found
    print("\n1. File not found")
    result = read_file(
        file_path="nonexistent/file.py",
        repo_root=str(repo_root),
    )
    print(f"   Success: {result.success}")
    print(f"   Error: {result.error}")

    # Error 2: Invalid line numbers
    print("\n2. Invalid line numbers")
    result = read_lines(
        file_path="backend/main.py",
        start_line=0,  # Invalid: must be >= 1
        end_line=10,
        repo_root=str(repo_root),
    )
    print(f"   Success: {result.success}")
    print(f"   Error: {result.error}")

    # Error 3: Reversed line range
    print("\n3. Reversed line range")
    result = read_lines(
        file_path="backend/main.py",
        start_line=20,
        end_line=10,  # Invalid: end < start
        repo_root=str(repo_root),
    )
    print(f"   Success: {result.success}")
    print(f"   Error: {result.error}")


def example_token_estimation():
    """
    Example 5: Token estimation for code.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Token Estimation")
    print("=" * 60)

    from backend.intelligence.inspection.utils import estimate_tokens

    code_samples = [
        ("def foo():\n    pass", "Simple function"),
        ("x = 1\ny = 2\nz = x + y", "Simple math"),
        ("x" * 400, "400 characters"),
    ]

    for code, description in code_samples:
        tokens = estimate_tokens(code)
        chars = len(code)
        print(f"   {description:20s}: {chars:4d} chars → ~{tokens} tokens")


if __name__ == "__main__":
    print("Phase 2L Inspection Tools - Usage Examples\n")

    example_filesystem_mode()
    example_language_detection()
    example_error_handling()
    example_token_estimation()
    example_with_database()

    print("\n" + "=" * 60)
    print("Documentation: backend/intelligence/inspection/INSPECTION_TOOLS.md")
    print("Tests: backend/tests/unit/test_inspection_tools.py")
    print("=" * 60)
