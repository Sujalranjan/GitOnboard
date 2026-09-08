#!/usr/bin/env python3
"""
GATE 2 — Symbol Extraction Verification

For sampled Python/JS/TS/JSX files, verify:
- Source location → extracted RIM symbol → FactSymbol record
- Line boundaries match actual source code
- Functions, classes, methods, components are correctly captured

This allows manual verification against actual repository source.
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.repository import Analysis, Repository
from backend.models.fact_store import FactFile, FactSymbol
from backend.intelligence.parser import LanguageParser

@dataclass
class SymbolVerification:
    file_path: str
    source_code_snippet: str
    extracted_symbol_id: str
    symbol_name: str
    symbol_type: str
    line_start: Optional[int]
    line_end: Optional[int]
    qualified_name: str
    matches_source: bool
    verification_notes: List[str]


class Gate2SymbolExtractor:
    def __init__(self, analysis_id: int, target_dir: Optional[Path] = None):
        self.analysis_id = analysis_id
        self.db = SessionLocal()
        self.parser = LanguageParser()
        self.target_dir = target_dir or Path("/tmp/repo-analysis")
        self.verifications: List[SymbolVerification] = []

    def sample_and_verify(self, sample_size: int = 5) -> List[SymbolVerification]:
        """Sample files and extract/verify symbols"""
        print(f"\n{'='*60}")
        print(f"GATE 2: Symbol Extraction Verification")
        print(f"Analysis ID: {self.analysis_id}")
        print(f"Sample Size: {sample_size}")
        print(f"{'='*60}\n")

        # Get analysis and repo info
        analysis = self.db.query(Analysis).filter(Analysis.id == self.analysis_id).first()
        if not analysis:
            print(f"✗ Analysis {self.analysis_id} not found")
            return []

        repo = self.db.query(Repository).filter(Repository.id == analysis.repository_id).first()
        print(f"Repository: {repo.url}")
        print(f"Analysis Status: {analysis.status}\n")

        # Get code files only (Python, JS, TS, JSX, TSX)
        code_extensions = {".py", ".js", ".ts", ".tsx", ".jsx"}
        symbols = self.db.query(FactSymbol).filter(
            FactSymbol.analysis_id == self.analysis_id
        ).all()

        # Group by file
        symbols_by_file = {}
        for sym in symbols:
            if sym.file_id:
                if sym.file_id not in symbols_by_file:
                    symbols_by_file[sym.file_id] = []
                symbols_by_file[sym.file_id].append(sym)

        # Sample files
        sampled_files = list(symbols_by_file.items())[:sample_size]
        print(f"Sampled {len(sampled_files)} files with symbols:\n")

        for file_id, file_symbols in sampled_files:
            file_record = self.db.query(FactFile).filter(FactFile.id == file_id).first()
            if not file_record:
                continue

            print(f"{'─'*60}")
            print(f"FILE: {file_record.path}")
            print(f"Extension: {Path(file_record.path).suffix}")
            print(f"File ID: {file_id}")
            print(f"Size: {file_record.size} bytes\n")

            # Try to read source file
            source_path = self.target_dir / file_record.path
            source_code = None
            if source_path.exists():
                try:
                    with open(source_path, 'r', encoding='utf-8') as f:
                        source_code = f.readlines()
                    print(f"✓ Source file found at: {source_path}\n")
                except Exception as e:
                    print(f"⚠ Could not read source: {e}\n")

            # Verify each symbol
            for sym in file_symbols[:3]:  # Show first 3 symbols per file
                self._verify_symbol(sym, file_record, source_code)

        self._print_summary()
        return self.verifications

    def _verify_symbol(self, symbol: FactSymbol, file_record: FactFile, source_code: Optional[List[str]]):
        """Verify a single symbol extraction"""
        print(f"  Symbol: {symbol.name}")
        print(f"  Type: {symbol.symbol_type}")
        print(f"  Qualified Name: {symbol.qualified_name}")
        print(f"  Lines: {symbol.line_start}-{symbol.line_end}")
        print(f"  ID: {symbol.id}\n")

        verification_notes = []
        matches_source = False

        # Verify line boundaries exist
        if symbol.line_start is None or symbol.line_end is None:
            verification_notes.append("❌ Missing line boundaries")

        # Try to extract source snippet
        source_snippet = ""
        if source_code and symbol.line_start and symbol.line_end:
            try:
                line_idx_start = symbol.line_start - 1  # Convert to 0-indexed
                line_idx_end = min(symbol.line_end, len(source_code))
                source_snippet = "".join(source_code[line_idx_start:line_idx_end])

                # Verify symbol name appears in source
                if symbol.name in source_snippet:
                    verification_notes.append(f"✅ Symbol name '{symbol.name}' found in source")
                    matches_source = True
                else:
                    verification_notes.append(f"❌ Symbol name '{symbol.name}' NOT found in source range")

                # Show snippet
                print(f"  Source snippet (lines {symbol.line_start}-{symbol.line_end}):")
                for i, line in enumerate(source_snippet.split('\n')[:5], 1):  # Show first 5 lines
                    print(f"    {line[:80]}")
                if len(source_snippet.split('\n')) > 5:
                    print(f"    ... ({len(source_snippet.split('\n')) - 5} more lines)")
                print()

            except Exception as e:
                verification_notes.append(f"⚠ Could not extract snippet: {e}")

        verification = SymbolVerification(
            file_path=file_record.path,
            source_code_snippet=source_snippet[:200],
            extracted_symbol_id=symbol.id,
            symbol_name=symbol.name,
            symbol_type=symbol.symbol_type,
            line_start=symbol.line_start,
            line_end=symbol.line_end,
            qualified_name=symbol.qualified_name,
            matches_source=matches_source,
            verification_notes=verification_notes
        )
        self.verifications.append(verification)

        # Print notes
        for note in verification_notes:
            print(f"  {note}")
        print()

    def _print_summary(self):
        """Print summary of verifications"""
        print(f"\n{'='*60}")
        print("GATE 2 SUMMARY")
        print(f"{'='*60}\n")

        total = len(self.verifications)
        matches = sum(1 for v in self.verifications if v.matches_source)

        print(f"Total symbols verified: {total}")
        print(f"Source-matched symbols: {matches}/{total}")
        print(f"Match rate: {(matches/total*100):.1f}%\n")

        if matches < total:
            print("❌ SYMBOLS NOT FOUND IN SOURCE:")
            for v in self.verifications:
                if not v.matches_source:
                    print(f"  - {v.qualified_name} in {v.file_path} (lines {v.line_start}-{v.line_end})")
            print()

        # Export detailed report
        report = {
            'analysis_id': self.analysis_id,
            'total_verified': total,
            'source_matched': matches,
            'match_rate': matches/total if total > 0 else 0,
            'verifications': [
                {
                    'file': v.file_path,
                    'symbol': v.symbol_name,
                    'type': v.symbol_type,
                    'qualified_name': v.qualified_name,
                    'lines': f"{v.line_start}-{v.line_end}",
                    'matches_source': v.matches_source,
                    'notes': v.verification_notes
                }
                for v in self.verifications
            ]
        }

        print(json.dumps(report, indent=2))
        print(f"\n{'='*60}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python gate2_symbol_extraction.py <analysis_id> [sample_size] [repo_dir]")
        print("Example: python gate2_symbol_extraction.py 7 5 /tmp/repo-analysis/job_9_GitOnboard")
        sys.exit(1)

    analysis_id = int(sys.argv[1])
    sample_size = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    repo_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    extractor = Gate2SymbolExtractor(analysis_id, repo_dir)
    verifications = extractor.sample_and_verify(sample_size)

    # Exit with success if symbols match source
    match_rate = sum(1 for v in verifications if v.matches_source) / len(verifications) if verifications else 0
    sys.exit(0 if match_rate >= 0.8 else 1)


if __name__ == "__main__":
    main()
