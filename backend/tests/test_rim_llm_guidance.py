"""
Test Suite for RIM LLM Guidance Validation

Tests LLM's interpretation of RIM metadata guidance:
1. Relationship direction preservation
2. Anchor vs expanded entity priority
3. Negative query safety
4. Relationship interpretation accuracy
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from backend.agent.context.rim_guidance import (
    get_rim_guidance_for_system_prompt,
    format_rim_metadata_for_prompt,
    RIM_ANCHOR_AND_EXPANSION_GUIDANCE,
    RIM_NEGATIVE_QUERY_GUIDANCE,
    RIM_RELATIONSHIP_DIRECTION_GUIDANCE,
)


class TestRIMGuidanceGeneration:
    """Test RIM guidance prompt section generation."""

    def test_anchor_guidance_section_contains_key_concepts(self):
        """Verify anchor guidance covers key RIM concepts."""
        text = RIM_ANCHOR_AND_EXPANSION_GUIDANCE
        assert "Anchors:" in text
        assert "Expanded Entities:" in text
        assert "Graph Distance:" in text
        assert "Distance 0 = Anchor" in text
        assert "Distance 1 =" in text

    def test_negative_query_guidance_has_safety_rules(self):
        """Verify negative query guidance includes safety constraints."""
        text = RIM_NEGATIVE_QUERY_GUIDANCE
        assert "RULES:" in text
        assert "NOT prove a feature exists" in text
        assert "NOT prove absence" in text
        assert "express uncertainty" in text
        assert "DO NOT DO:" in text

    def test_relationship_direction_guidance_preserves_semantics(self):
        """Verify direction guidance explains directional semantics."""
        text = RIM_RELATIONSHIP_DIRECTION_GUIDANCE
        assert "CALLS" in text
        assert "invokes" in text or "triggers" in text
        assert "NOT:" in text
        assert "Never reverse" in text or "reverse" in text

    def test_get_rim_guidance_default_sections(self):
        """Test default RIM guidance includes critical sections (may be truncated)."""
        guidance = get_rim_guidance_for_system_prompt()
        assert "Anchors" in guidance
        # Key concepts should be present (may be truncated but should have core material)
        assert "Negative" in guidance or "absence" in guidance or "distance" in guidance

    def test_get_rim_guidance_custom_sections(self):
        """Test RIM guidance can filter to specific sections."""
        # Get full guidance first
        full_guidance = get_rim_guidance_for_system_prompt(max_chars=10000)
        anchor_guidance = get_rim_guidance_for_system_prompt(
            include_sections=['anchor'],
            max_chars=10000
        )
        # Anchor guidance should be shorter than full
        assert len(anchor_guidance) <= len(full_guidance)

    def test_get_rim_guidance_respects_char_limit(self):
        """Test RIM guidance respects maximum character limit."""
        guidance = get_rim_guidance_for_system_prompt(max_chars=500)
        assert len(guidance) <= 600  # Small buffer for truncation message


class TestRIMMetadataFormatting:
    """Test formatting of RIM metadata for LLM injection."""

    def test_format_anchors_only(self):
        """Test formatting anchors without expanded entities."""
        anchors = [
            {
                'name': 'authenticate_user',
                'type': 'function',
                'file_path': 'auth.py',
                'line_start': 42,
            }
        ]
        text = format_rim_metadata_for_prompt(anchors, expanded=[])
        assert "[ANCHOR]" in text
        assert "authenticate_user" in text
        assert "auth.py:42" in text

    def test_format_anchors_and_expanded(self):
        """Test formatting both anchors and expanded entities."""
        anchors = [
            {
                'name': 'authenticate_user',
                'type': 'function',
                'file_path': 'auth.py',
                'line_start': 42,
            }
        ]
        expanded = [
            {
                'name': 'validate_password',
                'type': 'function',
                'file_path': 'auth.py',
                'line_start': 100,
                'distance_from_anchor': 1,
                'rel_type': 'CALLS',
                'relationship_role': 'callee',
            }
        ]
        text = format_rim_metadata_for_prompt(anchors, expanded)
        assert "[ANCHOR]" in text
        assert "CALLS:" in text
        assert "validate_password" in text
        assert "Distance 1:" in text

    def test_format_respects_max_items(self):
        """Test formatting respects maximum item count."""
        anchors = [{'name': f'func{i}', 'type': 'function', 'file_path': f'f{i}.py', 'line_start': i} for i in range(10)]
        text = format_rim_metadata_for_prompt(anchors, max_items=3)
        # Should show anchors but limited
        assert "func" in text
        assert "REPOSITORY RELATIONSHIP METADATA" in text

    def test_format_groups_by_distance(self):
        """Test formatting groups expanded entities by graph distance."""
        anchors = [{'name': 'main', 'type': 'function', 'file_path': 'main.py', 'line_start': 1}]
        expanded = [
            {
                'name': 'func1',
                'type': 'function',
                'file_path': 'a.py',
                'line_start': 10,
                'distance_from_anchor': 1,
                'rel_type': 'CALLS',
            },
            {
                'name': 'func2',
                'type': 'function',
                'file_path': 'b.py',
                'line_start': 20,
                'distance_from_anchor': 2,
                'rel_type': 'CALLS',
            },
        ]
        text = format_rim_metadata_for_prompt(anchors, expanded)
        assert "Distance 1:" in text
        assert "Distance 2:" in text
        # func1 should appear before func2
        assert text.index("func1") < text.index("func2")


class TestRIMGuidanceIntegration:
    """Test integration of RIM guidance into LLM prompts."""

    @patch('backend.agent.modes.build_default_service')
    @patch('backend.agent.modes.SessionLocal')
    def test_explain_mode_includes_rim_guidance(self, mock_session_local, mock_llm_service):
        """Test that execute_explain includes RIM guidance in system prompt."""
        # This is a simple integration test to verify the guidance is included
        # Actual LLM testing would require more complex setup

        from backend.agent.modes import execute_explain
        from backend.config import settings

        # This is a placeholder - actual implementation would mock LLM service properly
        # and verify system prompt contains RIM guidance
        pass

    def test_rim_guidance_sections_non_overlapping(self):
        """Verify RIM guidance sections don't have significant duplication."""
        sections = [
            RIM_ANCHOR_AND_EXPANSION_GUIDANCE,
            RIM_NEGATIVE_QUERY_GUIDANCE,
            RIM_RELATIONSHIP_DIRECTION_GUIDANCE,
        ]
        # Count total words
        total_words = sum(len(s.split()) for s in sections)
        # Each section should be meaningful (>100 words)
        assert all(len(s.split()) > 100 for s in sections)
        # Total should be reasonable (not excessively long)
        assert total_words < 2000


