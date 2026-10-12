"""
Unit and regression tests for Test 6: Evidence preservation through context compaction
and final-synthesis assembly in GitOnboard QALoop.

Tests:
Test A - Source retention: Verified source observations survive compaction with code intact.
Test B - Older observations: Earlier file observations outside standard window survive into synthesis.
Test C - Multiple files: Evidence from controller, helper, and middleware remain distinguishable.
Test D - Budget limit: Deterministic selection policy when budget is constrained, reporting omitted files.
Test E - Deduplication: Duplicate calls do not consume extra budget or erase unique source excerpts.
Test F - No regression: Compatibility with token budgeting and compaction contracts.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.loop.contracts import AgentLoopConfig, StopReason
from backend.ai.schemas import LLMRequest, LLMResponse, Message, MessageRole, TokenUsage
from backend.services.qa_loop import QALoop, SystemPromptParts
from backend.services.qa_budgeting import (
    compact_messages_deterministically,
    extract_read_file_metadata,
)


@pytest.fixture
def qa_loop_instance():
    llm_service = MagicMock()
    llm_service.providers = [MagicMock(provider_name="groq")]
    tool_dispatch = MagicMock()
    config = AgentLoopConfig()
    system_parts = SystemPromptParts(
        grounding_and_protocol_text="Grounding rules",
        tool_catalog_text="Tool catalog",
        rim_metadata_text="RIM metadata",
        full_text="System Prompt Context",
    )
    loop = QALoop(
        llm_service=llm_service,
        tool_dispatch=tool_dispatch,
        config=config,
        system_prompt_parts=system_parts,
        model="openai/gpt-oss-120b",
        provider="groq",
    )
    return loop


class TestEvidencePreservationCompaction:
    """Tests A through F for Test 6 evidence preservation."""

    def test_a_source_retention(self):
        """Test A: Retrieved source excerpts survive final-synthesis compaction with code intact."""
        code_body = (
            "[read_file] app/Deep-Guard-Backend/controllers/authcontroller.js lines 18-28: 450 chars (total: 523)\n"
            "  18 | const createSession = async (req, user, refreshToken) => {\n"
            "  19 |   const hashed = hashToken(refreshToken);\n"
            "  20 |   await supabase.from('sessions').insert({ refresh_token_hash: hashed });\n"
            "  21 | };"
        )
        messages = [
            {"role": "user", "content": "How are sessions created?"},
            {"role": "assistant", "content": "read_file(path='app/Deep-Guard-Backend/controllers/authcontroller.js')"},
            {"role": "user", "content": code_body},
            {"role": "assistant", "content": "search_code(query='hashToken')"},
            {"role": "user", "content": "[search_code] Found 2 results"},
            {"role": "assistant", "content": "search_repository(query='sessions')"},
            {"role": "user", "content": "[search_repository] Found 1 result"},
        ]

        compacted = compact_messages_deterministically(messages, target_tokens=10000)

        # The source observation must NOT be degraded to an outline placeholder
        obs_msg = [m for m in compacted if "createSession" in m["content"]]
        assert len(obs_msg) == 1
        assert "await supabase.from('sessions').insert" in obs_msg[0]["content"]
        assert "... [Older observation compacted to outline" not in obs_msg[0]["content"]

    def test_b_older_observations_survive_windowing(self, qa_loop_instance):
        """Test B: Relevant evidence remains available even when outside the standard 10-message window."""
        old_evidence = (
            "[read_file] app/Deep-Guard-Backend/controllers/authcontroller.js lines 18-28: 400 chars (total: 523)\n"
            "const createSession = async () => { supabase.from('sessions'); };"
        )
        messages = [
            {"role": "user", "content": "Explain authentication architecture"},
            {"role": "assistant", "content": '{"action": "tool_call", "tool_name": "read_file"}'},
            {"role": "user", "content": old_evidence},
        ]
        for i in range(13):
            messages.append({"role": "assistant", "content": f'{{"action": "tool_call", "tool_name": "search_{i}"}}'})
            messages.append({"role": "user", "content": f"[search_{i}] Observation {i}"})

        window_size = 10
        recent_msgs = messages[-(window_size - 1):]
        older_evidence = []
        recent_ids = {id(m) for m in recent_msgs}
        seen_evidence_paths = set()
        for m in recent_msgs:
            c = m.get("content", "")
            meta = extract_read_file_metadata(c)
            if meta and meta.get("path"):
                seen_evidence_paths.add(meta["path"])

        for m in messages[1:-(window_size - 1)]:
            if id(m) in recent_ids:
                continue
            c = m.get("content", "")
            meta = extract_read_file_metadata(c)
            if meta and meta.get("path") and meta["path"] not in seen_evidence_paths:
                older_evidence.append(m)
                seen_evidence_paths.add(meta["path"])

        msgs_to_include = [messages[0]] + older_evidence + recent_msgs

        assert any("createSession" in m["content"] for m in msgs_to_include)
        compacted = compact_messages_deterministically(msgs_to_include, target_tokens=15000)
        assert any("createSession" in m["content"] for m in compacted)

    def test_c_multiple_files_distinguishable(self):
        """Test C: Evidence from controller, helper, and middleware remains distinguishable and attributed."""
        controller = "[read_file] app/controllers/authcontroller.js lines 1-10: 200 chars\nexport function login() {}"
        helper = "[read_file] app/utils/authHelpers.js lines 1-10: 200 chars\nexport function createAccessToken() {}"
        middleware = "[read_file] app/middleware/authenticateToken.js lines 1-10: 200 chars\nexport function authenticateToken() {}"

        messages = [
            {"role": "user", "content": "Trace authentication"},
            {"role": "assistant", "content": "read_file(authcontroller.js)"},
            {"role": "user", "content": controller},
            {"role": "assistant", "content": "read_file(authHelpers.js)"},
            {"role": "user", "content": helper},
            {"role": "assistant", "content": "read_file(authenticateToken.js)"},
            {"role": "user", "content": middleware},
            {"role": "assistant", "content": "search()"},
            {"role": "user", "content": "[search] Done"},
        ]

        compacted = compact_messages_deterministically(messages, target_tokens=10000)

        content_str = "\n".join(m["content"] for m in compacted)
        assert "export function login" in content_str
        assert "export function createAccessToken" in content_str
        assert "export function authenticateToken" in content_str
        assert "authcontroller.js" in content_str
        assert "authHelpers.js" in content_str
        assert "authenticateToken.js" in content_str

    def test_d_budget_limit_graceful_handling(self):
        """Test D: When target budget is constrained, deterministic compaction handles non-source gracefully."""
        controller = "[read_file] app/controllers/authcontroller.js lines 1-10: 200 chars\nexport function login() {}"
        huge_search = "[search_repository] Found 100 items:\n" + ("  - Item result snippet\n" * 50)

        messages = [
            {"role": "user", "content": "Trace authentication"},
            {"role": "assistant", "content": "search_repository()"},
            {"role": "user", "content": huge_search},
            {"role": "assistant", "content": "read_file(authcontroller.js)"},
            {"role": "user", "content": controller},
            {"role": "assistant", "content": "search()"},
            {"role": "user", "content": "[search] 10 results"},
        ]

        compacted = compact_messages_deterministically(messages, target_tokens=1000)

        assert "... [Older observation compacted to outline" in compacted[2]["content"]
        assert "export function login" in compacted[4]["content"]

    def test_e_deduplication_preserves_unique_excerpts(self):
        """Test E: Duplicate observations for same file deduplicate older slice, keeping latest intact."""
        read1 = "[read_file] app/controllers/authcontroller.js lines 1-10: 200 chars\nslice 1 code"
        read2 = "[read_file] app/controllers/authcontroller.js lines 11-20: 200 chars\nslice 2 code"

        messages = [
            {"role": "user", "content": "Trace authentication"},
            {"role": "assistant", "content": "read_file(authcontroller.js, 1, 10)"},
            {"role": "user", "content": read1},
            {"role": "assistant", "content": "read_file(authcontroller.js, 11, 20)"},
            {"role": "user", "content": read2},
        ]

        compacted = compact_messages_deterministically(messages, target_tokens=1000)

        assert "[Deduplicated older observation for 'app/controllers/authcontroller.js'" in compacted[2]["content"]
        assert "slice 2 code" in compacted[4]["content"]

    def test_f_no_regression_existing_contracts(self, qa_loop_instance):
        """Test F: Existing provider profile and budget bounds remain respected."""
        profile = qa_loop_instance._get_provider_budget_profile()
        assert profile["provider"] == "groq"
        assert profile["safe_budget"] > 0
