from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict

def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    weights: Optional[List[float]] = None,
    rrf_k: int = 60,
    key_field: str = "id",
    top_k: int = 30
) -> List[Dict[str, Any]]:
    r"""
    Combines multiple ranked candidate lists using Reciprocal Rank Fusion (RRF).
    
    Formula:
        RRF_Score(d) = \sum_{r \in R} weight_r * (1 / (rrf_k + rank(d, r)))
        
    where rank(d, r) is 1-indexed rank of document d in list r.

    
    Args:
        ranked_lists: List of ranked candidate lists (each item is a dict with key_field).
        weights: Optional list of floats weighting each ranked list (defaults to 1.0 each).
        rrf_k: Constant smoothing parameter (standard default is 60).
        key_field: Unique identifier field on the candidate dict (e.g. 'id' or 'file_path:name').
        top_k: Number of unified candidates to return.
        
    Returns:
        List of candidate dicts sorted by fused score, with added fields '_rrf_score' and '_source_ranks'.
    """
    if not ranked_lists:
        return []

    if weights is None:
        weights = [1.0] * len(ranked_lists)

    scores: Dict[Any, float] = defaultdict(float)
    doc_map: Dict[Any, Dict[str, Any]] = {}
    source_ranks: Dict[Any, Dict[int, int]] = defaultdict(dict)

    for list_idx, ranked_list in enumerate(ranked_lists):
        w = weights[list_idx] if list_idx < len(weights) else 1.0
        for rank_idx, doc in enumerate(ranked_list):
            doc_key = doc.get(key_field)
            if not doc_key:
                # Fallback composite key if key_field is missing
                doc_key = f"{doc.get('file_path', '')}:{doc.get('name', doc.get('match_name', ''))}:{doc.get('type', doc.get('match_type', ''))}"
            
            rank = rank_idx + 1  # 1-indexed
            scores[doc_key] += w * (1.0 / (rrf_k + rank))
            source_ranks[doc_key][list_idx] = rank
            
            if doc_key not in doc_map:
                doc_map[doc_key] = dict(doc)

    # Sort items by accumulated RRF score descending
    sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

    results = []
    for k in sorted_keys[:top_k]:
        candidate = doc_map[k]
        candidate["_rrf_score"] = scores[k]
        candidate["_source_ranks"] = source_ranks[k]
        results.append(candidate)

    return results
