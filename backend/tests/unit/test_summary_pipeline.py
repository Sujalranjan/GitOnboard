"""
Unit tests for the documentation-aware Summary Pipeline:
classification, context budgeting, source delineation, prompt generation, and mock LLM orchestration.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.summary.schemas import (
    DocType,
    DocPriority,
    DiscoveredDoc,
    BudgetedDocContext,
)
from backend.summary.classifier import DocClassifier
from backend.summary.budgeter import DocContextBudgeter
from backend.summary.discovery import DocDiscovery
from backend.summary.generator import SummaryGenerator
from backend.summary.pipeline import SummaryPipeline
from backend.ai.service import LLMService
from backend.ai.schemas import LLMResponse, TokenUsage


@pytest.fixture
def classifier():
    return DocClassifier()


def test_classifier_priorities(classifier):
    # Highest Priority (README, Architecture)
    d_type, prio = classifier.classify("README.md")
    assert d_type == DocType.PRIMARY_README
    assert prio == DocPriority.HIGHEST

    d_type, prio = classifier.classify("ARCHITECTURE.md")
    assert d_type == DocType.ARCHITECTURE
    assert prio == DocPriority.HIGHEST

    d_type, prio = classifier.classify("docs/architecture/design.md")
    assert d_type == DocType.ARCHITECTURE
    assert prio == DocPriority.HIGHEST

    # High Priority (Contributing, System docs)
    d_type, prio = classifier.classify("CONTRIBUTING.md")
    assert d_type == DocType.CONTRIBUTING
    assert prio == DocPriority.HIGH

    d_type, prio = classifier.classify("docs/overview.md")
    assert d_type == DocType.PRODUCT_SYSTEM_DOCS
    assert prio == DocPriority.HIGH

    # Medium Priority (API, Guides, Diagrams)
    d_type, prio = classifier.classify("API.md")
    assert d_type == DocType.API_DOCS
    assert prio == DocPriority.MEDIUM

    d_type, prio = classifier.classify("docs/guides/setup.md")
    assert d_type == DocType.GUIDES_TUTORIALS
    assert prio == DocPriority.MEDIUM

    d_type, prio = classifier.classify("docs/flow.mmd")
    assert d_type == DocType.DIAGRAMS
    assert prio == DocPriority.MEDIUM

    # Agent Instructions (Strictly lower priority / separate trust class)
    for agent_file in ["AGENTS.md", "CLAUDE.md", "agent.md", "skill.md", ".cursor/rules/main.md", ".agents/skills/test/SKILL.md"]:
        d_type, prio = classifier.classify(agent_file)
        assert d_type == DocType.AGENT_INSTRUCTIONS
        assert prio == DocPriority.AGENT_CONTEXT
        assert prio < DocPriority.MEDIUM
        assert prio < DocPriority.HIGH
        assert prio < DocPriority.HIGHEST


def test_budgeter_enforces_budget_and_agent_cap():
    budgeter = DocContextBudgeter(total_budget=5000, agent_budget=500)

    docs = [
        DiscoveredDoc(
            path="README.md",
            filename="README.md",
            doc_type=DocType.PRIMARY_README,
            priority=DocPriority.HIGHEST,
            raw_size=1000,
            line_count=50,
            content="A" * 1000,
        ),
        DiscoveredDoc(
            path="ARCHITECTURE.md",
            filename="ARCHITECTURE.md",
            doc_type=DocType.ARCHITECTURE,
            priority=DocPriority.HIGHEST,
            raw_size=2000,
            line_count=100,
            content="B" * 2000,
        ),
        # Agent file that is huge (2000 chars)
        DiscoveredDoc(
            path="AGENTS.md",
            filename="AGENTS.md",
            doc_type=DocType.AGENT_INSTRUCTIONS,
            priority=DocPriority.AGENT_CONTEXT,
            raw_size=2000,
            line_count=100,
            content="C" * 2000,
        ),
        DiscoveredDoc(
            path="CLAUDE.md",
            filename="CLAUDE.md",
            doc_type=DocType.AGENT_INSTRUCTIONS,
            priority=DocPriority.AGENT_CONTEXT,
            raw_size=1000,
            line_count=50,
            content="D" * 1000,
        ),
    ]

    budgeted = budgeter.budget(docs)

    # Primary docs should be included
    assert len(budgeted.primary_docs) == 2
    # Agent docs must not exceed agent budget cap (500 chars)
    agent_chars = sum(len(d.content) for d in budgeted.agent_docs)
    assert agent_chars <= 500
    # Total context within total budget
    assert budgeted.total_chars <= 5000


def test_budgeter_preserves_headings_on_truncation():
    budgeter = DocContextBudgeter()
    long_content = "# Title\n\nIntro paragraph.\n\n" + ("Text line.\n" * 200) + "## Subheading 1\n\nMore text.\n## Subheading 2\n"
    doc = DiscoveredDoc(
        path="docs/large.md",
        filename="large.md",
        doc_type=DocType.PRODUCT_SYSTEM_DOCS,
        priority=DocPriority.HIGH,
        raw_size=len(long_content),
        line_count=210,
        content=long_content,
    )

    truncated = budgeter._truncate_doc(doc, max_chars=500)
    assert truncated.is_truncated is True
    assert "# Title" in truncated.content
    assert "[Remaining Headings in File]:" in truncated.content
    assert "Subheading" in truncated.content


def test_generator_prompt_source_delineation():
    mock_llm = MagicMock(spec=LLMService)
    generator = SummaryGenerator(mock_llm)

    metadata = {
        "repository": {"name": "DemoApp", "primary_language": "Python", "frameworks": ["FastAPI"]},
        "entrypoints": ["main.py"],
        "modules": [{"name": "auth", "purpose": "Auth module"}],
    }
    metrics = {"total_files": 25, "lines_of_code": 3500, "total_functions": 40}

    budgeted = BudgetedDocContext(
        primary_docs=[
            DiscoveredDoc(
                path="README.md",
                filename="README.md",
                doc_type=DocType.PRIMARY_README,
                priority=DocPriority.HIGHEST,
                raw_size=100,
                line_count=5,
                content="# DemoApp\nA FastAPI web service.",
            )
        ],
        agent_docs=[
            DiscoveredDoc(
                path="AGENTS.md",
                filename="AGENTS.md",
                doc_type=DocType.AGENT_INSTRUCTIONS,
                priority=DocPriority.AGENT_CONTEXT,
                raw_size=50,
                line_count=3,
                content="Always format code with black.",
            )
        ],
        total_chars=150,
        total_tokens_est=37,
    )

    prompt = generator.build_prompt_context(metadata, metrics, budgeted)

    # Assert distinct section banners exist in prompt
    assert "=== SECTION 1: VERIFIED CODE EVIDENCE (STATIC ANALYSIS) ===" in prompt
    assert "=== SECTION 2: PRIMARY PROJECT DOCUMENTATION (README & ARCHITECTURE) ===" in prompt
    assert "=== SECTION 5: AGENT / TOOL INSTRUCTIONS (LOW-PRIORITY CONTEXTUAL ONLY) ===" in prompt
    assert "FastAPI" in prompt
    assert "README.md" in prompt
    assert "AGENTS.md" in prompt


@pytest.mark.asyncio
async def test_summary_pipeline_e2e_mock_llm():
    mock_llm = MagicMock(spec=LLMService)
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            content="# DemoApp — Repository Summary\n\n## 1. Overview\nGrounded summary.",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=80, total_tokens=280),
            provider="mock",
            model="mock",
        )
    )

    pipeline = SummaryPipeline(llm_service=mock_llm)
    metadata = {
        "repository": {"name": "DemoApp", "primary_language": "Python", "frameworks": ["FastAPI"]},
        "entrypoints": ["main.py"],
        "modules": [],
    }

    result = await pipeline.run(
        repo_name="DemoApp",
        metadata=metadata,
        metrics={"total_files": 10},
    )

    assert result.summary_markdown.startswith("# DemoApp — Repository Summary")
    assert "total_chars" in result.doc_context_stats
    mock_llm.generate.assert_awaited_once()
