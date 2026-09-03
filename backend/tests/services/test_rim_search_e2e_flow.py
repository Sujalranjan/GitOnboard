"""
End-to-end integration test: Verify search_repository data flow to LLM.

Tests the complete boundary:
  User question
    ↓
  LLM search_repository call
    ↓
  Retriever: 5 results
    ↓
  Tool dispatch: data preserved
    ↓
  Sanitizer: data preserved
    ↓
  Formatter: file paths visible
    ↓
  LLM: receives usable information

This is the critical invariant that was previously broken.
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.repository_tools.tools import RepositoryToolLayer
from backend.services.rim_tool_dispatch import ToolDispatchTable
from backend.services.rim_qa_loop import RIMQALoop, SystemPromptParts
from backend.agent.loop.guardrails import LoopGuardrails
from backend.agent.loop.contracts import AgentLoopConfig, ToolObservation


@pytest.fixture
def test_repository():
    """Create a temporary test repository with authentication code."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create src directory
        src = root / "src"
        src.mkdir()

        # Create auth.py
        (src / "auth.py").write_text("""\"\"\"Authentication module.\"\"\"

def login(username, password):
    '''Handle user login with username and password.'''
    user = db.get_user(username)
    if user and user.verify_password(password):
        return generate_session_token(user.id)
    return None

def verify_password(stored_hash, provided):
    '''Verify password against stored hash.'''
    import hashlib
    return hashlib.sha256(provided.encode()).hexdigest() == stored_hash

def generate_session_token(user_id):
    '''Generate session token for authenticated user.'''
    import uuid
    return str(uuid.uuid4())
""")

        # Create login.py
        (src / "login.py").write_text("""\"\"\"Login endpoint handler.\"\"\"
from auth import login

def handle_login_request(request):
    '''HTTP handler for login requests.'''
    username = request.get('username')
    password = request.get('password')

    token = login(username, password)
    if token:
        return {'status': 'ok', 'token': token}
    return {'status': 'failed'}

def handle_logout_request(request):
    '''HTTP handler for logout requests.'''
    session_id = request.get('session_id')
    destroy_session(session_id)
    return {'status': 'ok'}
""")

        # Create session.py
        (src / "session.py").write_text("""\"\"\"Session management.\"\"\"

class SessionManager:
    '''Manages user sessions.'''

    def create_session(self, user_id):
        '''Create new session for user.'''
        pass

    def destroy_session(self, session_id):
        '''Destroy session.'''
        pass

def destroy_session(session_id):
    '''Destroy a session.'''
    mgr = SessionManager()
    mgr.destroy_session(session_id)
""")

        yield root


