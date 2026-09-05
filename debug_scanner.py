#!/usr/bin/env python
"""Debug script to check what directories are being scanned/excluded."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from backend.intelligence.engine.scanner.scanner import RepositoryScanner
import os

repo_path = PROJECT_ROOT

scanner = RepositoryScanner(str(repo_path))

print(f"Scanning: {repo_path}")
print(f"\nDEFAULT_IGNORES ({len(scanner.DEFAULT_IGNORES)}):")
for d in sorted(scanner.DEFAULT_IGNORES):
    print(f"  - {d}")

print(f"\n\nTop-level directories in repo:")
for item in sorted(os.listdir(repo_path)):
    full_path = repo_path / item
    if full_path.is_dir():
        if item in scanner.DEFAULT_IGNORES:
            print(f"  [EXCLUDED] {item}/")
        else:
            file_count = sum(1 for _ in full_path.rglob('*') if _.is_file())
            print(f"  [SCANNED]  {item}/ ({file_count} files)")

print(f"\n\nFull scan results:")
manifest = scanner.scan()
print(f"Total files: {len(manifest.files)}")
