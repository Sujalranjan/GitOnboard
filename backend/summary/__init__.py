"""
Documentation-Aware Repository Summary Pipeline.
"""
from .schemas import (
    DocType,
    DocPriority,
    DiscoveredDoc,
    BudgetedDocContext,
    SummaryGenerationResult,
)
from .discovery import DocDiscovery
from .classifier import DocClassifier
from .budgeter import DocContextBudgeter
from .generator import SummaryGenerator
from .pipeline import SummaryPipeline

__all__ = [
    "DocType",
    "DocPriority",
    "DiscoveredDoc",
    "BudgetedDocContext",
    "SummaryGenerationResult",
    "DocDiscovery",
    "DocClassifier",
    "DocContextBudgeter",
    "SummaryGenerator",
    "SummaryPipeline",
]
