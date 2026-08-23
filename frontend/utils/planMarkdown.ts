/**
 * Formats an EngineeringAgent Implementation Plan into Antigravity-style Markdown.
 */
export function generatePlanMarkdown(plan: any, tasks: any[] = []): string {
  if (!plan) {
    return "# Implementation Plan\n\nNo implementation plan has been generated yet.";
  }

  const req = plan.requirement || "Feature Implementation";
  const version = plan.version || 1;
  const status = plan.status || "AWAITING_APPROVAL";
  const allTasks = tasks && tasks.length > 0 ? tasks : (plan.tasks || []);

  let md = `# Implementation Plan: ${req}\n\n`;
  md += `**Status**: \`${status}\` | **Version**: \`v${version}\` | **Tasks**: \`${allTasks.length}\`\n\n`;
  md += `---\n\n`;

  // 1. Goal & Architecture Context
  md += `## 1. Goal & Architectural Context\n\n`;
  if (plan.architecture_context?.summary) {
    md += `${plan.architecture_context.summary}\n\n`;
  } else if (plan.repository_understanding?.summary) {
    md += `${plan.repository_understanding.summary}\n\n`;
  } else {
    md += `Implementation plan synthesized for user requirement: *"${req}"*.\n\n`;
  }

  // 2. Acceptance Criteria
  if (plan.acceptance_criteria && plan.acceptance_criteria.length > 0) {
    md += `## 2. Acceptance Criteria\n\n`;
    plan.acceptance_criteria.forEach((ac: string) => {
      md += `- [ ] ${ac}\n`;
    });
    md += `\n`;
  }

  // 3. Execution Plan (Tasks DAG)
  md += `## 3. Execution Plan (Tasks DAG)\n\n`;
  if (allTasks.length === 0) {
    md += `*No discrete tasks specified.*\n\n`;
  } else {
    allTasks.forEach((t: any, idx: number) => {
      const taskTitle = t.title || `Task ${idx + 1}`;
      const taskId = t.task_id || `task_${idx + 1}`;
      const actionType = t.action_type || "MODIFY_CODE";
      const taskStatus = t.status || "PENDING";
      const files = t.affected_files || [];

      md += `### Task ${idx + 1}: ${taskTitle} (\`${taskId}\`)\n\n`;
      md += `- **Action**: \`${actionType}\` | **Status**: \`${taskStatus}\`\n`;
      if (files.length > 0) {
        md += `- **Target Files**:\n`;
        files.forEach((f: string) => {
          md += `  - \`${f}\`\n`;
        });
      }
      if (t.description) {
        md += `\n${t.description}\n`;
      }
      if (t.acceptance_criteria && t.acceptance_criteria.length > 0) {
        md += `\n**Acceptance Criteria**:\n`;
        t.acceptance_criteria.forEach((tac: string) => {
          md += `- [ ] ${tac}\n`;
        });
      }
      md += `\n---\n\n`;
    });
  }

  // 4. Invariants & Risks
  if (plan.risks && plan.risks.length > 0) {
    md += `## 4. Invariants & Technical Risks\n\n`;
    plan.risks.forEach((r: string) => {
      md += `- ⚠️ **Risk**: ${r}\n`;
    });
    md += `\n`;
  }

  // 5. Verification Strategy
  md += `## 5. Verification Strategy\n\n`;
  md += `- **Strategy**: \`${plan.verification_strategy || "Multi-Vector AST & Dynamic Verification"}\`\n`;
  md += `- Automated regression testing and AST boundary validation before PR creation.\n\n`;

  return md;
}
