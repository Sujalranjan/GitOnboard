"""
Diagnostic Report Analyzer: Post-mortem analysis of failed/incomplete analyses.

Load saved diagnostic reports and:
- Identify what went wrong
- Suggest fixes
- Compare analyses
- Find patterns in failures
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict


class DiagnosticReportAnalyzer:
    """Analyze saved diagnostic reports to debug failures."""

    def __init__(self, report_file: Path):
        self.report_file = Path(report_file)
        self.report = self._load_report()
        self.actions = self._load_actions()

    def _load_report(self) -> Dict[str, Any]:
        """Load the diagnostic report JSON."""
        with open(self.report_file, "r") as f:
            return json.load(f)

    def _load_actions(self) -> List[Dict[str, Any]]:
        """Load the actions log (JSONL format)."""
        actions = []
        actions_file = self.report_file.parent / self.report_file.name.replace("_report.json", "_actions.jsonl")
        if actions_file.exists():
            with open(actions_file, "r") as f:
                for line in f:
                    actions.append(json.loads(line))
        return actions

    def print_summary(self) -> None:
        """Print human-readable summary."""
        r = self.report
        print(f"""
{'=' * 80}
ANALYSIS REPORT: {r.get('analysis_id', 'N/A')}
Repository: {r.get('repository_name', 'N/A')}
Time Range: {r.get('start_time', 'N/A')} to {r.get('end_time', 'N/A')}

KEY METRICS:
  Files Processed: {r.get('total_files_processed', 0)}
  Entities Created: {r.get('total_entities_created', 0)}
  Total Relationships: {r.get('total_relationships_created', 0)}

RELATIONSHIP BREAKDOWN:
{self._format_breakdown(r.get('relationship_breakdown', {}))}

ANALYZERS RUN:
{chr(10).join(f'  ✓ {a}' for a in r.get('analyzers_executed', []))}

ERRORS ({len(r.get('errors_encountered', []))}):
{self._format_errors(r.get('errors_encountered', []))}

SKIPPED RELATIONSHIPS ({r.get('skipped_relationships_count', 0)}):
{self._format_skipped(r)}

STATUS:
{self._diagnose_status(r)}
{'=' * 80}
""")

    def _format_breakdown(self, breakdown: Dict[str, int]) -> str:
        """Format relationship breakdown."""
        if not breakdown:
            return "  (None - this is a problem!)"
        return "\n".join(f"  {k}: {v}" for k, v in sorted(breakdown.items()))

    def _format_errors(self, errors: List[Dict[str, Any]]) -> str:
        """Format error list."""
        if not errors:
            return "  None"
        lines = []
        for e in errors[:5]:
            lines.append(f"  [{e.get('type', 'Unknown')}] {e.get('analyzer', '?')} @ {e.get('file', '?')}")
            lines.append(f"    → {e.get('message', 'No message')}")
        if len(errors) > 5:
            lines.append(f"  ... and {len(errors) - 5} more")
        return "\n".join(lines)

    def _format_skipped(self, report: Dict[str, Any]) -> str:
        """Format skipped relationships."""
        count = report.get('skipped_relationships_count', 0)
        if count == 0:
            return "  None (all relationships persisted)"

        # Try to find reasons in actions
        reasons = defaultdict(int)
        for action in self.actions:
            if action.get('action_type') == 'RELATIONSHIP_SKIP':
                reason = action.get('details', {}).get('reason', 'Unknown')
                reasons[reason] += 1

        if reasons:
            return "\n".join(f"  {count} total: {', '.join(f'{r}({c})' for r, c in sorted(reasons.items(), key=lambda x: -x[1]))}")
        return f"  {count} relationships skipped (reasons not logged)"

    def _diagnose_status(self, report: Dict[str, Any]) -> str:
        """Diagnose the overall status."""
        rel_breakdown = report.get('relationship_breakdown', {})
        total_rels = report.get('total_relationships_created', 0)
        errors = len(report.get('errors_encountered', []))
        skipped = report.get('skipped_relationships_count', 0)

        # Check for the specific problem we're seeing
        if 'CALLS' not in rel_breakdown and 'USES' not in rel_breakdown and 'RENDERS' not in rel_breakdown:
            return """
  ⚠️  PROBLEM: New relationship types (CALLS, USES, RENDERS) not found!

  This indicates:
  1. New analyzers (CallGraphAnalyzer, UsesAnalyzer) not running
  2. OR parsers returning invalid AST objects
  3. OR AST traversal finding no callable/component nodes

  Recommendations:
  - Check that CallGraphAnalyzer/UsesAnalyzer are registered
  - Verify TypeScriptProvider returns valid tree-sitter Tree objects
  - Check for exceptions in analyzer logs (see errors above)
  - Review ANALYZER_PROCESS_FILE actions to see which files were skipped
