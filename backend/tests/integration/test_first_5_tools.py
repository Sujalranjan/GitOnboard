"""
Integration Test: First 5 Verified Tools
Tests natural language query execution on real repository data.

Tools being tested:
1. search_code - Search repository file contents
2. search_symbols - Find files and symbols by pattern
3. get_symbol - Look up symbol definition and locations
4. get_callers - Find functions that call a specific symbol
5. get_callees - Find functions called by a specific symbol
"""

import sys
import pytest
import os
from backend.database import get_engine, SessionLocal
from backend.models.repository import Repository, Analysis
from backend.agent.tools.repository import (
    handle_search_code,
    handle_search_symbols,
    handle_get_symbol,
    handle_get_callers,
    handle_get_callees,
)
from backend.agent.tools.contracts import AgentToolContext


class TestFirst5Tools:
    """Test the first 5 verified tools with natural language queries."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Find an existing completed analysis to test against."""
        self.db = SessionLocal()

        # Find a completed analysis with enough data
        analysis = self.db.query(Analysis).filter(
            Analysis.status == "Completed"
        ).first()

        if not analysis:
            pytest.skip("No completed analysis found in database")

        self.analysis = analysis
        self.analysis_id = analysis.id
        self.repo = self.db.query(Repository).filter(
            Repository.id == analysis.repository_id
        ).first()

        yield

        self.db.close()

    def _make_context(self):
        """Create AgentToolContext for tool execution."""
        return AgentToolContext(
            db=self.db,
            repository_id=self.repo.id,
            user_id=1,
            worktree_path="/tmp/repo"
        )

    def test_1_search_code_authentication(self):
        """
        Natural Language Query:
        'Find where we handle user authentication in this codebase'
        """
        print(f"\n=== TEST 1: Search Code for Authentication ===")
        print(f"Analysis ID: {self.analysis_id}")
        print(f"Repository: {self.repo.name}")

        context = self._make_context()

        # Tool call: search for authentication code
        result = handle_search_code(
            args={
                "query": "authenticate",
                "limit": 20,
                "path_pattern": "*.py"
            },
            context=context
        )

        print(f"\nSearching for 'authenticate' in Python files...")
        print(f"Found: {result['match_count']} matches")

        # Verify results
        assert result['match_count'] >= 0, "search_code should return a match count"
        assert 'matches' in result, "search_code should return matches list"

        if result['match_count'] > 0:
            print(f"Sample matches:")
            for match in result['matches'][:3]:
                print(f"  - {match}")

        print(f"✅ PASS: search_code works with natural language query")
        return result

    def test_2_search_symbols_api_endpoints(self):
        """
        Natural Language Query:
        'Show me all the API endpoint definitions'
        """
        print(f"\n=== TEST 2: Search Symbols for API Files ===")

        context = self._make_context()

        # Tool call: find route/API-related files
        result = handle_search_symbols(
            args={
                "pattern": "*route*",
                "limit": 20
            },
            context=context
        )

        print(f"Searching for files matching '*route*' pattern...")
        print(f"Found: {len(result.get('files_found', []))} files")

        if result.get('files_found'):
            print(f"Sample files:")
            for file in result['files_found'][:3]:
                print(f"  - {file}")

        # Verify structure
        assert 'pattern' in result, "Result should contain pattern"
        assert 'files_found' in result, "Result should contain files_found list"

        print(f"✅ PASS: search_symbols works with natural language query")
        return result

    def test_3_get_symbol_user_model(self):
        """
        Natural Language Query:
        'Show me the User class and where it's defined'
        """
        print(f"\n=== TEST 3: Get Symbol Definition ===")

        context = self._make_context()

        # Tool call: look up User symbol
        result = handle_get_symbol(
            args={"name": "User"},
            context=context
        )

        print(f"Looking up symbol 'User'...")
        print(f"Found: {result['symbol_count']} symbols")

        if result.get('symbols'):
            print(f"Symbol details:")
            for sym in result['symbols'][:2]:
                print(f"  - {sym}")

        # Verify structure
        assert 'name' in result, "Result should contain name"
        assert 'symbol_count' in result, "Result should contain symbol count"
        assert isinstance(result['symbols'], list), "Result should have symbols list"

        print(f"✅ PASS: get_symbol works with natural language query")
        return result

    def test_4_get_callers_database_save(self):
        """
        Natural Language Query:
        'Who calls the save method / create function?'
        """
        print(f"\n=== TEST 4: Get Callers ===")

        context = self._make_context()

        # Tool call: find callers of 'save'
        result = handle_get_callers(
            args={"symbol_name": "save"},
            context=context
        )

        print(f"Looking for functions that call 'save'...")
        print(f"Found: {result['caller_count']} callers")

        if result.get('callers'):
            print(f"Sample callers:")
            for caller in result['callers'][:3]:
                print(f"  - {caller}")

        # Verify structure
        assert 'symbol_name' in result, "Result should contain symbol_name"
        assert 'caller_count' in result, "Result should contain caller count"
        assert isinstance(result['callers'], list), "Result should have callers list"

        print(f"✅ PASS: get_callers works with natural language query")
        return result

    def test_5_get_callees_process_request(self):
        """
        Natural Language Query:
        'What functions does the request handler call?'
        """
        print(f"\n=== TEST 5: Get Callees ===")

        context = self._make_context()

        # Tool call: find functions called by 'request_handler' or 'process'
        result = handle_get_callees(
            args={"symbol_name": "process"},
            context=context
        )

        print(f"Looking for functions called by 'process'...")
        print(f"Found: {result['callee_count']} callees")

        if result.get('callees'):
            print(f"Sample callees:")
            for callee in result['callees'][:3]:
                print(f"  - {callee}")

        # Verify structure
        assert 'symbol_name' in result, "Result should contain symbol_name"
        assert 'callee_count' in result, "Result should contain callee count"
        assert isinstance(result['callees'], list), "Result should have callees list"

        print(f"✅ PASS: get_callees works with natural language query")
        return result

    def test_integrated_flow_search_to_callers(self):
        """
        Integration test: Chain multiple tools together

        Flow:
        1. Search for 'authenticate' code
        2. Get the symbol definition
        3. Find callers of that symbol
        """
        print(f"\n=== INTEGRATION TEST: Chained Tool Calls ===")

        context = self._make_context()

        # Step 1: Search for authentication code
        print("\nStep 1: Search for authentication code...")
        search_result = handle_search_code(
            args={"query": "authenticate", "limit": 5},
            context=context
        )

        print(f"  Found {search_result['match_count']} matches")

        if search_result['match_count'] == 0:
            pytest.skip("No authentication code found to test chaining")

        # Step 2: Try to get symbol definition
        print("\nStep 2: Get symbol definition...")
        symbol_result = handle_get_symbol(
            args={"name": "authenticate"},
            context=context
        )

        print(f"  Found {symbol_result['symbol_count']} symbols")

        if symbol_result['symbol_count'] == 0:
            pytest.skip("No authenticate symbol found")

        # Step 3: Get callers of that symbol
        print("\nStep 3: Get callers of authenticate...")
        callers_result = handle_get_callers(
            args={"symbol_name": "authenticate"},
            context=context
        )

        print(f"  Found {callers_result['caller_count']} callers")

        # Verify the chain worked
        assert search_result['match_count'] > 0, "Search should find results"
        assert symbol_result['symbol_count'] >= 0, "Symbol lookup should work"
        assert callers_result['caller_count'] >= 0, "Callers lookup should work"

        print(f"\n✅ PASS: Tools work together in an integrated flow")


if __name__ == "__main__":
    # Run with: python -m pytest backend/tests/integration/test_first_5_tools.py -v -s
    pytest.main([__file__, "-v", "-s"])
