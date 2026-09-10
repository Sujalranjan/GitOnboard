import pytest
from backend.intelligence.rim import (
    EntityType, RelationshipType, SourceLocation, Entity, Relationship,
    RepositoryMetadata, RepositoryModel, generate_entity_id,
    generate_relationship_id, RIMValidator, serialize_rim, deserialize_rim,
    GraphQueryService
)

def test_stable_id_generation():
    ent_id = generate_entity_id(EntityType.FUNCTION, "src/auth/service.py", "auth.login")
    assert ent_id == "urn:function:src/auth/service.py#auth.login"
    
    rel_id = generate_relationship_id(RelationshipType.CALLS, "urn:func:1", "urn:func:2")
    assert rel_id == "rel:calls:urn:func:1->urn:func:2"

def test_entity_creation():
    loc = SourceLocation(
        repository_path="src/main.py",
        start_line=10,
        end_line=20,
        language="Python"
    )
    ent = Entity(
        id="urn:function:src/main.py#main.run",
        type=EntityType.FUNCTION,
        name="run",
        qualified_name="main.run",
        display_name="run()",
        location=loc,
        metadata={"visibility": "public"}
    )
    assert ent.id == "urn:function:src/main.py#main.run"
    assert ent.location.language == "Python"
    assert ent.metadata["visibility"] == "public"

def test_validation():
    loc = SourceLocation(repository_path="test", start_line=1, end_line=2, language="test")
    ent1 = Entity(id="urn:func:1", type=EntityType.FUNCTION, name="f1", location=loc)
    ent2 = Entity(id="urn:func:2", type=EntityType.FUNCTION, name="f2", location=loc)
    
    rel = Relationship(
        id="rel:calls:1->2",
        type=RelationshipType.CALLS,
        source_id="urn:func:1",
        target_id="urn:func:2"
    )
    
    model = RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test"),
        entities={ent1.id: ent1, ent2.id: ent2},
        relationships={rel.id: rel}
    )
    
    validator = RIMValidator(model)
    assert validator.validate() is True
    assert len(validator.errors) == 0
    
    # Test invalid relationship
    bad_rel = Relationship(
        id="rel:calls:1->3",
        type=RelationshipType.CALLS,
        source_id="urn:func:1",
        target_id="urn:func:3"
    )
    model.relationships[bad_rel.id] = bad_rel
    validator = RIMValidator(model)
    assert validator.validate() is False
    assert any("not found in entities" in err for err in validator.errors)

def test_serialization():
    loc = SourceLocation(repository_path="test", start_line=1, end_line=2, language="test")
    ent = Entity(id="urn:func:1", type=EntityType.FUNCTION, name="f1", location=loc)
    model = RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test"),
        entities={ent.id: ent}
    )
    
    json_str = serialize_rim(model)
    assert "urn:func:1" in json_str
    
    model2 = deserialize_rim(json_str)
    assert model2.metadata.name == "test"
    assert "urn:func:1" in model2.entities
    assert model2.entities["urn:func:1"].name == "f1"

def test_query_service():
    loc = SourceLocation(repository_path="test", start_line=1, end_line=2, language="test")
    ent1 = Entity(id="urn:func:1", type=EntityType.FUNCTION, name="f1", location=loc)
    ent2 = Entity(id="urn:class:2", type=EntityType.CLASS, name="c2", location=loc)
    rel = Relationship(
        id="rel:calls:1->2",
        type=RelationshipType.CALLS,
        source_id="urn:func:1",
        target_id="urn:class:2"
    )
    
    model = RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test"),
        entities={ent1.id: ent1, ent2.id: ent2},
        relationships={rel.id: rel}
    )
    
    qs = GraphQueryService(model)
    assert qs.get_entity("urn:func:1") == ent1
    assert len(qs.find_by_type(EntityType.CLASS)) == 1
    assert len(qs.get_outgoing("urn:func:1")) == 1
    assert len(qs.get_incoming("urn:class:2")) == 1
    assert qs.neighbors("urn:func:1")[0] == ent2