"""

        if errors > 0:
            return f"""
  ⚠️  ISSUES: {errors} errors encountered

  Check error details above. May have impacted relationship extraction.
  Review full actions log for stack traces.
"""

        if skipped > 0:
            return f"""
  ⚠️  INCOMPLETE: {skipped} relationships skipped (source/target missing)

  This is normal if validation is strict. Check if entity creation is complete
  before relationship processing.
"""

        return """
  ✓ HEALTHY: Analysis completed successfully with all relationship types
"""

    def find_missing_relationships(self) -> Dict[str, List[str]]:
        """Identify analyzers/relationship types that should exist but don't."""
        rel_breakdown = self.report.get('relationship_breakdown', {})
        analyzers = self.report.get('analyzers_executed', [])

        missing = {}

        if 'CallGraphAnalyzer' in analyzers and 'CALLS' not in rel_breakdown:
            missing['CALLS'] = [
                'CallGraphAnalyzer ran but extracted zero CALLS',
                'Check: Are there function calls in the codebase?',
                'Check: Is AST traversal working? (see log actions)',
            ]

        if 'UsesAnalyzer' in analyzers and 'USES' not in rel_breakdown:
            missing['USES'] = [
                'UsesAnalyzer ran but extracted zero USES',
                'Check: Are there property accesses in the code?',
                'Check: TypeScript/JavaScript files only',
            ]

        if 'CallGraphAnalyzer' in analyzers and 'RENDERS' not in rel_breakdown:
            missing['RENDERS'] = [
                'CallGraphAnalyzer ran but extracted zero RENDERS',
                'Check: Are there React components using JSX?',
                'Check: JSX element visitor is working',
            ]

        return missing

    def show_action_timeline(self, analyzer_name: Optional[str] = None, limit: int = 20) -> None:
        """Show timeline of actions (useful for tracing execution flow)."""
        print(f"\n{'=' * 80}\nACTION TIMELINE{f' ({analyzer_name})' if analyzer_name else ''}\n{'=' * 80}")

        actions = self.actions
        if analyzer_name:
            actions = [a for a in actions if a.get('analyzer_name') == analyzer_name]

        for i, action in enumerate(actions[:limit]):
            print(
                f"[{i:3d}] {action.get('action_type', 'UNKNOWN'):30s} "
                f"{action.get('analyzer_name', 'N/A'):20s} "
                f"{action.get('message', '')}"
            )

        if len(actions) > limit:
            print(f"\n... and {len(actions) - limit} more actions")

    def compare_relationships(self, expected: Dict[str, int]) -> None:
        """Compare actual vs expected relationships."""
        actual = self.report.get('relationship_breakdown', {})

        print(f"\n{'=' * 80}\nRELATIONSHIP COMPARISON\n{'=' * 80}")
        print(f"{'Type':<20} {'Expected':<10} {'Actual':<10} {'Status':<10}")
        print("-" * 50)

        all_types = set(expected.keys()) | set(actual.keys())
        for rel_type in sorted(all_types):
            exp = expected.get(rel_type, 0)
            act = actual.get(rel_type, 0)
            status = "✓ OK" if exp <= act else f"⚠ SHORT ({act}/{exp})"
            print(f"{rel_type:<20} {exp:<10} {act:<10} {status:<10}")


def analyze_report(report_file: Path) -> None:
    """Analyze a diagnostic report and print findings."""
    analyzer = DiagnosticReportAnalyzer(report_file)

    # Print summary
    analyzer.print_summary()

    # Find missing relationships
    missing = analyzer.find_missing_relationships()
    if missing:
        print(f"\n{'=' * 80}\nMISSING RELATIONSHIP TYPES\n{'=' * 80}")
        for rel_type, reasons in missing.items():
            print(f"\n{rel_type}:")
            for reason in reasons:
                print(f"  - {reason}")

    # Show action timeline
    print(f"\n{'=' * 80}\nRECENT ACTIONS\n{'=' * 80}")
    analyzer.show_action_timeline(limit=30)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python analyzer.py <report_file>")
        print("Example: python analyzer.py /tmp/rim_diagnostics/analysis_2_report.json")
        sys.exit(1)

    report_file = Path(sys.argv[1])
    if not report_file.exists():
        print(f"Error: Report file not found: {report_file}")
        sys.exit(1)

    analyze_report(report_file)
