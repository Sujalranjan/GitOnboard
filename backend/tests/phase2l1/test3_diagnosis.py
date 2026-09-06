#!/usr/bin/env python
"""
TEST 3 DIAGNOSIS: Complete instrumentation of authentication exploration flow.

Logs every step for all 11 files to identify exact failure point.
"""
import logging
import json
import sys
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.inspection.file_inspector import inspect_file

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def diagnose_test3():
    """Diagnose TEST 3 with full instrumentation."""
    db = SessionLocal()
    project_root = Path(__file__).parent.parent.parent.parent

    # Get latest analysis
    analysis = (
        db.query(Analysis)
        .filter(Analysis.repository_id == 84712003)
        .order_by(Analysis.id.desc())
        .first()
    )

    if not analysis:
        logger.error("No analysis found")
        return

    logger.info(f"\n{'='*80}")
    logger.info(f"TEST 3 DIAGNOSIS: Authentication Exploration")
    logger.info(f"Analysis ID: {analysis.id}, Status: {analysis.status}")
    logger.info(f"Repository: 846 files, 9451 symbols")
    logger.info(f"{'='*80}\n")

    # Step 1: Retrieve across multiple keywords
    keywords = ["auth", "login", "jwt", "oauth", "session", "middleware"]
    all_results = []

    logger.info("STEP 1: RETRIEVAL ACROSS KEYWORDS")
    logger.info("-" * 80)

    retriever = HybridRetriever(
        db=db,
        analysis_id=analysis.id,
        chroma_collection=None
    )

    for keyword in keywords:
        logger.info(f"\nRetrieving for keyword: '{keyword}'")
        ret_results = retriever.retrieve(keyword, top_k=3)
        logger.info(f"  Found: {len(ret_results)} results")

        for idx, ret_result in enumerate(ret_results):
            logger.info(f"    [{idx}] {ret_result.file_path} (score: {ret_result.score:.3f})")
            all_results.append(ret_result)

    # Deduplicate
    unique_files = list(set(r.file_path for r in all_results))
    logger.info(f"\n✓ Total unique files across keywords: {len(unique_files)}")

    # Step 2: Detailed diagnosis for each file
    logger.info(f"\n{'='*80}")
    logger.info("STEP 2: FILE-BY-FILE DIAGNOSIS")
    logger.info(f"{'='*80}\n")

    diagnosis_results = []

    for file_idx, file_path in enumerate(unique_files, 1):
        logger.info(f"\n[FILE {file_idx}/{len(unique_files)}] {file_path}")
        logger.info("-" * 80)

        file_diagnosis = {
            "index": file_idx,
            "path": file_path,
            "steps": []
        }

        # STEP 2A: Check if file exists in analysis
        logger.info("  Step 2A: Check FactFile in database...")
        fact_file = (
            db.query(FactFile)
            .filter(
                FactFile.analysis_id == analysis.id,
                FactFile.path == file_path,
            )
            .first()
        )

        if fact_file:
            logger.info(f"    ✓ Found in database")
            logger.info(f"      ID: {fact_file.id}")
            logger.info(f"      Size: {fact_file.size} bytes")
            logger.info(f"      Language: {fact_file.language}")
            file_diagnosis["steps"].append({
                "step": "2A_fact_file_lookup",
                "result": "FOUND",
                "fact_file_id": fact_file.id,
                "size": fact_file.size,
                "language": fact_file.language,
            })
        else:
            logger.warning(f"    ✗ NOT FOUND in FactFile")
            file_diagnosis["steps"].append({
                "step": "2A_fact_file_lookup",
                "result": "NOT_FOUND",
            })
            diagnosis_results.append(file_diagnosis)
            continue  # Skip to next file

        # STEP 2B: Count symbols in database
        logger.info("  Step 2B: Count symbols in database...")
        symbol_count_db = (
            db.query(FactSymbol)
            .filter(FactSymbol.file_id == fact_file.id)
            .count()
        )

        logger.info(f"    Found {symbol_count_db} symbols in database")
        file_diagnosis["steps"].append({
            "step": "2B_symbol_count_db",
            "count": symbol_count_db,
        })

        # STEP 2C: Call inspect_file with analysis_id
        logger.info("  Step 2C: Call inspect_file(path, analysis_id=...)...")

        inspect_call_args = {
            "file_path": file_path,
            "db": "SessionLocal()",
            "repo_root": str(project_root),
            "analysis_id": analysis.id,
        }
        logger.info(f"    Arguments: {inspect_call_args}")

        try:
            file_info = inspect_file(
                file_path,
                db=db,
                repo_root=str(project_root),
                analysis_id=analysis.id
            )

            logger.info(f"    ✓ inspect_file() succeeded")
            logger.info(f"      Success: {file_info.success}")
            logger.info(f"      Language: {file_info.language}")
            logger.info(f"      Symbols returned: {len(file_info.symbols)}")

            if file_info.symbols:
                logger.info(f"      First 3 symbols:")
                for sym in file_info.symbols[:3]:
                    logger.info(f"        - {sym.name} (line {sym.line_start}-{sym.line_end})")
            else:
                logger.warning(f"      WARNING: No symbols returned despite {symbol_count_db} in DB!")

            file_diagnosis["steps"].append({
                "step": "2C_inspect_file",
                "result": "SUCCESS",
                "success": file_info.success,
                "symbols_returned": len(file_info.symbols),
                "language": file_info.language,
                "error": file_info.error if not file_info.success else None,
            })

        except Exception as e:
            logger.error(f"    ✗ inspect_file() raised exception: {e}")
            file_diagnosis["steps"].append({
                "step": "2C_inspect_file",
                "result": "EXCEPTION",
                "error": str(e),
            })

        # STEP 2D: Summary
        logger.info(f"  Summary for {file_path}:")
        logger.info(f"    DB count: {symbol_count_db}")
        try:
            symbols_returned = len(file_info.symbols)
        except:
            symbols_returned = -1

        if symbol_count_db > 0 and symbols_returned == 0:
            logger.error(f"    ⚠️ MISMATCH: {symbol_count_db} symbols in DB, 0 returned by inspect_file()")
            file_diagnosis["verdict"] = "SILENT_FAILURE"
        elif symbol_count_db == 0 and symbols_returned == 0:
            logger.warning(f"    File has no symbols (valid)")
            file_diagnosis["verdict"] = "VALID_EMPTY"
        elif symbols_returned > 0:
            logger.info(f"    ✓ Symbols correctly retrieved: {symbols_returned}")
            file_diagnosis["verdict"] = "SUCCESS"
        else:
            logger.error(f"    ? Cannot determine verdict")
            file_diagnosis["verdict"] = "UNKNOWN"

        diagnosis_results.append(file_diagnosis)

    # STEP 3: Summary
    logger.info(f"\n{'='*80}")
    logger.info("STEP 3: SUMMARY")
    logger.info(f"{'='*80}\n")

    verdicts = {}
    for result in diagnosis_results:
        verdict = result.get("verdict", "UNKNOWN")
        verdicts[verdict] = verdicts.get(verdict, 0) + 1

    logger.info("Verdict distribution:")
    for verdict, count in sorted(verdicts.items()):
        logger.info(f"  {verdict}: {count} files")

    # Detailed problems
    problems = [r for r in diagnosis_results if r.get("verdict") in ["SILENT_FAILURE", "UNKNOWN"]]
    if problems:
        logger.error(f"\n⚠️ PROBLEMS FOUND ({len(problems)} files):")
        for problem in problems:
            logger.error(f"  - {problem['path']}: {problem.get('verdict')}")

    # Save detailed results
    output = {
        "timestamp": str(Path(__file__).parent / "test3_diagnosis_results.json"),
        "analysis_id": analysis.id,
        "unique_files": len(unique_files),
        "verdicts": verdicts,
        "details": diagnosis_results
    }

    output_path = Path(__file__).parent / "test3_diagnosis_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"\n✓ Detailed results saved to: {output_path}")

    return verdicts, diagnosis_results


if __name__ == "__main__":
    verdicts, results = diagnose_test3()

    # Exit code based on findings
    silent_failures = [r for r in results if r.get("verdict") == "SILENT_FAILURE"]

    if silent_failures:
        print(f"\n❌ DIAGNOSIS COMPLETE: {len(silent_failures)} silent failures found")
        sys.exit(1)
    else:
        print(f"\n✓ DIAGNOSIS COMPLETE: No silent failures detected")
        sys.exit(0)
