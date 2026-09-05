# Repository Rules & Conventions

## Repository Organization

### Root Directory (Keep Clean)

The repository root (`/`) must contain **only**:

- Essential config files: `pyproject.toml`, `alembic.ini`, `docker-compose.yml`
- Environment files: `.env`, `.env.example`
- Documentation: `README.md`, `LICENSE`, `RULES.md`, `CLAUDE.md`
- System files: `.gitignore`, `.github/`, `uv.lock`
- **NO** temporary scripts, investigation code, or debug output

### Organization Structure

```
repository_intelligence_platform/
├── backend/               # Main application code
├── frontend/              # Frontend code
├── investigations/        # Temporary/experimental code
│   └── phase_2x_validation/  # Phase 2K+ validation scripts
├── docs/                  # Documentation
│   ├── reports/          # Analysis reports & findings
│   └── architecture/      # Architecture documentation
├── tests/                 # Test files (also in backend/)
└── scripts/               # Production utilities (if needed)
```

### File Placement Rules

**In repo root: YES**
- `phase2k_complete_e2e_validation.py` — primary validation harness (essential)
- `phase2k2_full_e2e_validation.py` — primary validation harness (essential)
- Configuration files (setup.py, pyproject.toml, etc.)
- Main documentation (README.md, LICENSE)

**In investigations/: YES**
- Temporary validation scripts (`run_phase2d_*.py`, `phase2i_*.py`, etc.)
- Debug/profiling scripts (`benchmark_*.py`, `test_*.py`)
- One-off analysis scripts (`diagnose_*.py`, `monitor_*.py`, etc.)
- Phase-specific reports and logs
- Temporary data files (`.json`, `.db`, `.log`)

**In docs/reports/: YES**
- Phase reports (`PHASE2K4_FILE_FILTERING_REPORT.md`)
- Investigation findings and documentation
- Audit reports

**Nowhere: NO**
- Generated data files (`.json`, `.db`, `.log`) — move to investigations/
- Temporary scripts — move to investigations/
- Debug output — move to investigations/
- Backup files (`.backup`) — delete or move to investigations/

---

## Cleanup Protocol

When finishing a phase or investigation:

1. **Move temporary code** to `investigations/phase_2x_validation/`
   ```bash
   mv phase2x_*.py investigations/phase_2x_validation/
   mv run_*.py investigations/phase_2x_validation/
   mv *.json *.log *.db investigations/phase_2x_validation/
   ```

2. **Move reports** to `docs/reports/`
   ```bash
   mv PHASE*.md docs/reports/
   ```

3. **Keep only primary validation scripts** in root:
   - `phase2k_complete_e2e_validation.py`
   - `phase2k2_full_e2e_validation.py`

4. **Commit cleanup**
   ```bash
   git add -A
   git commit -m "Cleanup: Move investigation files to investigations/"
   ```

---

## Why This Matters

- **Clarity** — Developers can immediately see what's production vs. experimental
- **Git history** — Root stays clean; easier to find relevant changes
- **CI/CD** — Easier to identify what scripts should run automatically
- **Onboarding** — New developers understand the structure immediately
- **Maintenance** — Investigation code doesn't clutter the main codebase

---

## Current State (2026-09-06)

✓ **Repository root cleaned**
- Moved 20+ investigation scripts to `investigations/phase_2x_validation/`
- Moved 10+ report/logs to `investigations/phase_2x_validation/`
- Moved PHASE reports to `docs/reports/`
- Root now contains only essential files

---

## Exception Process

If a script needs to stay in root (e.g., primary validation harness), document it:

1. Add an entry to this RULES.md explaining why
2. Add a comment in the script header referencing this rule
3. Ensure it's genuinely production/essential, not experimental

---

## Approved Exceptions (Root Files)

These files stay in root because they're essential:

- `phase2k_complete_e2e_validation.py` — Primary E2E validation harness (Phase 2K integration testing)
- `phase2k2_full_e2e_validation.py` — Extended E2E validation (stages 6-8, future use)

All other investigation/temporary scripts go to `investigations/`.

---

**Last Updated:** 2026-09-06  
**Enforced by:** Manual code review + this document