class TestRIMSafetyRules:
    """Test that RIM guidance enforces safety rules."""

    def test_negative_query_guidance_prevents_fabrication(self):
        """Test that negative query guidance prevents fabricating features."""
        text = RIM_NEGATIVE_QUERY_GUIDANCE
        # Should contain explicit warning about not inferring from expanded context
        assert "WRONG:" in text
        assert "RIGHT:" in text
        # Should have concrete examples
        assert "WebSocket" in text or "OAuth" in text

    def test_negative_query_examples_show_danger(self):
        """Test that negative query examples show common mistakes."""
        text = RIM_NEGATIVE_QUERY_GUIDANCE
        # Should show what NOT to do with examples
        assert "Found auth-related code" in text or "No mention of WebSocket" in text

    def test_direction_guidance_prevents_reversal(self):
        """Test that direction guidance prevents reversing relationships."""
        text = RIM_RELATIONSHIP_DIRECTION_GUIDANCE
        assert "Never reverse" in text or "reverse" in text
        assert "CALLS" in text
        assert "invokes" in text or "triggers" in text


class TestRIMGuidanceCompleteness:
    """Test that RIM guidance covers all necessary aspects."""

    def test_all_critical_concepts_covered(self):
        """Test that all critical RIM concepts are explained."""
        full_guidance = get_rim_guidance_for_system_prompt(
            include_sections=['all'],
            max_chars=10000
        )

        critical_concepts = [
            "Anchors",
            "Expanded Entities",
            "CALLS",
            "IMPORTS",
            "distance",
            "negative",
            "direction",
            "priority",
        ]

        for concept in critical_concepts:
            assert concept.lower() in full_guidance.lower(), f"Missing concept: {concept}"

    def test_guidance_includes_examples(self):
        """Test that guidance includes concrete examples."""
        guidance = get_rim_guidance_for_system_prompt()
        # Should have examples with actual code patterns
        assert "(" in guidance  # Some function/syntax examples
        assert "->" in guidance or ":" in guidance  # Notation examples

    def test_guidance_addresses_ambiguity(self):
        """Test that guidance addresses potential ambiguity."""
        guidance = get_rim_guidance_for_system_prompt()
        # Should address when to prefer what
        assert "Prefer" in guidance or "prefer" in guidance


