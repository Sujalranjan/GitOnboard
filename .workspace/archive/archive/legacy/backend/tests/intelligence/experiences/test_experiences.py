import pytest
import os
from unittest.mock import MagicMock
from backend.intelligence.experiences.framework.registry import ExperienceRegistry
from backend.intelligence.experiences.framework.runner import ExperienceRunner, ExperienceRequest
from backend.intelligence.orchestrator.intent.analyzer import UserIntent, IntentType
from backend.intelligence.orchestrator.knowledge.model import KnowledgePack
from backend.intelligence.features.model import Feature

def test_experience_registry(tmpdir):
    # Create a mock yaml definition
    yaml_content = \"\"\"
id: test_exp
name: Test Experience
intents:
  - Explain Feature
knowledge_requirements:
  - features
prompt_template: test.j2
\"\"\"
    yaml_file = tmpdir.join("test.yaml")
    yaml_file.write(yaml_content)
    
    registry = ExperienceRegistry()
    registry.load_from_directory(str(tmpdir))
    
    exp = registry.get("test_exp")
    assert exp.name == "Test Experience"
    
    exp2 = registry.find_by_intent("Explain Feature")
    assert exp2.id == "test_exp"

def test_experience_runner(tmpdir):
    # Setup template
    template_file = tmpdir.join("test.j2")
    template_file.write("Query: {{ query }}\nFeatures: {{ features }}")
    
    # Setup registry
    registry = ExperienceRegistry()
    yaml_content = \"\"\"
id: test_exp
name: Test Exp
intents: [Explain Feature]
knowledge_requirements: [features]
prompt_template: test.j2
\"\"\"
    tmpdir.join("test.yaml").write(yaml_content)
    registry.load_from_directory(str(tmpdir))
    
    # Setup retrieval engine
    retrieval = MagicMock()
    feat = Feature(id="f1", name="Auth", members=[], confidence=1.0, evidence=[])
    pack = KnowledgePack(intent="Explain Feature", features=[feat])
    retrieval.build_knowledge_pack.return_value = pack
    
    # Setup AI Provider
    provider = MagicMock()
    provider.complete.return_value = MagicMock(answer="Mocked Answer", evidence_links=[], confidence=1.0)
    
    # Run
    runner = ExperienceRunner(registry, retrieval, provider, str(tmpdir))
    req = ExperienceRequest(query="How does Auth work?", experience_id="test_exp")
    res = runner.execute(req)
    
    # Assert provider was called with the compiled prompt
    provider.complete.assert_called_once()
    called_prompt = provider.complete.call_args[0][0]
    assert "Query: How does Auth work?" in called_prompt
    assert "Features: Auth" in called_prompt
    
    # Assert response
    assert res.answer == "Mocked Answer"
