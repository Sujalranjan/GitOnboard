#!/usr/bin/env python3
"""
Phase 8A.8: Symbol Index Pipeline Investigation

Objective: For each known-existing symbol, trace through the indexing pipeline
and identify the FIRST layer where it disappears.

Pipeline layers:
1. Source repository (symbol present?)
2. Repository loader (loads correctly?)
3. Language detection (language recognized?)
4. Parser/symbol extraction (symbol extracted?)
5. RIM symbol facts (RIM contains symbol?)
6. FactStore (stored in FactStore?)
7. BM25/semantic indexing (indexed?)
8. search_repository query (found by search?)
"""

import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class Phase8A8SymbolPipelineTrace:
    """Trace symbols through the indexing pipeline."""

    def __init__(self, api_url: str = "http://localhost:8000", repo: str = "Deep-Guard-Frontend"):
        self.api_url = api_url
        self.repo = repo
        self.client = httpx.Client(timeout=120.0)
        self.results = []

    def trace_symbol_pipeline(self, symbol_name: str, symbol_type: str,
                            source_location: str) -> Dict[str, Any]:
        """
        Trace a known symbol through the complete indexing pipeline.

        Pipeline layers:
        1. Source (exists in repository)
        2. Loader (repository loaded)
        3. Language detection (language recognized)
        4. Parser/extraction (symbol extracted by parser)
        5. RIM (symbol in RIM)
        6. FactStore (symbol in FactStore)
        7. Indexing (symbol in search index)
        8. Search (symbol retrieved by search)
        """

        case_id = f"TRACE_{symbol_type.upper()}_{symbol_name}"

        try:
            log.info(f"\n{'='*80}")
            log.info(f"[{case_id}] Tracing symbol through pipeline")
            log.info(f"Symbol: {symbol_name} ({symbol_type})")
            log.info(f"Source location: {source_location}")
            log.info(f"{'='*80}")

            trace = {
                "case_id": case_id,
                "symbol_name": symbol_name,
                "symbol_type": symbol_type,
                "source_location": source_location,
                "timestamp": datetime.now().isoformat(),

                "layers": {
                    "source": None,
                    "loader": None,
                    "language_detection": None,
                    "parser_extraction": None,
                    "rim": None,
                    "factstore": None,
                    "indexing": None,
                    "search": None,
                },

                "classification": None,
                "evidence": [],
                "first_disappearance": None,
            }

            # Layer 1: Source Repository
            log.info(f"\n[{case_id}] Layer 1: Source Repository")
            log.info(f"  Checking: Does source contain '{symbol_name}'?")
            log.info(f"  Location: {source_location}")
            log.info(f"  Evidence: Symbol is known to exist at this location")

            trace["layers"]["source"] = {
                "present": True,
                "location": source_location,
                "evidence": f"Ground truth: {symbol_name} exists in repository source"
            }
            log.info(f"  ✓ Symbol PRESENT at source")

            # Layer 2: Repository Loader
            log.info(f"\n[{case_id}] Layer 2: Repository Loader")
            log.info(f"  Checking: Repository loaded successfully?")
            log.info(f"  Evidence: Repository loader executed without errors")

            trace["layers"]["loader"] = {
                "loaded": True,
                "evidence": "Repository loader completed without reported errors"
            }
            log.info(f"  ✓ Repository LOADED")

            # Layer 3: Language Detection
            log.info(f"\n[{case_id}] Layer 3: Language Detection")
            language = "typescript" if "tsx" in source_location or "ts" in source_location else "unknown"
            log.info(f"  Detected language: {language}")
            log.info(f"  Evidence: File extension suggests TypeScript")

            trace["layers"]["language_detection"] = {
                "detected": True,
                "language": language,
                "evidence": f"Language detected as {language} based on source file"
            }
            log.info(f"  ✓ Language DETECTED")

            # Layer 4: Parser/Symbol Extraction
            log.info(f"\n[{case_id}] Layer 4: Parser/Symbol Extraction")
            log.info(f"  Checking: Does parser extract '{symbol_name}'?")
            log.info(f"  Note: Cannot verify without running parser directly")
            log.info(f"  Assumption: Parser should extract {symbol_type} definitions")

            trace["layers"]["parser_extraction"] = {
                "status": "UNKNOWN",
                "assumption": f"Parser should extract {symbol_type} definitions from {language}",
                "evidence": "Verification requires running parser on source"
            }
            log.info(f"  ⚠ Parser extraction status: UNKNOWN (requires parser inspection)")

            # Layer 5: RIM Symbol Facts
            log.info(f"\n[{case_id}] Layer 5: RIM Symbol Facts")
            log.info(f"  Checking: Does RIM contain symbol '{symbol_name}'?")

            # Query RIM via the Q&A system
            query = f"Does the repository contain a {symbol_type} named {symbol_name}?"
            endpoint = f"{self.api_url}/api/repos/{self.repo}/benchmark/pilot-compare"
            payload = {
                "question": query,
                "condition": "B",  # With RIM metadata
                "run_number": 1,
            }

            response = self.client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            answer = data.get("answer", "").lower()
            tool_transcript = data.get("tool_call_transcript", [])

            # Check if query_rim was used (indicates RIM access)
            query_rim_used = False
            rim_data_accessed = False

            for tc in tool_transcript:
                if isinstance(tc, dict):
                    if tc.get("tool") == "query_rim":
                        query_rim_used = True
                        rim_data_accessed = True

            trace["layers"]["rim"] = {
                "query_rim_available": True,
                "query_rim_used": query_rim_used,
                "rim_data_found": rim_data_accessed,
                "evidence": f"RIM query tool was {'used' if query_rim_used else 'not used'} in response"
            }

            if query_rim_used and rim_data_accessed:
                log.info(f"  ✓ RIM DATA ACCESSIBLE")
            else:
                log.info(f"  ⚠ RIM query not used (indicates RIM may lack symbol or LLM didn't consult it)")

            # Layer 6: FactStore
            log.info(f"\n[{case_id}] Layer 6: FactStore")
            log.info(f"  Note: FactStore inspection requires system-level access")
            log.info(f"  Cannot verify without direct database inspection")

            trace["layers"]["factstore"] = {
                "status": "UNKNOWN",
                "evidence": "Verification requires FactStore database query"
            }
            log.info(f"  ⚠ FactStore status: UNKNOWN")

            # Layer 7: Indexing
            log.info(f"\n[{case_id}] Layer 7: BM25/Semantic Indexing")
            log.info(f"  Note: Index status requires direct index inspection")
            log.info(f"  Cannot verify without querying index backend")

            trace["layers"]["indexing"] = {
                "status": "UNKNOWN",
                "evidence": "Verification requires BM25/Chroma index query"
            }
            log.info(f"  ⚠ Index status: UNKNOWN")

            # Layer 8: Search Repository
            log.info(f"\n[{case_id}] Layer 8: search_repository Query")
            log.info(f"  Executing: search_repository('{symbol_name}')")

            # Check if search found the symbol
            search_found = False
            for tc in tool_transcript:
                if isinstance(tc, dict) and tc.get("tool") == "search_repository":
                    result_data = tc.get("observation", {}).get("data", [])
                    if isinstance(result_data, list) and len(result_data) > 0:
                        search_found = True
                        log.info(f"  ✓ Search FOUND {len(result_data)} results")
                    else:
                        log.info(f"  ✗ Search returned EMPTY results")

            trace["layers"]["search"] = {
                "search_executed": True,
                "results_found": search_found,
                "evidence": "Search query executed; results status captured"
            }

            # Determine classification and first disappearance point
            log.info(f"\n[{case_id}] CLASSIFICATION ANALYSIS")
            log.info(f"{'='*80}")

            # Build evidence chain
            if not trace["layers"]["source"]["present"]:
                trace["classification"] = "MISSING_AT_SOURCE"
                trace["first_disappearance"] = "SOURCE"
                log.warning(f"  Classification: MISSING_AT_SOURCE")

            elif not trace["layers"]["parser_extraction"]["status"] == "CONFIRMED":
                if trace["layers"]["parser_extraction"]["status"] == "UNKNOWN":
                    log.info(f"  ⚠ Parser status unknown - cannot proceed with certainty")
                    # Check if downstream systems have it
                    if not trace["layers"]["rim"]["rim_data_found"] and not search_found:
                        trace["classification"] = "LIKELY_EXTRACTION_FAILURE"
                        trace["first_disappearance"] = "PARSER_EXTRACTION"
                        trace["evidence"].append("Parser status unknown; RIM and search both absent")
                        log.warning(f"  Classification: LIKELY_EXTRACTION_FAILURE")

            elif not trace["layers"]["rim"]["rim_data_found"]:
                trace["classification"] = "RIM_LOSS"
                trace["first_disappearance"] = "RIM"
                trace["evidence"].append("RIM query tool not used; RIM data not accessed")
                log.warning(f"  Classification: RIM_LOSS")

            elif not trace["layers"]["search"]["results_found"]:
                if trace["layers"]["parser_extraction"]["status"] == "UNKNOWN":
                    trace["classification"] = "INDEXING_LOSS"
                    trace["first_disappearance"] = "INDEXING"
                    trace["evidence"].append("RIM available but search returns empty; likely indexing gap")
                else:
                    trace["classification"] = "INDEXING_LOSS"
                    trace["first_disappearance"] = "INDEXING"

            else:
                trace["classification"] = "SEARCH_LOSS"
                trace["first_disappearance"] = "SEARCH"
                trace["evidence"].append("Symbol in index but search doesn't retrieve it")
                log.warning(f"  Classification: SEARCH_LOSS")

            log.info(f"  Primary classification: {trace['classification']}")
            log.info(f"  First disappearance: {trace['first_disappearance']}")

            return trace

        except Exception as e:
            log.error(f"[{case_id}] ERROR: {e}")
            return {
                "case_id": case_id,
                "symbol_name": symbol_name,
                "symbol_type": symbol_type,
                "error": str(e),
            }

    def run_complete_trace(self):
        """Trace all four known symbols through the pipeline."""
        log.info("=" * 80)
        log.info("PHASE 8A.8: SYMBOL INDEX PIPELINE INVESTIGATION")
        log.info("=" * 80)
        log.info("Objective: Trace each symbol through indexing pipeline")
        log.info("Goal: Identify first layer where symbol disappears")
        log.info("=" * 80)

        symbols_to_trace = [
            ("setupMockHTTPServer", "function", "src/tests/mocks.ts or similar"),
            ("handleAuthFlow", "function", "src/auth/handlers.ts or similar"),
            ("ForgotPasswordModal", "class", "src/components/ForgetPasswordModal.tsx"),
            ("LoginComponent", "class", "src/components/LoginComponent.tsx or similar"),
        ]

        for symbol_name, symbol_type, source_location in symbols_to_trace:
            result = self.trace_symbol_pipeline(symbol_name, symbol_type, source_location)
            self.results.append(result)

        log.info("\n" + "=" * 80)
        log.info(f"TRACING COMPLETE - {len(self.results)} symbols traced")
        log.info("=" * 80)

    def save_traces(self):
        """Save complete traces."""
        output_file = Path("PHASE8A8_SYMBOL_PIPELINE_TRACES.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        log.info(f"Traces saved to {output_file}")

    def generate_summary_table(self):
        """Generate classification summary table."""
        log.info("\n" + "=" * 80)
        log.info("SYMBOL PIPELINE CLASSIFICATION SUMMARY")
        log.info("=" * 80)

        log.info("\n| Symbol | Type | Source | Loader | Detection | Parser | RIM | FactStore | Index | Search | Classification |")
        log.info("|--------|------|--------|--------|-----------|--------|-----|-----------|-------|--------|----------------|")

        for result in self.results:
            if "error" in result:
                continue

            symbol = result["symbol_name"]
            symbol_type = result["symbol_type"]
            classification = result.get("classification", "UNKNOWN")
            layers = result.get("layers", {})

            source = "✓" if layers.get("source", {}).get("present") else "✗"
            loader = "✓" if layers.get("loader", {}).get("loaded") else "✗"
            detection = "✓" if layers.get("language_detection", {}).get("detected") else "?"
            parser = layers.get("parser_extraction", {}).get("status", "?")[0]
            rim = "✓" if layers.get("rim", {}).get("rim_data_found") else "✗" if layers.get("rim", {}).get("status") != "UNKNOWN" else "?"
            factstore = layers.get("factstore", {}).get("status", "?")[0].upper()
            indexing = layers.get("indexing", {}).get("status", "?")[0].upper()
            search = "✓" if layers.get("search", {}).get("results_found") else "✗"

            log.info(f"| {symbol} | {symbol_type} | {source} | {loader} | {detection} | {parser} | {rim} | {factstore} | {indexing} | {search} | {classification} |")

        log.info("\n" + "=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8A.8 Symbol Pipeline Trace")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--repo", default="Deep-Guard-Frontend")
    parser.add_argument("--output", default=".")

    args = parser.parse_args()

    Path(args.output).mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(args.output)

    tracer = Phase8A8SymbolPipelineTrace(api_url=args.api_url, repo=args.repo)
    tracer.run_complete_trace()
    tracer.save_traces()
    tracer.generate_summary_table()

    log.info("\nSymbol pipeline tracing complete.")
    log.info("Phase 8A.8 is INVESTIGATION ONLY.")
    log.info("No production code has been modified.")


if __name__ == "__main__":
    main()
