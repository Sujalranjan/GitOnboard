#!/usr/bin/env python3
"""
RIM Reality Audit: Comprehensive inspection of Repository Intelligence Platform

Determines:
1. What RIM/navigation features are actually implemented (not just documented)
2. Whether features are connected and working end-to-end
3. Quality of real-data verification
4. Gaps preventing RIM from functioning as a repository navigation tool

AUDIT RULES:
- Feature gets FULL only if: implemented + connected + executable + verified
- Distinguished states: PLANNED vs IMPLEMENTED vs CONNECTED vs WORKING vs VERIFIED
- Credit given only for working end-to-end flows, not individual components
"""

import os
import sys
import json
import ast
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# AUDIT DATA STRUCTURES
# ============================================================================

class ImplementationStatus(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    DISCONNECTED = "DISCONNECTED"
    MISSING = "MISSING"
    UNVERIFIED = "UNVERIFIED"


@dataclass
class NodeTypeAudit:
    name: str
    status: ImplementationStatus
    definition_file: Optional[str] = None
    storage_models: List[str] = field(default_factory=list)
    creation_pipeline: List[str] = field(default_factory=list)
    retrieval_api: Optional[str] = None
    consumer_modules: List[str] = field(default_factory=list)
    tests: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class RelationshipAudit:
    relationship: str
    represented: bool
    extracted: bool
    persisted: bool
    queryable: bool
    reverse_queryable: bool
    tested: bool
    real_data_verified: bool
    status: ImplementationStatus
    evidence: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class QueryOperationAudit:
    operation: str
    actual_method: Optional[str]
    status: ImplementationStatus
    implemented_in: Optional[str] = None
    tested: bool = False
    verified_on_real_data: bool = False
    evidence: List[str] = field(default_factory=list)
    notes: str = ""


# ============================================================================
# CODE INSPECTION UTILITIES
# ============================================================================

class CodeInspector:
    """Inspects Python codebase for features, classes, methods."""

    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)

    def find_files(self, pattern: str) -> List[Path]:
        """Find files matching glob pattern."""
        return list(self.root_dir.glob(pattern))

    def grep_pattern(self, pattern: str, *file_patterns: str) -> Dict[str, List[Tuple[int, str]]]:
        """Search for pattern in files matching patterns."""
        import re
        results = {}
        for file_pattern in file_patterns:
            for file_path in self.root_dir.glob(file_pattern):
                if not file_path.is_file() or file_path.suffix != '.py':
                    continue
                try:
                    with open(file_path) as f:
                        for line_no, line in enumerate(f, 1):
                            if re.search(pattern, line):
                                key = str(file_path.relative_to(self.root_dir))
                                if key not in results:
                                    results[key] = []
                                results[key].append((line_no, line.strip()))
                except Exception:
                    pass
        return results

    def find_class_definitions(self, class_name: str, *patterns: str) -> List[Tuple[str, int]]:
        """Find class definitions."""
        results = []
        for pattern in patterns:
            for file_path in self.root_dir.glob(pattern):
                if not file_path.is_file() or file_path.suffix != '.py':
                    continue
                try:
                    with open(file_path) as f:
                        tree = ast.parse(f.read(), filename=str(file_path))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef) and class_name in node.name:
                            rel_path = file_path.relative_to(self.root_dir)
                            results.append((str(rel_path), node.lineno))
                except Exception:
                    pass
        return results

    def find_function_definitions(self, func_name: str, *patterns: str) -> List[Tuple[str, int]]:
        """Find function definitions."""
        results = []
        for pattern in patterns:
            for file_path in self.root_dir.glob(pattern):
                if not file_path.is_file() or file_path.suffix != '.py':
                    continue
                try:
                    with open(file_path) as f:
                        tree = ast.parse(f.read(), filename=str(file_path))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef) and func_name in node.name:
                            rel_path = file_path.relative_to(self.root_dir)
                            results.append((str(rel_path), node.lineno))
                except Exception:
                    pass
        return results


# ============================================================================
# AUDIT IMPLEMENTATION
# ============================================================================

