"""
Canonical schema for retrieval results.

This schema defines the contract between:
- HybridRetriever (produces results)
- RIM metadata builder (consumes results)
- RIM graph expansion (uses seeds)
- Any other retrieval consumers

All retrieval strategies (lexical, semantic, exact) must return results
conforming to this schema.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from enum import Enum


class EntityType(str, Enum):
    """Types of entities that can be retrieved."""
    SYMBOL = "symbol"
    FILE = "file"
    ROUTE = "route"
    DATABASE_TABLE = "database_table"
    CAPABILITY = "capability"


@dataclass
class RetrieverResult:
    """
    Canonical retrieval result that all retrieval strategies must produce.

    This is the contract between retriever and consumers:
    - RIM metadata builder
    - Graph expansion
    - Seed resolution

    Fields are guaranteed to be present with stable semantics.
    """

    # REQUIRED: Identity
    id: str  # Unique identifier (database ID or composite key)
    entity_name: str  # Name of the entity (symbol name, file path, route, etc.)
    entity_type: EntityType  # Type of entity

    # REQUIRED: Location
    file_path: str  # File containing this entity
    line_start: Optional[int] = None  # Start line in file
    line_end: Optional[int] = None  # End line in file

    # OPTIONAL: Additional names
    qualified_name: Optional[str] = None  # Fully qualified name (package.class.method)

    # SCORING: How was this result found?
    score_type: str = "unknown"  # "lexical", "semantic", "exact_fact"
    score: float = 0.0  # Normalized relevance score (0-1 preferred)

    # METADATA: Additional context
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "entity_name": self.entity_name,
            "entity_type": self.entity_type.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "qualified_name": self.qualified_name,
            "score_type": self.score_type,
            "score": self.score,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrieverResult":
        """Create from dictionary."""
        entity_type_val = data.get("entity_type")
        if isinstance(entity_type_val, str):
            entity_type = EntityType(entity_type_val)
        else:
            entity_type = entity_type_val

        return cls(
            id=data["id"],
            entity_name=data["entity_name"],
            entity_type=entity_type,
            file_path=data["file_path"],
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            qualified_name=data.get("qualified_name"),
            score_type=data.get("score_type", "unknown"),
            score=data.get("score", 0.0),
            metadata=data.get("metadata", {}),
        )


def convert_lexical_result_to_schema(doc: Dict[str, Any]) -> RetrieverResult:
    """Convert BM25 lexical result to canonical schema."""
    entity_type_str = doc.get("type") or doc.get("match_type", "symbol")
    try:
        entity_type = EntityType(entity_type_str)
    except ValueError:
        entity_type = EntityType.SYMBOL

    # Get entity name from available fields
    entity_name = doc.get("name") or doc.get("match_name") or doc.get("qualified_name", "")

    return RetrieverResult(
        id=doc.get("id", ""),
        entity_name=entity_name,
        entity_type=entity_type,
        file_path=doc.get("file_path", ""),
        line_start=doc.get("line_start"),
        line_end=doc.get("line_end"),
        qualified_name=doc.get("qualified_name"),
        score_type="lexical",
        score=doc.get("bm25_score", 0.0),
        metadata={
            "symbol_id": doc.get("symbol_id"),
        }
    )


def convert_semantic_result_to_schema(doc: Dict[str, Any]) -> RetrieverResult:
    """Convert Chroma semantic result to canonical schema."""
    entity_type_str = doc.get("type") or doc.get("match_type", "symbol")
    try:
        entity_type = EntityType(entity_type_str)
    except ValueError:
        entity_type = EntityType.SYMBOL

    entity_name = doc.get("name") or doc.get("match_name") or doc.get("qualified_name", "")

    return RetrieverResult(
        id=doc.get("id", ""),
        entity_name=entity_name,
        entity_type=entity_type,
        file_path=doc.get("file_path", ""),
        line_start=doc.get("line_start"),
        line_end=doc.get("line_end"),
        qualified_name=doc.get("qualified_name"),
        score_type="semantic",
        score=1.0 - (doc.get("distance", 1.0) / 2.0),  # Normalize distance to score
        metadata={
            "symbol_id": doc.get("symbol_id"),
            "distance": doc.get("distance"),
        }
    )


def convert_exact_result_to_schema(doc: Dict[str, Any]) -> RetrieverResult:
    """Convert exact fact result to canonical schema."""
    entity_type_str = doc.get("type") or doc.get("match_type", "symbol")
    try:
        entity_type = EntityType(entity_type_str)
    except ValueError:
        entity_type = EntityType.SYMBOL

    entity_name = doc.get("name") or doc.get("match_name") or doc.get("qualified_name", "")

    return RetrieverResult(
        id=doc.get("id", ""),
        entity_name=entity_name,
        entity_type=entity_type,
        file_path=doc.get("file_path", ""),
        line_start=doc.get("line_start"),
        line_end=doc.get("line_end"),
        qualified_name=doc.get("qualified_name"),
        score_type="exact_fact",
        score=1.0,  # Exact matches get highest score
        metadata={
            "symbol_id": doc.get("symbol_id"),
        }
    )
