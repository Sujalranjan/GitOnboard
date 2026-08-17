"""
Repository Hierarchy Discovery - Infers deployable units (Web App, Backend API, Worker, CLI, Library)
and module groupings across single repositories and monorepos.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

from .schemas import (
    DeployableUnit,
    DeployableUnitType,
    EvidenceItem,
    EvidenceSourceType,
    SourceClassification,
)


class RepositoryHierarchyEngine:
    """
    Infers project boundaries and DeployableUnits from manifest boundaries,
    framework signals, entrypoints, and container specs.
    """

    @staticmethod
    def infer_hierarchy(
        file_paths: List[str],
        evidence_items: List[EvidenceItem],
        entrypoints: Optional[List[str]] = None,
    ) -> List[DeployableUnit]:
        entrypoints = entrypoints or []
        units: List[DeployableUnit] = []
        
        # Identify package manifest locations
        manifest_files = [
            f for f in file_paths
            if os.path.basename(f).lower() in {"package.json", "pyproject.toml", "cargo.toml", "go.mod", "requirements.txt"}
            and not any(ign in f.lower().replace("\\", "/") for ign in ["node_modules/", "vendor/", "fixtures/", "test/", ".next/", "dist/", "build/", ".output/", ".turbo/", ".cache/"])
        ]

        if not manifest_files:
            manifest_files = ["root"]

        for m_file in manifest_files:
            root_dir = os.path.dirname(m_file) if m_file != "root" else ""
            unit_id = root_dir if root_dir else "root"
            name = os.path.basename(root_dir) if root_dir else "primary-service"

            contained_files = [
                f for f in file_paths
                if (f.startswith(root_dir) if root_dir else True)
                and not any(ign in f.lower() for ign in ["node_modules/", "vendor/", ".venv/"])
            ]

            matching_ev = [
                ev for ev in evidence_items
                if (ev.file_path.startswith(root_dir) if root_dir else True)
            ]

            dep_names = {ev.symbol_name.lower() for ev in matching_ev if ev.symbol_name}
            file_names_str = " ".join(f.lower() for f in contained_files)

            # Match entrypoints
            unit_eps = [
                ep for ep in entrypoints
                if (ep.startswith(root_dir) if root_dir else True)
            ]
            if not unit_eps and contained_files:
                for cand in ["main.py", "app.py", "index.ts", "index.js", "main.go", "main.rs", "src/main.py", "src/index.tsx"]:
                    cand_full = os.path.join(root_dir, cand) if root_dir else cand
                    if cand_full in file_paths:
                        unit_eps.append(cand_full)
                        break

            # Infer DeployableUnitType
            unit_type = DeployableUnitType.SHARED_LIBRARY
            
            # Check if this is a web app, backend api, worker, or cli
            if any(f in dep_names for f in ["next", "react", "vue", "svelte", "angular", "vite"]) or "next.config.js" in file_names_str:
                unit_type = DeployableUnitType.WEB_APPLICATION
            elif any(f in dep_names for f in ["celery", "rq", "bullmq", "kafka", "rabbitmq"]) or "worker" in unit_id.lower():
                unit_type = DeployableUnitType.BACKGROUND_WORKER
            elif any(f in dep_names for f in ["click", "typer", "cobra", "clap", "argparse"]) or "cmd/" in file_names_str or "cli" in unit_id.lower():
                unit_type = DeployableUnitType.CLI_TOOL
            elif unit_eps:
                # Only classify as BACKEND_API if an actual application entrypoint exists
                if any(f in dep_names for f in ["fastapi", "django", "flask", "express", "actix-web", "gin", "fiber"]):
                    unit_type = DeployableUnitType.BACKEND_API
                else:
                    unit_type = DeployableUnitType.SHARED_LIBRARY
            elif any(f in dep_names for f in ["fastapi", "django", "flask", "express"]):
                # If dependencies include framework but no entrypoints exist, check if repo is a library
                unit_type = DeployableUnitType.BACKEND_API if unit_eps else DeployableUnitType.SHARED_LIBRARY

            units.append(
                DeployableUnit(
                    unit_id=unit_id,
                    name=name,
                    unit_type=unit_type,
                    root_path=root_dir or "/",
                    entrypoints=unit_eps,
                    contained_modules=contained_files[:30]
                )
            )

        return units
