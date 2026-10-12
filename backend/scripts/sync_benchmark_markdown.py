import json
from pathlib import Path

def md_from_json(json_path: Path, title: str, intro: str) -> str:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    lines = [
        f"# {title}",
        "",
        intro,
        "",
        "> **Evaluation Rule:** Every question specifies concrete `required_evidence`, `expected_symbols`, `expected_answer_points`, and `difficulty` levels (L1–L5). A rigorous agent evaluation must grade answers against these ground-truth expectations.",
        "",
        "---",
        ""
    ]
    for item in data:
        lines.append(f"## {item['id']} — {item['category'].replace('_', ' ').title()} ({item['difficulty']})")
        lines.append(f"**Question:** {item['question']}")
        lines.append("")
        lines.append(f"- **Category:** `{item['category']}`")
        lines.append(f"- **Answer Type:** `{item['answer_type']}`")
        lines.append(f"- **Difficulty:** `{item['difficulty']}` (Files: {item['difficulty_factors']['files']}, Hops: {item['difficulty_factors']['hops']}, Concepts: {item['difficulty_factors']['concepts']})")
        lines.append(f"- **Repository:** `{item['repository']}` (Commit: `{item['repository_commit'][:12]}`)")
        lines.append(f"- **Multi-Hop Required:** `{item['requires_multi_hop']}` | **Graph Reasoning:** `{item['requires_graph_reasoning']}` | **Verification:** `{item['requires_verification']}`")
        lines.append("")
        lines.append("**Required Evidence Files:**")
        for f in item["required_evidence"]:
            lines.append(f"- `{f}`")
        lines.append("")
        if item.get("supporting_evidence"):
            lines.append("**Supporting Evidence:**")
            for f in item["supporting_evidence"]:
                lines.append(f"- `{f}`")
            lines.append("")
        if item.get("decoy_files"):
            lines.append("**Decoy / Negative Files (Must Not Confuse Agent):**")
            for f in item["decoy_files"]:
                lines.append(f"- `{f}`")
            lines.append("")
        if item.get("expected_symbols"):
            lines.append(f"**Expected Symbols:** `{', '.join(item['expected_symbols'])}`")
            lines.append("")
        lines.append(f"**Expected Concepts:** `{', '.join(item['expected_concepts'])}`")
        lines.append("")
        lines.append(f"**Expected Tool Capabilities:** `{', '.join(item['expected_tool_capabilities'])}`")
        lines.append("")
        lines.append("**Expected Answer Points:**")
        for pt in item["expected_answer_points"]:
            lines.append(f"1. {pt}")
        lines.append("")
        lines.append("**Expected Answer Structure:**")
        for st in item["expected_answer_structure"]:
            lines.append(f"- {st}")
        lines.append("")
        if item.get("known_traps"):
            lines.append("**Known Traps & Failure Modes:**")
            for trap in item["known_traps"]:
                lines.append(f"- {trap}")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)

# 1. DeepGuard Backend
dgb_md = md_from_json(
    Path("benchmark/deepguard_backend_benchmark.json"),
    "DeepGuard Backend Benchmark",
    "15 rigorous questions targeting the DeepGuard Integrated Backend (Express Gateway + FastAPI/TFLite ML Engine) and Supabase database / storage integration."
)
Path("benchmark/deepguard_backend_benchmark.md").write_text(dgb_md, encoding="utf-8")
print("Wrote benchmark/deepguard_backend_benchmark.md")

# 2. DeepGuard Frontend
dgf_md = md_from_json(
    Path("benchmark/deepguard_frontend_benchmark.json"),
    "DeepGuard Frontend Benchmark",
    "15 rigorous questions targeting the DeepGuard Frontend application (Next.js 15 App Router, React 19, Zustand store, and Tailwind CSS)."
)
Path("benchmark/deepguard_frontend_benchmark.md").write_text(dgf_md, encoding="utf-8")
print("Wrote benchmark/deepguard_frontend_benchmark.md")

# 3. GitOnboard Backend
gob_md = md_from_json(
    Path("benchmark/gitonboard_backend_benchmark.json"),
    "GitOnboard Backend Benchmark",
    "15 rigorous questions targeting GitOnboard Backend architecture (FastAPI, Tree-sitter AST, PostgreSQL Fact Store, Layer 6 Capabilities, Context Assembler, and Autonomous QALoop)."
)
Path("benchmark/gitonboard_backend_benchmark.md").write_text(gob_md, encoding="utf-8")
print("Wrote benchmark/gitonboard_backend_benchmark.md")

# 4. GitOnboard Frontend
gof_md = md_from_json(
    Path("benchmark/gitonboard_frontend_benchmark.json"),
    "GitOnboard Frontend Benchmark",
    "15 rigorous questions targeting GitOnboard Frontend architecture (Next.js 16 App Router, React 19, useAgentWorkspace SSE reconciliation, Monaco CodeEditorPanel, ApprovalBanner, and VerificationPanel)."
)
Path("benchmark/gitonboard_frontend_benchmark.md").write_text(gof_md, encoding="utf-8")
print("Wrote benchmark/gitonboard_frontend_benchmark.md")
