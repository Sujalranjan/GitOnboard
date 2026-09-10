import pytest
from unittest.mock import MagicMock
from backend.intelligence.orchestrator.intent.analyzer import IntentAnalyzer, IntentType
from backend.intelligence.orchestrator.retrieval.engine import RetrievalEngine
from backend.intelligence.orchestrator.prompt.orchestrator import PromptOrchestrator
from backend.intelligence.orchestrator.providers.mock_provider import MockAIProvider
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.features.model import Feature
from backend.intelligence.query.model.result import QueryResult

def test_intent_analyzer():
    analyzer = IntentAnalyzer()
    intent = analyzer.analyze("How does authentication work?")
    
    assert intent.type == IntentType.EXPLAIN_FEATURE
    assert "authentication" in intent.targets[0]

def test_retrieval_pipeline():
    api = MagicMock()
    # Mock the query execution to return a feature
    feat = Feature(id="feat:1", name="authentication", members=[], confidence=1.0, evidence=[])
    mock_result = QueryResult(type="FEATURE", result=feat, evidence=[], confidence=1.0)
    api.engine.executor.execute.return_value = mock_result
    
    engine = RetrievalEngine(api)
    intent = IntentAnalyzer().analyze("How does authentication work?")
    pack = engine.build_knowledge_pack(intent)
    
    assert pack.intent == IntentType.EXPLAIN_FEATURE.value
    assert len(pack.features) > 0
    assert pack.features[0].name == "authentication"

def test_prompt_orchestration():
    api = MagicMock()
    feat = Feature(id="feat:1", name="authentication", description="Handles auth", members=[], confidence=1.0, evidence=[])
    mock_result = QueryResult(type="FEATURE", result=feat, evidence=[], confidence=1.0)
    api.engine.executor.execute.return_value = mock_result
    
    intent = IntentAnalyzer().analyze("How does authentication work?")
    pack = RetrievalEngine(api).build_knowledge_pack(intent)
    
    orchestrator = PromptOrchestrator()
    prompt = orchestrator.build_prompt(pack)
    
    assert "Intent: Explain Feature" in prompt
    assert "authentication: Handles auth" in prompt

def test_provider():
    provider = MockAIProvider()
    response = provider.complete("Test prompt")
    
    assert response.confidence == 0.99
    assert len(response.evidence_links) > 0
