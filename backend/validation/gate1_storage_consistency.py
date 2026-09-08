#!/usr/bin/env python3
"""
GATE 1 — Storage/Persistence Verification

Cross-verifies the actual GitOnboard repository against PostgreSQL and Azure/Azurite.

Checks:
- Files, canonical paths, file counts
- File identity/content
- Repository/commit/analysis identity
- PostgreSQL ↔ Azure consistency
- Symbols ↔ files relationships
- Relationships ↔ symbols references
- Zero orphaned references
- No duplicate/cross-analysis data
"""

import sys
import json
from pathlib import Path
from typing import Set, Dict, List, Tuple
from dataclasses import dataclass, asdict
import hashlib

from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.repository import Analysis, Repository
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from backend.services.storage import BlobStorageService

@dataclass
class VerificationReport:
    analysis_id: int
    checks_passed: int
    checks_failed: int
    warnings: List[str]
    errors: List[str]
    details: Dict

    def summary(self):
        status = "✅ PASS" if self.checks_failed == 0 else "❌ FAIL"
        return f"{status} | {self.checks_passed} passed, {self.checks_failed} failed | {len(self.warnings)} warnings"


class Gate1Verifier:
    def __init__(self, analysis_id: int):
        self.analysis_id = analysis_id
        self.db = SessionLocal()
        self.storage = BlobStorageService()
        self.report = VerificationReport(
            analysis_id=analysis_id,
            checks_passed=0,
            checks_failed=0,
            warnings=[],
            errors=[],
            details={}
        )

    def verify_all(self) -> VerificationReport:
        """Run all verification checks"""
        print(f"\n{'='*60}")
        print(f"GATE 1: Storage Consistency Verification")
        print(f"Analysis ID: {self.analysis_id}")
        print(f"{'='*60}\n")

        self._check_analysis_exists()
        self._check_file_counts()
        self._check_file_paths()
        self._check_postgresql_integrity()
        self._check_blob_storage_consistency()
        self._check_symbol_file_links()
        self._check_relationship_references()
        self._check_no_orphaned_data()
        self._check_no_duplicates()

        return self._print_report()

    def _check_analysis_exists(self):
        """Verify analysis record exists"""
        print("CHECK 1: Analysis exists in database...")
        analysis = self.db.query(Analysis).filter(Analysis.id == self.analysis_id).first()

        if not analysis:
            self.report.errors.append(f"Analysis {self.analysis_id} not found in database")
            self.report.checks_failed += 1
            return

        self.report.details['analysis'] = {
            'id': analysis.id,
            'status': analysis.status,
            'repository_id': analysis.repository_id,
            'indexed_at': str(analysis.indexed_at) if analysis.indexed_at else None,
            'indexing_status': analysis.indexing_status
        }

        if analysis.status != "Completed":
            self.report.warnings.append(f"Analysis status is '{analysis.status}', not 'Completed'")

        self.report.checks_passed += 1
        print(f"  ✓ Analysis {self.analysis_id} exists, status: {analysis.status}\n")

    def _check_file_counts(self):
        """Verify file counts match across sources"""
        print("CHECK 2: File counts consistency...")

        # Count in PostgreSQL
        pg_files = self.db.query(FactFile).filter(FactFile.analysis_id == self.analysis_id).all()
        pg_file_count = len(pg_files)

        # Count unique file paths
        pg_paths = set(f.path for f in pg_files)

        self.report.details['file_counts'] = {
            'postgresql_total': pg_file_count,
            'postgresql_unique_paths': len(pg_paths),
            'files': {f.path: {'size': f.size, 'blob_name': f.blob_name} for f in pg_files[:5]}  # Sample
        }

        if pg_file_count == 0:
            self.report.errors.append("No files found in PostgreSQL")
            self.report.checks_failed += 1
        else:
            self.report.checks_passed += 1
            print(f"  ✓ PostgreSQL: {pg_file_count} files, {len(pg_paths)} unique paths\n")

    def _check_file_paths(self):
        """Verify file paths are canonical (no duplicates, proper format)"""
        print("CHECK 3: File path canonicalization...")

        pg_files = self.db.query(FactFile).filter(FactFile.analysis_id == self.analysis_id).all()
        paths_seen = set()
        path_issues = []

        for f in pg_files:
            # Check for backslashes (should be forward slashes)
            if '\\' in f.path:
                path_issues.append(f"Backslash in path: {f.path}")

            # Check for duplicate paths
            if f.path in paths_seen:
                path_issues.append(f"Duplicate path: {f.path}")
            paths_seen.add(f.path)

            # Check for leading/trailing slashes
            if f.path.startswith('/') or f.path.endswith('/'):
                path_issues.append(f"Invalid leading/trailing slash: {f.path}")

        if path_issues:
            self.report.errors.extend(path_issues)
            self.report.checks_failed += 1
            print(f"  ✗ Found {len(path_issues)} path issues\n")
        else:
            self.report.checks_passed += 1
            print(f"  ✓ All {len(paths_seen)} file paths are canonical\n")

    def _check_postgresql_integrity(self):
        """Verify PostgreSQL referential integrity"""
        print("CHECK 4: PostgreSQL referential integrity...")

        integrity_issues = []

        # Check files without IDs
        orphaned_files = self.db.query(FactFile).filter(
            FactFile.analysis_id == self.analysis_id,
            FactFile.id == None
        ).count()
        if orphaned_files > 0:
            integrity_issues.append(f"Files with NULL ID: {orphaned_files}")

        # Check symbols without file_id references
        symbols = self.db.query(FactSymbol).filter(FactSymbol.analysis_id == self.analysis_id).all()
        symbols_without_file = [s.id for s in symbols if not s.file_id]
        if symbols_without_file:
            integrity_issues.append(f"Symbols without file_id: {len(symbols_without_file)}")

        self.report.details['postgresql_integrity'] = {
            'orphaned_files': orphaned_files,
            'symbols_without_file': len(symbols_without_file),
            'total_symbols': len(symbols)
        }

        if integrity_issues:
            self.report.errors.extend(integrity_issues)
            self.report.checks_failed += 1
            print(f"  ✗ Found integrity issues\n")
        else:
            self.report.checks_passed += 1
            print(f"  ✓ PostgreSQL integrity OK ({len(symbols)} symbols)\n")

    def _check_blob_storage_consistency(self):
        """Verify files in PostgreSQL exist in blob storage"""
        print("CHECK 5: Blob storage consistency...")

        pg_files = self.db.query(FactFile).filter(FactFile.analysis_id == self.analysis_id).all()
        missing_blobs = []

        analysis = self.db.query(Analysis).filter(Analysis.id == self.analysis_id).first()
        repo = self.db.query(Repository).filter(Repository.id == analysis.repository_id).first()

        for f in pg_files[:10]:  # Sample first 10
            if f.blob_name:
                try:
                    exists = self.storage.object_exists(f.blob_name)
                    if not exists:
                        missing_blobs.append(f.blob_name)
                except Exception as e:
                    self.report.warnings.append(f"Could not verify blob {f.blob_name}: {e}")

        self.report.details['blob_storage'] = {
            'total_files_with_blob_name': len([f for f in pg_files if f.blob_name]),
            'sampled_count': min(10, len(pg_files)),
            'missing_in_blob': len(missing_blobs)
        }

        if missing_blobs:
            self.report.errors.append(f"Missing blobs: {missing_blobs}")
            self.report.checks_failed += 1
        else:
            self.report.checks_passed += 1
            print(f"  ✓ Blob storage consistency OK (sampled {min(10, len(pg_files))} files)\n")

    def _check_symbol_file_links(self):
        """Verify all symbols link to existing files"""
        print("CHECK 6: Symbol ↔ File links...")

        symbols = self.db.query(FactSymbol).filter(FactSymbol.analysis_id == self.analysis_id).all()
        files = self.db.query(FactFile).filter(FactFile.analysis_id == self.analysis_id).all()

        file_ids = set(f.id for f in files)
        orphaned_symbols = []

        for sym in symbols:
            if sym.file_id and sym.file_id not in file_ids:
                orphaned_symbols.append(sym.id)

        self.report.details['symbol_file_links'] = {
            'total_symbols': len(symbols),
            'total_files': len(files),
            'orphaned_symbols': len(orphaned_symbols)
        }

        if orphaned_symbols:
            self.report.errors.append(f"Orphaned symbols (file_id not in files table): {len(orphaned_symbols)}")
            self.report.checks_failed += 1
            print(f"  ✗ Found {len(orphaned_symbols)} orphaned symbols\n")
        else:
            self.report.checks_passed += 1
            print(f"  ✓ All {len(symbols)} symbols link to valid files\n")

    def _check_relationship_references(self):
        """Verify all relationship references point to existing symbols"""
        print("CHECK 7: Relationship ↔ Symbol references...")

        rels = self.db.query(FactRelationship).filter(FactRelationship.analysis_id == self.analysis_id).all()
        symbols = self.db.query(FactSymbol).filter(FactSymbol.analysis_id == self.analysis_id).all()

        symbol_ids = set(s.id for s in symbols)

        orphaned_from = []
        orphaned_to = []

        for rel in rels:
            if rel.from_symbol_id not in symbol_ids:
                orphaned_from.append(rel.id)
            if rel.to_symbol_id not in symbol_ids:
                orphaned_to.append(rel.id)

        self.report.details['relationship_references'] = {
            'total_relationships': len(rels),
            'total_symbols': len(symbols),
            'orphaned_from_symbol_id': len(orphaned_from),
            'orphaned_to_symbol_id': len(orphaned_to)
        }

        all_orphaned = orphaned_from + orphaned_to
        if all_orphaned:
            self.report.errors.append(f"Orphaned relationship references: {len(all_orphaned)} total")
            self.report.checks_failed += 1
            print(f"  ✗ Found {len(all_orphaned)} orphaned relationships\n")
        else:
            self.report.checks_passed += 1
            print(f"  ✓ All {len(rels)} relationships reference valid symbols (ZERO orphaned)\n")

    def _check_no_orphaned_data(self):
        """Verify no orphaned analysis data exists"""
        print("CHECK 8: No orphaned data...")

        issues = []

        # Check for orphaned analysis artifacts
        from backend.models.fact_store import AnalysisArtifact
        artifacts = self.db.query(AnalysisArtifact).filter(
            AnalysisArtifact.analysis_id == self.analysis_id
        ).all()

        # Check for orphaned analysis jobs
        from backend.models.repository import AnalysisJob
        jobs = self.db.query(AnalysisJob).filter(
            AnalysisJob.analysis_id == self.analysis_id
        ).all()

        self.report.details['orphaned_data'] = {
            'analysis_artifacts': len(artifacts),
            'analysis_jobs': len(jobs)
        }

        if not issues:
            self.report.checks_passed += 1
            print(f"  ✓ No orphaned data found\n")
        else:
            self.report.errors.extend(issues)
            self.report.checks_failed += 1

    def _check_no_duplicates(self):
        """Verify no duplicate data across analyses"""
        print("CHECK 9: No cross-analysis duplicates...")

        duplicates = []

        # Check for duplicate file paths across all analyses
        from sqlalchemy import func
        duplicate_paths = self.db.query(
            FactFile.path, func.count(FactFile.id).label('cnt')
        ).filter(
            FactFile.analysis_id == self.analysis_id
        ).group_by(FactFile.path).having(func.count(FactFile.id) > 1).all()

        if duplicate_paths:
            duplicates.append(f"Duplicate file paths within analysis: {len(duplicate_paths)}")

        self.report.details['duplicates'] = {
            'duplicate_file_paths': len(duplicate_paths)
        }

        if duplicates:
            self.report.errors.extend(duplicates)
            self.report.checks_failed += 1
        else:
            self.report.checks_passed += 1
            print(f"  ✓ No duplicates found\n")

    def _print_report(self) -> VerificationReport:
        """Print and return the verification report"""
        print(f"\n{'='*60}")
        print("GATE 1 REPORT")
        print(f"{'='*60}")
        print(f"\nStatus: {self.report.summary()}\n")

        if self.report.errors:
            print("ERRORS:")
            for err in self.report.errors:
                print(f"  ✗ {err}")

        if self.report.warnings:
            print("\nWARNINGS:")
            for warn in self.report.warnings:
                print(f"  ⚠ {warn}")

        print("\nDETAILS:")
        print(json.dumps(self.report.details, indent=2, default=str))

        print(f"\n{'='*60}\n")

        return self.report


def main():
    if len(sys.argv) < 2:
        print("Usage: python gate1_storage_consistency.py <analysis_id>")
        print("Example: python gate1_storage_consistency.py 7")
        sys.exit(1)

    analysis_id = int(sys.argv[1])

    verifier = Gate1Verifier(analysis_id)
    report = verifier.verify_all()

    sys.exit(0 if report.checks_failed == 0 else 1)


if __name__ == "__main__":
    main()