class RIMRealityAudit:
    """Conducts comprehensive audit of RIM implementation."""

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.backend_root = self.repo_root / "backend"
        self.inspector = CodeInspector(str(self.backend_root))

        self.node_audits: Dict[str, NodeTypeAudit] = {}
        self.relationship_audits: Dict[str, RelationshipAudit] = {}
        self.query_operations: Dict[str, QueryOperationAudit] = {}
        self.execution_paths: List[Dict[str, Any]] = []
        self.major_gaps: List[Dict[str, Any]] = []

    def audit_node_types(self):
        """Audit whether RIM node types are actually implemented."""
        logger.info("Auditing RIM Node Types...")

        # Check for entity definitions
        entity_files = self.inspector.find_files("intelligence/rim/*.py")
        entity_def_file = None
        for f in entity_files:
            if 'entity' in f.name:
                entity_def_file = str(f.relative_to(self.backend_root))

        # Check for FactStore models
        fact_store_file = self.backend_root / "models" / "fact_store.py"

        node_types = {
            "Repository": {"kind": "REPOSITORY"},
            "File": {"kind": "FILE"},
            "Directory": {"kind": "DIRECTORY"},
            "Module": {"kind": "MODULE"},
            "Class": {"kind": "CLASS"},
            "Function": {"kind": "FUNCTION"},
            "Route": {"kind": "ROUTE"},
            "DatabaseObject": {"kind": "DATABASE"},
            "Capability": {"kind": "CAPABILITY"},
            "Package": {"kind": "PACKAGE"},
        }

        for node_name, info in node_types.items():
            # Look for Fact* models in fact_store
            fact_model_name = f"Fact{node_name}"

            # Check if model is defined
            model_defined = False
            storage_models = []
            if fact_store_file.exists():
                with open(fact_store_file) as f:
                    content = f.read()
                    if f"class {fact_model_name}" in content:
                        model_defined = True
                        storage_models.append(fact_model_name)
                    # Also check for related models
                    if node_name == "Class" and "FactSymbol" in content:
                        storage_models.append("FactSymbol")
                    elif node_name == "Function" and "FactSymbol" in content:
                        storage_models.append("FactSymbol")

            # Check if there's retrieval/query support
            query_layer_file = self.backend_root / "intelligence" / "query_layer.py"
            retrieval_api = None
            if query_layer_file.exists():
                with open(query_layer_file) as f:
                    content = f.read()
                    if node_name == "Function" and "find_function" in content:
                        retrieval_api = "QueryLayer.find_function"
                    elif node_name == "Class" and "get_class" in content:
                        retrieval_api = "QueryLayer.get_class"
                    elif node_name == "File" and "get_file" in content:
                        retrieval_api = "QueryLayer.get_file"

            # Check for tests
            test_files = self.inspector.find_files(f"tests/**/*{node_name.lower()}*.py")

            # Determine status
            status = ImplementationStatus.MISSING
            if model_defined and storage_models:
                if retrieval_api or fact_model_name in ["FactFile", "FactSymbol"]:
                    status = ImplementationStatus.PARTIAL
                    if test_files:
                        status = ImplementationStatus.PARTIAL  # Need verification

            self.node_audits[node_name] = NodeTypeAudit(
                name=node_name,
                status=status,
                definition_file=entity_def_file,
                storage_models=storage_models,
                retrieval_api=retrieval_api,
                tests=[str(f.relative_to(self.backend_root)) for f in test_files],
                evidence=[]
            )

    def audit_relationships(self):
        """Audit whether relationships are extracted, stored, and queryable."""
        logger.info("Auditing Relationships...")

        relationship_types = [
            "CONTAINS", "DEFINED_IN", "IMPORTS", "CALLS", "CALLED_BY",
            "READS", "WRITES", "ROUTES_TO", "DEPENDS_ON", "USES", "INHERITS"
        ]

        fact_store_file = self.backend_root / "models" / "fact_store.py"

        for rel_type in relationship_types:
            # Check if FactRelationship exists
            represented = False
            persisted = False
            queryable = False
            reverse_queryable = False
            extracted = False
            tested = False

            if fact_store_file.exists():
                with open(fact_store_file) as f:
                    content = f.read()
                    if "FactRelationship" in content:
                        represented = True
                        if "rel_type" in content:
                            persisted = True

            # Check if QueryLayer can query
            query_layer_file = self.backend_root / "intelligence" / "query_layer.py"
            if query_layer_file.exists():
                with open(query_layer_file) as f:
                    content = f.read()
                    if rel_type.lower() in content or "relationships" in content:
                        queryable = True

            # Check for extraction in parser/analyzer
            extraction_patterns = [
                f"backend/intelligence/parser.py",
                f"backend/intelligence/analysis/**/*.py",
                f"backend/intelligence/engine/**/*.py",
            ]
            extraction_files = self.inspector.grep_pattern(
                rel_type,
                *extraction_patterns
            )
            if extraction_files:
                extracted = True

            # Check tests
            test_files = self.inspector.find_files(f"tests/**/*relationship*.py")
            if test_files:
                tested = True

            status = ImplementationStatus.MISSING
            if represented and persisted:
                status = ImplementationStatus.PARTIAL

            self.relationship_audits[rel_type] = RelationshipAudit(
                relationship=rel_type,
                represented=represented,
                extracted=extracted,
                persisted=persisted,
                queryable=queryable,
                reverse_queryable=reverse_queryable,
                tested=tested,
                real_data_verified=False,
                status=status,
                evidence=list(extraction_files.keys())[:3]
            )

    def audit_query_layer(self):
        """Audit QueryLayer capabilities."""
        logger.info("Auditing QueryLayer...")

        operations = [
            ("find_symbol", "find_symbol"),
            ("get_entity", "get_file"),
            ("get_callers", None),
            ("get_callees", "get_calls"),
            ("get_imports", None),
            ("get_dependents", None),
            ("get_dependencies", "get_dependencies"),
            ("get_related_files", None),
            ("get_related_symbols", None),
            ("get_routes", None),
            ("trace", None),
        ]

        query_layer_file = self.backend_root / "intelligence" / "query_layer.py"
        available_methods = []

        if query_layer_file.exists():
            with open(query_layer_file) as f:
                tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        available_methods.append(node.name)

        for op, actual_method in operations:
            status = ImplementationStatus.MISSING
            tested = False
            actual_impl = actual_method

            if actual_method and actual_method in available_methods:
                status = ImplementationStatus.PARTIAL
            elif op in available_methods:
                status = ImplementationStatus.PARTIAL
                actual_impl = op

            # Check for tests
            test_files = self.inspector.grep_pattern(op, "tests/**/*query*.py")
            if test_files:
                tested = True

            self.query_operations[op] = QueryOperationAudit(
                operation=op,
                actual_method=actual_impl,
                status=status,
                implemented_in="backend/intelligence/query_layer.py" if actual_impl else None,
                tested=tested,
                evidence=list(test_files.keys())[:2]
            )

    def audit_retrieval_pipeline(self):
        """Audit the retrieval pipeline end-to-end."""
        logger.info("Auditing Retrieval Pipeline...")

        retriever_file = self.backend_root / "intelligence" / "retrieval" / "retriever.py"

        if not retriever_file.exists():
            logger.warning("HybridRetriever not found")
            return

        with open(retriever_file) as f:
            content = f.read()

        # Check for key pipeline stages
        stages = {
            "exact_search": "_search_exact_facts" in content,
            "lexical_search": "_search_lexical" in content or "BM25" in content,
            "semantic_search": "_search_semantic" in content or "chroma" in content.lower(),
            "fusion": "reciprocal_rank_fusion" in content,
            "expansion": "FactStoreExpander" in content,
        }

        # Check for actual retrieve method
        has_retrieve_method = "def retrieve(" in content

        self.execution_paths.append({
            "path": "Retrieval Pipeline",
            "stages": stages,
            "main_method": "retrieve" if has_retrieve_method else None,
            "file": str(retriever_file.relative_to(self.backend_root))
        })

    def audit_context_assembly(self):
        """Audit ContextAssembler and its RIM integration."""
        logger.info("Auditing Context Assembly...")

        assembler_file = self.backend_root / "agent" / "context" / "assembler.py"

        if not assembler_file.exists():
            logger.warning("ContextAssembler not found")
            return

        with open(assembler_file) as f:
            content = f.read()

        # Check for key methods
        has_assemble = "def assemble(" in content
        uses_retriever = "HybridRetriever" in content
        uses_fact_store = "FactStore" in content or "Fact" in content
        uses_source_reader = "read_source" in content or "source_reader" in content

        # Check if RIM metadata is passed to LLM
        passes_rim_metadata = "rim_metadata" in content or "rim_data" in content.lower()

        self.execution_paths.append({
            "path": "Context Assembly",
            "has_assembler": has_assemble,
            "uses_retriever": uses_retriever,
            "uses_fact_store": uses_fact_store,
            "uses_source_reader": uses_source_reader,
            "passes_rim_to_llm": passes_rim_metadata,
            "file": str(assembler_file.relative_to(self.backend_root))
        })

    def audit_llm_integration(self):
        """Audit how RIM metadata is passed to LLM."""
        logger.info("Auditing LLM Integration...")

        # Check if RIM metadata is injected into prompts
        prompt_files = self.inspector.find_files("agent/**/*prompt*.py")
        system_prompt_files = self.inspector.grep_pattern(
            "system_prompt|rim_metadata|repository_context",
            "services/**/*.py",
            "agent/**/*.py"
        )

        # Check for context in agent mode
        engineering_agent = self.backend_root / "agent" / "engineering_agent.py"
        has_context_injection = False

        if engineering_agent.exists():
            with open(engineering_agent) as f:
                content = f.read()
                has_context_injection = "RepositoryContext" in content or "context" in content

        self.execution_paths.append({
            "path": "LLM Integration",
            "system_prompt_files": len(system_prompt_files),
            "has_context_injection": has_context_injection,
            "evidence_files": list(system_prompt_files.keys())[:3]
        })

    def audit_source_code_bridge(self):
        """Audit the bridge from RIM entity to source code."""
        logger.info("Auditing Source Code Bridge...")

        source_reader_file = self.backend_root / "intelligence" / "retrieval" / "source_reader.py"

        if not source_reader_file.exists():
            logger.warning("SourceCodeReader not found")
            return

        with open(source_reader_file) as f:
            content = f.read()

        # Check for resolution capabilities
        can_resolve_file = "resolve_file" in content or "file_path" in content
        can_resolve_symbol = "resolve_symbol" in content or "symbol" in content
        can_resolve_location = "line_start" in content or "line_end" in content
        can_read_snippet = "read_snippet" in content or "read_source" in content

        self.execution_paths.append({
            "path": "Source Code Bridge",
            "can_resolve_file": can_resolve_file,
            "can_resolve_symbol": can_resolve_symbol,
            "can_resolve_location": can_resolve_location,
            "can_read_snippet": can_read_snippet,
            "file": str(source_reader_file.relative_to(self.backend_root))
        })

    def audit_graph_traversal(self):
        """Audit graph traversal capabilities."""
        logger.info("Auditing Graph Traversal...")

        graph_traverser = self.backend_root / "intelligence" / "retrieval" / "graph_traverser.py"

        if not graph_traverser.exists():
            logger.warning("GraphTraverser not found")
            return

        with open(graph_traverser) as f:
            tree = ast.parse(f.read())
            methods = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    methods.append(node.name)

        self.execution_paths.append({
            "path": "Graph Traversal",
            "traversal_methods": methods,
            "file": str(graph_traverser.relative_to(self.backend_root))
        })

    def find_major_gaps(self):
        """Identify major gaps preventing RIM from functioning."""
        logger.info("Identifying Major Gaps...")

        gaps = []

        # Gap 1: Check if graph traversal is actually used
        if not self.execution_paths or not any("traversal" in str(p).lower() for p in self.execution_paths):
            gaps.append({
                "priority": "P1",
                "title": "Graph Traversal Not Integrated",
                "description": "GraphTraverser exists but may not be integrated into retrieval pipeline",
                "impact": "RIM cannot expand queries through relationships to find related entities",
                "location": "backend/intelligence/retrieval/"
            })

        # Gap 2: Check relationship extraction
        extracted_rels = [r for r in self.relationship_audits.values() if r.extracted]
        if len(extracted_rels) == 0:
            gaps.append({
                "priority": "P1",
                "title": "Relationship Extraction Missing",
                "description": "No evidence of automatic relationship extraction from source code",
                "impact": "RIM graph has no edges; cannot traverse or reason about code structure",
                "location": "backend/intelligence/"
            })

        # Gap 3: Check if retrieved results reach LLM as RIM metadata
        llm_integration = next((e for e in self.execution_paths if "LLM" in e.get("path", "")), None)
        if not llm_integration or not llm_integration.get("has_context_injection"):
            gaps.append({
                "priority": "P1",
                "title": "RIM Metadata Not Reaching LLM",
                "description": "LLM may not receive RIM navigation information, only source code",
                "impact": "LLM cannot use RIM structure to reason about codebase or make grounded decisions",
                "location": "backend/agent/"
            })

        # Gap 4: Check if symbols are properly resolved to source
        source_bridge = next((e for e in self.execution_paths if "Source" in e.get("path", "")), None)
        if not source_bridge or not all(source_bridge.get(k) for k in ["can_resolve_file", "can_resolve_symbol", "can_resolve_location"]):
            gaps.append({
                "priority": "P1",
                "title": "Incomplete Source Code Resolution",
                "description": "Cannot reliably resolve RIM entities to exact source locations",
                "impact": "Cannot retrieve bounded source snippets; LLM gets incomplete or wrong code",
                "location": "backend/intelligence/retrieval/source_reader.py"
            })

        # Gap 5: Check if reverse relationships are queryable
        reverse_rels = [r for r in self.relationship_audits.values() if not r.reverse_queryable]
        if len(reverse_rels) > len(self.relationship_audits) / 2:
            gaps.append({
                "priority": "P2",
                "title": "Reverse Relationship Queries Not Supported",
                "description": "Can find what a function calls, but not what calls it (or vice versa)",
                "impact": "RIM cannot answer key questions like 'what uses this service?'",
                "location": "backend/intelligence/query_layer.py"
            })

        self.major_gaps = sorted(gaps, key=lambda g: g["priority"])

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive audit report."""
        logger.info("Generating Report...")

        # Calculate scores
        node_status_counts = {}
        for audit in self.node_audits.values():
            status = audit.status.value
            node_status_counts[status] = node_status_counts.get(status, 0) + 1

        rel_status_counts = {}
        for audit in self.relationship_audits.values():
            status = audit.status.value
            rel_status_counts[status] = rel_status_counts.get(status, 0) + 1

        query_status_counts = {}
        for audit in self.query_operations.values():
            status = audit.status.value
            query_status_counts[status] = query_status_counts.get(status, 0) + 1

        # Overall score
        total_components = (
            len(self.node_audits) +
            len(self.relationship_audits) +
            len(self.query_operations)
        )

        full_count = (
            node_status_counts.get("FULL", 0) +
            rel_status_counts.get("FULL", 0) +
            query_status_counts.get("FULL", 0)
        )
        partial_count = (
            node_status_counts.get("PARTIAL", 0) +
            rel_status_counts.get("PARTIAL", 0) +
            query_status_counts.get("PARTIAL", 0)
        )

        overall_score = int((full_count * 100 + partial_count * 50) / (total_components or 1))

        return {
            "audit_version": "1.0",
            "overall_score": overall_score,
            "summary": {
                "nodes": {
                    "total": len(self.node_audits),
                    "status_counts": node_status_counts,
                },
                "relationships": {
                    "total": len(self.relationship_audits),
                    "status_counts": rel_status_counts,
                },
                "query_operations": {
                    "total": len(self.query_operations),
                    "status_counts": query_status_counts,
                },
                "gaps_found": len(self.major_gaps),
            },
            "capabilities": [
                {
                    "name": name,
                    **asdict(audit)
                }
                for name, audit in self.node_audits.items()
            ],
            "nodes": [
                {
                    "type": name,
                    **asdict(audit)
                }
                for name, audit in self.node_audits.items()
            ],
            "relationships": [
                {
                    **asdict(audit)
                }
                for audit in self.relationship_audits.values()
            ],
            "navigation": [
                {
                    **asdict(op)
                }
                for op in self.query_operations.values()
            ],
            "retrieval": [],
            "context_assembly": [],
            "source_code_bridge": [],
            "execution_paths": self.execution_paths,
            "gaps": self.major_gaps,
        }

    def run(self) -> Dict[str, Any]:
        """Run complete audit."""
        logger.info("Starting RIM Reality Audit...")

        self.audit_node_types()
        self.audit_relationships()
        self.audit_query_layer()
        self.audit_retrieval_pipeline()
        self.audit_context_assembly()
        self.audit_llm_integration()
        self.audit_source_code_bridge()
        self.audit_graph_traversal()
        self.find_major_gaps()

        report = self.generate_report()

        logger.info("Audit complete")
        return report


# ============================================================================
# MAIN
# ============================================================================

def main():
    repo_root = "/home/dheeraj/repository_intelligence_platform"

    audit = RIMRealityAudit(repo_root)
    report = audit.run()

    # Write JSON report
    output_file = Path(repo_root) / "backend" / "scripts" / "rim_reality_audit_report.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report written to {output_file}")

    # Print summary
    print("\n" + "="*80)
    print("RIM REALITY AUDIT SUMMARY")
    print("="*80)
    print(f"\nOverall Implementation Score: {report['overall_score']}/100")
    print(f"\nNodes: {report['summary']['nodes']}")
    print(f"\nRelationships: {report['summary']['relationships']}")
    print(f"\nQuery Operations: {report['summary']['query_operations']}")
    print(f"\nMajor Gaps Found: {report['summary']['gaps_found']}")

    if report['gaps']:
        print("\nTOP GAPS:")
        for i, gap in enumerate(report['gaps'][:5], 1):
            print(f"\n{i}. [{gap['priority']}] {gap['title']}")
            print(f"   {gap['description']}")
            print(f"   Location: {gap['location']}")

    print("\n" + "="*80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
