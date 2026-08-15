from .repository import RepositoryModel
from typing import Dict, Any
import json

def serialize_rim(model: RepositoryModel) -> str:
    """
    Serialize the RepositoryModel into the canonical JSON format.
    """
    data = {
        "version": "1.0",
        "repository": model.metadata.model_dump(),
        "entities": [e.model_dump() for e in model.entities.values()],
        "relationships": [r.model_dump() for r in model.relationships.values()],
        "capabilities": [c.model_dump() for c in getattr(model, 'capabilities', {}).values()],
        "capability_relationships": [r.model_dump() for r in getattr(model, 'capability_relationships', {}).values()],
        "features": [f.model_dump() for f in getattr(model, 'features', {}).values()],
        "feature_relationships": [r.model_dump() for r in getattr(model, 'feature_relationships', {}).values()]
    }
    return json.dumps(data, indent=2)

def deserialize_rim(json_str: str) -> RepositoryModel:
    """
    Deserialize the canonical JSON format back into a RepositoryModel.
    """
    data = json.loads(json_str)
    
    # Reconstruct dictionary maps from lists
    entities_map = {e["id"]: e for e in data.get("entities", [])}
    relationships_map = {r["id"]: r for r in data.get("relationships", [])}
    capabilities_map = {c["id"]: c for c in data.get("capabilities", [])}
    cap_rels_map = {r["id"]: r for r in data.get("capability_relationships", [])}
    features_map = {f["id"]: f for f in data.get("features", [])}
    feature_rels_map = {r["id"]: r for r in data.get("feature_relationships", [])}
    
    model_data = {
        "metadata": data.get("repository", {}),
        "entities": entities_map,
        "relationships": relationships_map,
        "capabilities": capabilities_map,
        "capability_relationships": cap_rels_map,
        "features": features_map,
        "feature_relationships": feature_rels_map
    }
    
    return RepositoryModel.model_validate(model_data)