def test_search_repository_complete_flow(test_repository):
    """
    End-to-end test: "How does login work?"

    Verifies that search_repository data reaches LLM with usable information.
    """
    # Setup
    tool_layer = RepositoryToolLayer(
        repo_name="test",
        repo_root=test_repository,
        db=None,
        analysis_id=None
    )

    tool_dispatch = ToolDispatchTable(tool_layer)

    config = AgentLoopConfig(max_observation_bytes=8000)
    guardrails = LoopGuardrails(config)

    system_prompt_parts = SystemPromptParts(
        grounding_and_protocol_text="You are a code analyzer.",
        tool_catalog_text="Tools: search_repository, read_file",
        rim_metadata_text="",
        full_text="You are a code analyzer.\nTools: search_repository, read_file"
    )

    loop = RIMQALoop(
        llm_service=None,
        tool_dispatch=tool_dispatch,
        config=config,
        system_prompt_parts=system_prompt_parts
    )

    # Step 1: Call search_repository with "login" query
    # (This is what LLM would ask for "How does login work?")
    tool_observation = tool_dispatch.dispatch(
        "search_repository",
        {"query": "login", "limit": 10}
    )

    # Verify retriever found results
    assert tool_observation.success, "Retriever should find results"
    assert isinstance(tool_observation.data, list), "Data should be a list"
    assert len(tool_observation.data) > 0, "Should find login-related code"

    raw_count = len(tool_observation.data)
    print(f"Step 1 - Retriever: Found {raw_count} results")

    # Step 2: Sanitize observation (guards truncate large payloads)
    sanitized_data = guardrails.sanitize_observation(tool_observation.data)
    assert len(sanitized_data) == raw_count, "Sanitizer should preserve count"
    print(f"Step 2 - Sanitizer: {len(sanitized_data)} results preserved")

    # Step 3: Format for LLM (critical boundary that was previously broken)
    formatted_message = loop._format_tool_observation(
        "search_repository",
        tool_observation,
        sanitized_data
    )
    print(f"Step 3 - Formatter: Message length {len(formatted_message)}")

    # Verify formatted message is usable
    assert "[search_repository]" in formatted_message
    assert f"Found {raw_count} results" in formatted_message

    # CRITICAL INVARIANT: File paths must appear
    # (Previously they were all "?" because formatter looked for "path" key instead of "file")
    assert "auth.py" in formatted_message, \
        f"auth.py should appear in formatted message. Got:\n{formatted_message}"
    assert "login.py" in formatted_message or "login" in formatted_message, \
        f"login.py or login reference should appear. Got:\n{formatted_message}"

    # CRITICAL INVARIANT: Not all "?"
    assert "- ?" not in formatted_message, \
        f"Should not have placeholder results. Got:\n{formatted_message}"

    # CRITICAL INVARIANT: LLM-visible content bytes > 0
    llm_visible_bytes = len(formatted_message.encode("utf-8"))
    assert llm_visible_bytes > 100, \
        f"LLM should see {llm_visible_bytes} bytes of content (minimum 100)"

    print(f"Step 4 - LLM receives: {llm_visible_bytes} bytes of usable content")

    # Step 4: Verify LLM can act on this information
    # The formatted message would be appended to conversation, and LLM could now:
    # - Understand that login-related code was found
    # - Know which files to read_file from
    # - Continue the agentic loop
    can_find_auth = "auth" in formatted_message.lower()
    can_find_login = "login" in formatted_message.lower()
    assert can_find_auth or can_find_login, \
        "LLM should be able to identify relevant files from search results"

    print("✓ End-to-end flow successful: LLM can act on search_repository results")


def test_search_repository_invariant_nonzero_results():
    """
    Regression test for the critical invariant.

    If search_repository returns N > 0 results with content,
    then LLM-visible formatted output must also show N > 0 results with content.

    This invariant was violated when formatter looked for "path" key instead of "file".
    """
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        src = root / "src"
        src.mkdir()
        (src / "test.py").write_text("def test(): pass")
        (src / "demo.py").write_text("def demo(): pass")

        tool_layer = RepositoryToolLayer(repo_name="test", repo_root=root)
        tool_dispatch = ToolDispatchTable(tool_layer)
        config = AgentLoopConfig()
        system_prompt_parts = SystemPromptParts(
            grounding_and_protocol_text="Test",
            tool_catalog_text="Test",
            rim_metadata_text="",
            full_text="Test"
        )
        loop = RIMQALoop(
            llm_service=None,
            tool_dispatch=tool_dispatch,
            config=config,
            system_prompt_parts=system_prompt_parts
        )

        # Execute search
        observation = tool_dispatch.dispatch("search_repository", {"query": "test"})

        # Count raw results
        raw_count = len(observation.data)
        assert raw_count > 0, "Search should find results"

        # Format for LLM
        formatted = loop._format_tool_observation(
            "search_repository", observation, observation.data
        )

        # Count formatted results
        result_lines = [line for line in formatted.split("\n") if line.strip().startswith("- ")]
        formatted_count = len(result_lines)

        # INVARIANT: Must preserve result count
        assert formatted_count > 0, f"Formatted message should show results. Got:\n{formatted}"
        assert formatted_count >= min(raw_count, 10), \
            f"Formatter truncates >10 results, but should show first 10. " \
            f"Raw: {raw_count}, Formatted: {formatted_count}"

        # INVARIANT: No placeholder results
        for line in result_lines:
            assert "- ?" not in line, f"Should not have placeholder. Got:\n{formatted}"

        print(f"✓ Invariant preserved: {raw_count} results → {formatted_count} formatted results")
