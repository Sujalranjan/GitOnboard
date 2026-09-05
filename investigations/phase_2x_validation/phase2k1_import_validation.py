#!/usr/bin/env python3
"""
Phase 2K.1: Import Path Validation

Quick test to verify that all the updated import paths work correctly.
This validates the architectural changes without running full analysis.
"""
import sys

def test_imports():
    """Test that all required imports work."""
    print("\n" + "="*80)
    print("PHASE 2K.1: IMPORT PATH VALIDATION")
    print("="*80 + "\n")

    tests = []

    # Test 1: Database imports
    print("Testing database imports...")
    try:
        from backend.database import SessionLocal, engine, Base
        print("✓ backend.database imports successful")
        tests.append(("Database", True))
    except Exception as e:
        print(f"✗ backend.database import failed: {e}")
        tests.append(("Database", False))

    # Test 2: FactStore imports
    print("Testing FactStore imports...")
    try:
        from backend.intelligence.store.fact_store import save_rim_to_fact_store
        from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
        from backend.models.repository import Repository, Analysis
        print("✓ FactStore imports successful")
        tests.append(("FactStore", True))
    except Exception as e:
        print(f"✗ FactStore import failed: {e}")
        tests.append(("FactStore", False))

    # Test 3: BM25 imports
    print("Testing BM25 imports...")
    try:
        from backend.intelligence.retrieval.lexical import BM25Index, CodeTokenizer
        print("✓ BM25 imports successful (from lexical.py)")
        tests.append(("BM25", True))
    except Exception as e:
        print(f"✗ BM25 import failed: {e}")
        tests.append(("BM25", False))

    # Test 4: Semantic imports
    print("Testing Semantic indexing imports...")
    try:
        from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder
        print("✓ Semantic indexing imports successful (SemanticIndexBuilder)")
        tests.append(("Semantic", True))
    except Exception as e:
        print(f"✗ Semantic import failed: {e}")
        tests.append(("Semantic", False))

    # Test 5: HybridRetriever imports
    print("Testing HybridRetriever imports...")
    try:
        from backend.intelligence.retrieval.retriever import HybridRetriever
        print("✓ HybridRetriever imports successful (from retriever.py)")
        tests.append(("HybridRetriever", True))
    except Exception as e:
        print(f"✗ HybridRetriever import failed: {e}")
        tests.append(("HybridRetriever", False))

    # Test 6: Context Assembler imports
    print("Testing Context Assembler imports...")
    try:
        from backend.agent.context.assembler import ContextAssembler
        print("✓ ContextAssembler imports successful (from agent.context)")
        tests.append(("ContextAssembler", True))
    except Exception as e:
        print(f"✗ ContextAssembler import failed: {e}")
        tests.append(("ContextAssembler", False))

    # Test 7: Analysis Engine imports
    print("Testing Analysis Engine imports...")
    try:
        from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
        from backend.intelligence.engine.analyzers import get_default_registry
        print("✓ Analysis Engine imports successful")
        tests.append(("AnalysisEngine", True))
    except Exception as e:
        print(f"✗ Analysis Engine import failed: {e}")
        tests.append(("AnalysisEngine", False))

    # Test 8: RIM imports
    print("Testing RIM imports...")
    try:
        from backend.intelligence.rim.repository import RepositoryModel
        from backend.intelligence.rim.entity import Entity
        from backend.intelligence.rim.relationship import Relationship
        from backend.intelligence.rim.enums import EntityType, RelationshipType
        print("✓ RIM imports successful")
        tests.append(("RIM", True))
    except Exception as e:
        print(f"✗ RIM import failed: {e}")
        tests.append(("RIM", False))

    # Summary
    print("\n" + "="*80)
    print("IMPORT VALIDATION SUMMARY")
    print("="*80 + "\n")

    successful = sum(1 for _, result in tests if result)
    total = len(tests)

    for name, result in tests:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")

    print(f"\nTotal: {successful}/{total} passed\n")

    if successful == total:
        print("✓ ALL IMPORTS SUCCESSFUL - Phase 2K.1 architecture is ready")
        print("="*80 + "\n")
        return True
    else:
        print("✗ Some imports failed - see details above")
        print("="*80 + "\n")
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
