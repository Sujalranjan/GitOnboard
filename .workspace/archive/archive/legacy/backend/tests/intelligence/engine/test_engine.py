import pytest
from unittest.mock import MagicMock
from backend.intelligence.engine.core.engine import IntelligenceEngine
from backend.intelligence.engine.core.registry import IntelligenceRegistry
from backend.intelligence.engine.core.recommendations import RecommendationEngine
from backend.intelligence.engine.core.scorecard_engine import ScorecardEngine
from backend.intelligence.engine.providers.architecture_health import ArchitectureHealthProvider
from backend.intelligence.engine.providers.risk import RiskProvider
from backend.intelligence.store.store import MemoryStore
from backend.intelligence.engine.model.intelligence import IntelligenceType

def test_intelligence_engine():
    # Setup registry
    registry = IntelligenceRegistry()
    registry.register(ArchitectureHealthProvider())
    registry.register(RiskProvider())
    
    # Setup engines
    query_engine = MagicMock()
    analysis_engine = MagicMock()
    store = MemoryStore()
    recommendation_engine = RecommendationEngine()
    scorecard_engine = ScorecardEngine()
    
    engine = IntelligenceEngine(
        registry=registry,
        query_engine=query_engine,
        analysis_engine=analysis_engine,
        store=store,
        recommendation_engine=recommendation_engine,
        scorecard_engine=scorecard_engine
    )
    
    repository = MagicMock()
    
    # Run evaluate
    results = engine.evaluate(repository)
    
    assert len(results) == 2
    assert any(r.type == IntelligenceType.ARCHITECTURE_HEALTH for r in results)
    
    # Verify recommendations were purely functionally derived
    arch_intel = next(r for r in results if r.type == IntelligenceType.ARCHITECTURE_HEALTH)
    assert len(arch_intel.recommendations) > 0
    assert arch_intel.recommendations[0].action == "Extract Interface"
    
    # Verify scorecard derivation
    scorecard = scorecard_engine.compute(results)
    assert scorecard.architecture_score < 100
    assert scorecard.risk_score < 100
    
    # Verify store persistence
    assert len(store.intelligence) == 2
