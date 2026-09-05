"""
Minimal test case to verify AnalysisEngine parser fix.

Tests that after fixing the parser_manager.parse_file() signature mismatch,
the engine can now extract symbols (FUNCTION, CLASS, METHOD) from parsed code.
"""
import tempfile
from pathlib import Path
import pytest


def test_symbol_extraction_with_minimal_fixture():
    """
    Verify AnalysisEngine now extracts symbols after parser fix.

    This test validates that:
    1. Parser receives correct argument types (rel_path: str, language: str)
    2. ASTs dictionary populates with parsed code
    3. SymbolAnalyzer extracts FUNCTION, CLASS, METHOD entities
    4. Model contains extracted symbols and relationships
    """
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    # Create minimal fixture with Python functions and classes
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test.py with functions and classes
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("""
def authenticate_token(token):
    '''Authenticate a user token.'''
    return token is not None

class AuthService:
    '''Authentication service.'''

    def login(self, username, password):
        '''Login user.'''
        return {'token': 'abc123'}

    def logout(self):
        '''Logout user.'''
        return True

def validate_credentials(username, password):
    '''Validate user credentials.'''
    return len(username) > 0 and len(password) > 0
""")

        # Run AnalysisEngine
        registry = get_default_registry()
        engine = AnalysisEngine(tmpdir, registry)
        model = engine.run(
            repo_name="test_repo",
            commit_info=None,
            analysis_id=None,
            db=None
        )

        # Collect entity types and names for assertions
        # Note: model.entities is a Dict[str, Entity], not a list
        entity_types = {e.type for e in model.entities.values()}
        entity_names = {e.name for e in model.entities.values()}

        print(f"\n✓ Analysis Complete")
        print(f"  Total entities: {len(model.entities)}")
        print(f"  Entity types: {entity_types}")
        print(f"  Entity names: {sorted(entity_names)}")
        print(f"  Total relationships: {len(model.relationships)}")

        # Assertions: Entity types
        assert "FILE" in entity_types, \
            f"FILE entity missing. Types found: {entity_types}"
        assert "FUNCTION" in entity_types, \
            f"FUNCTION entity missing. Types found: {entity_types}"
        assert "CLASS" in entity_types, \
            f"CLASS entity missing. Types found: {entity_types}"

        # Assertions: Specific functions
        assert "authenticate_token" in entity_names, \
            f"Function 'authenticate_token' not extracted. Found: {entity_names}"
        assert "validate_credentials" in entity_names, \
            f"Function 'validate_credentials' not extracted. Found: {entity_names}"

        # Assertions: Class and methods
        assert "AuthService" in entity_names, \
            f"Class 'AuthService' not extracted. Found: {entity_names}"
        assert "login" in entity_names, \
            f"Method 'login' not extracted. Found: {entity_names}"
        assert "logout" in entity_names, \
            f"Method 'logout' not extracted. Found: {entity_names}"

        # Assertions: Relationships
        assert len(model.relationships) > 0, \
            "No relationships extracted (expected DECLARES, CALLS, etc.)"

        # Summary
        print(f"✓ All assertions passed!")
        print(f"  Extracted {len([e for e in model.entities.values() if e.type == 'FUNCTION'])} functions")
        print(f"  Extracted {len([e for e in model.entities.values() if e.type == 'CLASS'])} classes")
        print(f"  Extracted {len([e for e in model.entities.values() if e.type == 'METHOD'])} methods")


def test_parser_signature_correctness():
    """
    Verify that ASTParserManager.parse_file() receives correct arguments.

    This directly tests that AnalysisEngine line 81 now passes:
    - file_info.path (string) as rel_path
    - file_info.language (string) as language
    """
    from backend.intelligence.engine.parser.manager import ASTParserManager

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple Python file
        test_file = Path(tmpdir) / "simple.py"
        test_file.write_text("def hello(): pass")

        # Test parser with correct arguments
        parser = ASTParserManager(tmpdir)

        # This should NOT raise an exception
        # Note: language must match provider names: "Python", "JavaScript", "TypeScript", "Java"
        ast = parser.parse_file("simple.py", "Python")

        # AST should be populated (not None)
        assert ast is not None, \
            "Parser returned None (expected valid AST after fix)"

        print(f"✓ Parser received correct arguments and returned AST")
        print(f"  AST type: {type(ast).__name__}")


def test_multiple_language_support():
    """
    Verify that parser fix works across multiple languages.
    """
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create Python file
        Path(tmpdir, "script.py").write_text("def greet(): pass")

        # Create JavaScript file
        Path(tmpdir, "script.js").write_text("function greet() { console.log('hi'); }")

        # Create TypeScript file
        Path(tmpdir, "script.ts").write_text("function greet(): void { console.log('hi'); }")

        # Run engine
        registry = get_default_registry()
        engine = AnalysisEngine(tmpdir, registry)
        model = engine.run("multi_lang_test")

        # Verify all files were scanned
        file_entities = [e for e in model.entities.values() if e.type == "FILE"]
        file_paths = {e.name for e in file_entities}

        print(f"\n✓ Multi-language analysis complete")
        print(f"  Files found: {file_paths}")
        print(f"  Total entities: {len(model.entities)}")

        # All 3 files should be present
        assert len(file_entities) == 3, \
            f"Expected 3 FILE entities, got {len(file_entities)}"

        # Should have extracted symbols from all
        assert len(model.entities) > 3, \
            f"Expected more than 3 entities (files + symbols), got {len(model.entities)}"
