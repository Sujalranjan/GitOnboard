#!/usr/bin/env python3
"""
Phase 8A.9: Direct Parser Inspection

Execute the actual symbol extraction pipeline on Deep-Guard-Frontend
and compare extracted symbols with source code.

Objective: Determine if parser/extraction is the first confirmed disappearance point.
"""

import json
import sys
from pathlib import Path

# Import the actual extraction infrastructure
from backend.intelligence.engine.analyzers.symbol import SymbolAnalyzer
from backend.intelligence.engine.parser.providers.typescript import TypeScriptProvider
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.enums import EntityType

def run_parser_on_file(file_path: str) -> dict:
    """Run the actual parser/extraction on a single file."""
    try:
        # Read source
        with open(file_path, 'r') as f:
            source = f.read()

        # Parse using TypeScript provider
        parsed = TypeScriptProvider.parse(source, file_path)

        # Extract symbols using SymbolAnalyzer
        entities, relationships = SymbolAnalyzer.analyze(parsed, file_path)

        # Return results
        return {
            "file": file_path,
            "source_size": len(source),
            "parser_error": None,
            "entities_extracted": [
                {
                    "name": e.name,
                    "type": e.type.name if hasattr(e.type, 'name') else str(e.type),
                    "qualified_name": e.qualified_name,
                }
                for e in entities
            ],
            "entity_count": len(entities),
            "success": True,
        }
    except Exception as e:
        return {
            "file": file_path,
            "parser_error": str(e),
            "success": False,
        }

def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    log = logging.getLogger(__name__)

    log.info("=" * 80)
    log.info("PHASE 8A.9: DIRECT PARSER INSPECTION")
    log.info("=" * 80)
    log.info("Executing actual symbol extraction on Deep-Guard-Frontend source files")
    log.info("=" * 80)

    # Sample files to inspect
    sample_files = [
        "/home/dheeraj/Deep-Guard/Deep-Guard-Frontend/src/components/ImageAnalysisSection.tsx",
        "/home/dheeraj/Deep-Guard/Deep-Guard-Frontend/src/components/AccountDataManagement.tsx",
        "/home/dheeraj/Deep-Guard/Deep-Guard-Frontend/lib/auth.ts",
    ]

    results = []

    for file_path in sample_files:
        if not Path(file_path).exists():
            log.warning(f"File not found: {file_path}")
            continue

        log.info(f"\nParsing: {file_path}")
        result = run_parser_on_file(file_path)
        results.append(result)

        if result["success"]:
            log.info(f"  ✓ Parser executed successfully")
            log.info(f"  Entities extracted: {result['entity_count']}")
            if result["entity_count"] > 0:
                log.info(f"  Sample entities:")
                for entity in result["entities_extracted"][:5]:
                    log.info(f"    - {entity['name']} ({entity['type']})")
        else:
            log.warning(f"  ✗ Parser error: {result['parser_error']}")

    # Save results
    output_file = Path("PHASE8A9_PARSER_INSPECTION_RESULTS.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"\nResults saved to {output_file}")

    log.info("\n" + "=" * 80)
    log.info("PARSER INSPECTION COMPLETE")
    log.info("=" * 80)

if __name__ == "__main__":
    main()
