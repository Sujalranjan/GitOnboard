from typing import List, Dict, Set
from ..rim.repository import RepositoryModel
from .model import Feature, FeatureRelationship, FeatureRelationshipType, FeatureMembership
from .similarity.engine import SimilarityEngine
from .clustering.connected_components import ConnectedComponents
from .refinement import RefinementEngine
from .naming import NamingEngine
import uuid

class FeatureReconstructionEngine:
    """
    Orchestrates the transformation of Semantic Capabilities into bounded context Features.
    """
    def run(self, model: RepositoryModel) -> RepositoryModel:
        if not hasattr(model, "features"):
            model.features = {}
        if not hasattr(model, "feature_relationships"):
            model.feature_relationships = {}
            
        # 1. Similarity Engine
        sim_engine = SimilarityEngine(model)
        weighted_graph = sim_engine.build_weighted_graph()
        
        # 2. Clustering
        clustering_algo = ConnectedComponents(threshold=0.65)
        raw_clusters = clustering_algo.cluster(weighted_graph)
        
        # 3. Refinement
        refinement_engine = RefinementEngine(model)
        refined_clusters = refinement_engine.refine(raw_clusters)
        
        # 4. Assembly & Naming
        naming_engine = NamingEngine(model)
        features: List[Feature] = []
        
        for cluster in refined_clusters:
            name = naming_engine.name_feature(cluster)
            
            members: List[FeatureMembership] = []
            
            # Add capabilities
            for cid in cluster:
                cap = model.capabilities.get(cid)
                if not cap:
                    continue
                    
                members.append(FeatureMembership(
                    item_id=cid,
                    item_type="capability",
                    confidence=1.0,
                    evidence=[{"source": "Directly clustered capability"}]
                ))
                
                # Add underlying entities
                for src in cap.representative_sources:
                    members.append(FeatureMembership(
                        item_id=src,
                        item_type="entity",
                        confidence=0.8,
                        evidence=[{"source": f"Belongs to capability {cid}"}]
                    ))
                    
                    # If this entity is part of a pattern, add the pattern
                    patterns = getattr(model, "patterns", {})
                    if patterns:
                        for pattern in patterns.values():
                            if src in getattr(pattern, "participants", []):
                                members.append(FeatureMembership(
                                    item_id=pattern.id,
                                    item_type="pattern",
                                    confidence=0.7,
                                    evidence=[{"source": f"Pattern containing entity {src}"}]
                                ))
                            
            feature = Feature(
                id=f"feat:{uuid.uuid4().hex[:8]}",
                name=name,
                description=f"Auto-reconstructed feature for {name}",
                members=members,
                confidence=0.9,
                evidence=[{"source": "Reconstructed from capability graph"}]
            )
            features.append(feature)
            model.features[feature.id] = feature
            
        # 5. Relationship Projection
        # Project capability relationships up to features
        cap_to_feat: Dict[str, str] = {}
        for feat in features:
            for member in feat.members:
                if member.item_type == "capability":
                    cap_to_feat[member.item_id] = feat.id
                    
        added_edges = set()
        for cap_rel in model.capability_relationships.values():
            src_feat = cap_to_feat.get(cap_rel.source_id)
            tgt_feat = cap_to_feat.get(cap_rel.target_id)
            
            if src_feat and tgt_feat and src_feat != tgt_feat:
                edge_key = f"{src_feat}->{tgt_feat}"
                if edge_key not in added_edges:
                    added_edges.add(edge_key)
                    
                    feat_rel_type = FeatureRelationshipType.DEPENDS_ON
                    if cap_rel.type.value == "PERSISTS":
                        feat_rel_type = FeatureRelationshipType.USES
                        
                    frel = FeatureRelationship(
                        id=f"frel:{uuid.uuid4().hex[:8]}",
                        type=feat_rel_type,
                        source_id=src_feat,
                        target_id=tgt_feat,
                        metadata={"inferred_from": cap_rel.id}
                    )
                    model.feature_relationships[frel.id] = frel
                    
        return model
