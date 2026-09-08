#!/usr/bin/env python3
"""
GATE 3 — Tools Test Harness

Provides commands to test every repository-inspection/query tool
against real GitOnboard test cases.

After GATE 1 and GATE 2 pass, use this to:
- Run query tools (find files, find symbols, search relationships)
- Test graph navigation
- Verify retrieval
- Test context assembly
- Run end-to-end repository inspection

Usage:
    python gate3_tools_harness.py <analysis_id> <test_case> [args]

Test Cases:
    - find_files <pattern>
    - find_symbols <pattern>
    - find_relationships <source_id>
    - graph_neighbors <symbol_id>
    - retrieval_search <query>
    - context_assembly <symbol_id>
"""

import sys
import json
from typing import Dict, List, Any
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import and_
from backend.database import SessionLocal
from backend.models.repository import Analysis
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship


class Gate3ToolsHarness:
    def __init__(self, analysis_id: int):
        self.analysis_id = analysis_id
        self.db = SessionLocal()
        self.analysis = self.db.query(Analysis).filter(Analysis.id == analysis_id).first()

        if not self.analysis:
            raise ValueError(f"Analysis {analysis_id} not found")

    def find_files(self, pattern: str) -> List[Dict]:
        """Find files matching pattern"""
        print(f"\nTEST: find_files('{pattern}')")
        print(f"{'─'*60}")

        files = self.db.query(FactFile).filter(
            and_(
                FactFile.analysis_id == self.analysis_id,
                FactFile.path.ilike(f"%{pattern}%")
            )
        ).all()

        results = [
            {
                'id': f.id,
                'path': f.path,
                'size': f.size,
                'blob_name': f.blob_name
            }
            for f in files
        ]

        print(f"Found {len(results)} files matching '{pattern}':")
        for r in results[:10]:
            print(f"  - {r['path']} ({r['size']} bytes)")
        if len(results) > 10:
            print(f"  ... and {len(results) - 10} more")

        return results

    def find_symbols(self, pattern: str) -> List[Dict]:
        """Find symbols matching pattern"""
        print(f"\nTEST: find_symbols('{pattern}')")
        print(f"{'─'*60}")

        symbols = self.db.query(FactSymbol).filter(
            and_(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.name.ilike(f"%{pattern}%")
            )
        ).all()

        results = [
            {
                'id': s.id,
                'name': s.name,
                'type': s.symbol_type,
                'qualified_name': s.qualified_name,
                'file_id': s.file_id,
                'lines': f"{s.line_start}-{s.line_end}"
            }
            for s in symbols
        ]

        print(f"Found {len(results)} symbols matching '{pattern}':")
        for r in results[:10]:
            print(f"  - {r['qualified_name']} ({r['type']}) @ {r['lines']}")
        if len(results) > 10:
            print(f"  ... and {len(results) - 10} more")

        return results

    def find_relationships(self, source_id: str) -> List[Dict]:
        """Find relationships from a symbol"""
        print(f"\nTEST: find_relationships('{source_id}')")
        print(f"{'─'*60}")

        # First get the symbol
        source = self.db.query(FactSymbol).filter(FactSymbol.id == source_id).first()
        if not source:
            print(f"  ✗ Symbol {source_id} not found")
            return []

        print(f"  Source: {source.qualified_name} ({source.symbol_type})")

        # Find outgoing relationships
        rels = self.db.query(FactRelationship).filter(
            and_(
                FactRelationship.analysis_id == self.analysis_id,
                FactRelationship.from_symbol_id == source_id
            )
        ).all()

        results = []
        print(f"\n  Relationships ({len(rels)} total):")
        for r in rels:
            target = self.db.query(FactSymbol).filter(FactSymbol.id == r.to_symbol_id).first()
            result = {
                'from_symbol_id': r.from_symbol_id,
                'to_symbol_id': r.to_symbol_id,
                'rel_type': r.rel_type,
                'target_name': target.qualified_name if target else 'UNKNOWN'
            }
            results.append(result)
            print(f"    -{r.rel_type}-> {target.qualified_name if target else 'UNKNOWN'}")

        return results

    def graph_neighbors(self, symbol_id: str, depth: int = 1) -> Dict:
        """Navigate graph neighbors"""
        print(f"\nTEST: graph_neighbors('{symbol_id}', depth={depth})")
        print(f"{'─'*60}")

        symbol = self.db.query(FactSymbol).filter(FactSymbol.id == symbol_id).first()
        if not symbol:
            print(f"  ✗ Symbol {symbol_id} not found")
            return {}

        print(f"  Center: {symbol.qualified_name}\n")

        # Outgoing
        out_rels = self.db.query(FactRelationship).filter(
            and_(
                FactRelationship.analysis_id == self.analysis_id,
                FactRelationship.from_symbol_id == symbol_id
            )
        ).all()

        # Incoming
        in_rels = self.db.query(FactRelationship).filter(
            and_(
                FactRelationship.analysis_id == self.analysis_id,
                FactRelationship.to_symbol_id == symbol_id
            )
        ).all()

        print(f"  Outgoing ({len(out_rels)} relationships):")
        for r in out_rels[:5]:
            target = self.db.query(FactSymbol).filter(FactSymbol.id == r.to_symbol_id).first()
            print(f"    -{r.rel_type}-> {target.qualified_name if target else 'UNKNOWN'}")

        print(f"\n  Incoming ({len(in_rels)} relationships):")
        for r in in_rels[:5]:
            source = self.db.query(FactSymbol).filter(FactSymbol.id == r.from_symbol_id).first()
            print(f"    <-{r.rel_type}- {source.qualified_name if source else 'UNKNOWN'}")

        return {
            'symbol': symbol.qualified_name,
            'outgoing_count': len(out_rels),
            'incoming_count': len(in_rels)
        }

    def retrieval_search(self, query: str) -> List[Dict]:
        """Search using retrieval (lexical)"""
        print(f"\nTEST: retrieval_search('{query}')")
        print(f"{'─'*60}")

        # Simple lexical search across symbols and file names
        symbol_results = self.db.query(FactSymbol).filter(
            and_(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.qualified_name.ilike(f"%{query}%")
            )
        ).all()

        file_results = self.db.query(FactFile).filter(
            and_(
                FactFile.analysis_id == self.analysis_id,
                FactFile.path.ilike(f"%{query}%")
            )
        ).all()

        results = [
            {'type': 'symbol', 'name': s.qualified_name, 'id': s.id}
            for s in symbol_results
        ] + [
            {'type': 'file', 'name': f.path, 'id': f.id}
            for f in file_results
        ]

        print(f"Found {len(results)} results for '{query}':")
        for r in results[:10]:
            print(f"  [{r['type']}] {r['name']}")
        if len(results) > 10:
            print(f"  ... and {len(results) - 10} more")

        return results

    def context_assembly(self, symbol_id: str) -> Dict:
        """Assemble context around a symbol"""
        print(f"\nTEST: context_assembly('{symbol_id}')")
        print(f"{'─'*60}")

        symbol = self.db.query(FactSymbol).filter(FactSymbol.id == symbol_id).first()
        if not symbol:
            print(f"  ✗ Symbol {symbol_id} not found")
            return {}

        # Get file
        file = self.db.query(FactFile).filter(FactFile.id == symbol.file_id).first()

        # Get relationships
        outgoing = self.db.query(FactRelationship).filter(
            FactRelationship.from_symbol_id == symbol_id
        ).all()
        incoming = self.db.query(FactRelationship).filter(
            FactRelationship.to_symbol_id == symbol_id
        ).all()

        context = {
            'symbol': {
                'id': symbol.id,
                'name': symbol.name,
                'qualified_name': symbol.qualified_name,
                'type': symbol.symbol_type,
                'lines': f"{symbol.line_start}-{symbol.line_end}"
            },
            'file': {
                'id': symbol.file_id,
                'path': file.path if file else 'UNKNOWN',
                'size': file.size if file else 0
            },
            'relationships': {
                'outgoing_count': len(outgoing),
                'incoming_count': len(incoming),
                'outgoing_types': list(set(r.rel_type for r in outgoing)),
                'incoming_types': list(set(r.rel_type for r in incoming))
            }
        }

        print(f"\n  Symbol: {context['symbol']['qualified_name']}")
        print(f"  File: {context['file']['path']}")
        print(f"  Type: {context['symbol']['type']}")
        print(f"  Location: {context['symbol']['lines']}")
        print(f"\n  Relationships:")
        print(f"    Outgoing: {context['relationships']['outgoing_count']}")
        print(f"    Incoming: {context['relationships']['incoming_count']}")

        return context

    def run_test(self, test_case: str, *args):
        """Run a test case"""
        handlers = {
            'find_files': self.find_files,
            'find_symbols': self.find_symbols,
            'find_relationships': self.find_relationships,
            'graph_neighbors': self.graph_neighbors,
            'retrieval_search': self.retrieval_search,
            'context_assembly': self.context_assembly,
        }

        if test_case not in handlers:
            print(f"Unknown test case: {test_case}")
            print(f"Available: {', '.join(handlers.keys())}")
            return None

        handler = handlers[test_case]
        try:
            result = handler(*args)
            print(f"\n✓ Test passed\n")
            return result
        except Exception as e:
            print(f"\n✗ Test failed: {e}\n")
            import traceback
            traceback.print_exc()
            return None


def main():
    if len(sys.argv) < 3:
        print("GATE 3 — Tools Test Harness")
        print("\nUsage: python gate3_tools_harness.py <analysis_id> <test_case> [args]\n")
        print("Available Test Cases:")
        print("  find_files <pattern>           - Find files matching pattern")
        print("  find_symbols <pattern>         - Find symbols matching pattern")
        print("  find_relationships <symbol_id> - Find relationships from symbol")
        print("  graph_neighbors <symbol_id>    - Navigate graph around symbol")
        print("  retrieval_search <query>       - Search using lexical retrieval")
        print("  context_assembly <symbol_id>   - Assemble context around symbol")
        print("\nExamples:")
        print("  python gate3_tools_harness.py 7 find_files 'backend'")
        print("  python gate3_tools_harness.py 7 find_symbols 'process'")
        print("  python gate3_tools_harness.py 7 context_assembly '7:urn:function:...'")
        sys.exit(1)

    analysis_id = int(sys.argv[1])
    test_case = sys.argv[2]
    test_args = sys.argv[3:]

    harness = Gate3ToolsHarness(analysis_id)
    result = harness.run_test(test_case, *test_args)

    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