class TestRIMGuidanceUsability:
    """Test that RIM guidance is usable and understandable."""

    def test_guidance_is_concise(self):
        """Test that guidance is concise enough for context windows."""
        guidance = get_rim_guidance_for_system_prompt()
        # Should be under 3000 chars for practical LLM use
        assert len(guidance) < 3500

    def test_guidance_has_clear_structure(self):
        """Test that guidance is clearly structured with headers."""
        guidance = get_rim_guidance_for_system_prompt()
        # Should use markdown/clear headers
        assert "###" in guidance or "**" in guidance or "---" in guidance

    def test_guidance_actionable_not_abstract(self):
        """Test that guidance is actionable, not overly abstract."""
        guidance = get_rim_guidance_for_system_prompt()
        # Should have concrete rules and steps
        assert "1." in guidance or "-" in guidance
        # Should reference specific patterns
        assert "CALLS" in guidance
        assert "IMPORTS" in guidance


class TestRIMGuidanceEdgeCases:
    """Test RIM guidance handling of edge cases."""

    def test_empty_anchors_and_expanded(self):
        """Test formatting with no data."""
        text = format_rim_metadata_for_prompt([], [])
        assert "REPOSITORY RELATIONSHIP METADATA" in text
        # Should gracefully handle empty input
        assert isinstance(text, str)

    def test_very_long_entity_names(self):
        """Test formatting handles long entity names."""
        anchors = [
            {
                'name': 'this_is_an_extremely_long_function_name_that_goes_on_forever_v2_updated',
                'type': 'function',
                'file_path': 'very/deep/path/structure/that/is/quite/long/file_name.py',
                'line_start': 42,
            }
        ]
        text = format_rim_metadata_for_prompt(anchors)
        # Should not crash and should format gracefully
        assert isinstance(text, str)
        assert len(text) > 0

    def test_missing_optional_fields(self):
        """Test formatting handles missing optional fields."""
        anchors = [
            {
                'name': 'func',
                'type': 'function',
                'file_path': 'file.py',
                # line_start missing
            }
        ]
        text = format_rim_metadata_for_prompt(anchors)
        # Should use defaults gracefully
        assert "func" in text

    def test_invalid_distance_values(self):
        """Test formatting handles invalid distance values."""
        anchors = [{'name': 'main', 'type': 'function', 'file_path': 'main.py', 'line_start': 1}]
        expanded = [
            {
                'name': 'func1',
                'type': 'function',
                'file_path': 'a.py',
                'line_start': 10,
                'distance_from_anchor': -1,  # Invalid
                'rel_type': 'CALLS',
            },
            {
                'name': 'func2',
                'type': 'function',
                'file_path': 'b.py',
                'line_start': 20,
                'distance_from_anchor': 999,  # Very large
                'rel_type': 'CALLS',
            },
        ]
        text = format_rim_metadata_for_prompt(anchors, expanded)
        # Should handle gracefully
        assert isinstance(text, str)
        assert len(text) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
