# Repository Intent Classification Benchmark Report

- **Evaluated At**: 2026-08-23 12:03:54 UTC
- **Dataset**: `repository_intent_benchmark.csv` (139 cases)
- **Overall Accuracy**: **79.86%** (111/139)
- **Total Runtime**: 753.73s

## 1. Accuracy by Intent

| Intent | Correct | Total | Accuracy |
| :--- | :---: | :---: | :---: |
| **CHAT** | 10 | 10 | **100.0%** |
| **CLARIFY** | 7 | 20 | **35.0%** |
| **EXPLAIN** | 27 | 28 | **96.43%** |
| **EXPLORE** | 24 | 26 | **92.31%** |
| **IMPLEMENT** | 26 | 28 | **92.86%** |
| **PLAN** | 17 | 27 | **62.96%** |

## 2. Accuracy by Difficulty

| Difficulty | Correct | Total | Accuracy |
| :--- | :---: | :---: | :---: |
| **Easy** | 42 | 48 | **87.5%** |
| **Expert** | 19 | 26 | **73.08%** |
| **Hard** | 31 | 40 | **77.5%** |
| **Medium** | 19 | 25 | **76.0%** |

## 3. Accuracy by Case Type

| Case Type | Correct | Total | Accuracy |
| :--- | :---: | :---: | :---: |
| `boundary_pair` | 13 | 20 | **65.0%** |
| `clear` | 42 | 48 | **87.5%** |
| `keyword_trap` | 14 | 16 | **87.5%** |
| `mixed_intent` | 5 | 10 | **50.0%** |
| `natural_variation` | 19 | 25 | **76.0%** |
| `negation_constraint` | 9 | 10 | **90.0%** |
| `semantic_boundary` | 9 | 10 | **90.0%** |

## 4. Classification Method Distribution

| Method | Count | Percentage |
| :--- | :---: | :---: |
| `deterministic` | 41 | 29.5% |
| `llm` | 98 | 70.5% |

## 5. Mismatched Cases (28)

| ID | Question | Expected | Predicted | Method | Reason |
| :---: | :--- | :---: | :---: | :---: | :--- |
| 028 | `How should we redesign the scheduler?` | **plan** | `explain` | llm | The user is asking about the process or approach to redesigning a scheduler, which requires an explanation of how it should be done. |
| 032 | `What is the safest approach for adding Redis caching?` | **plan** | `explain` | llm | The user is asking about the safest approach, which requires an explanation of concepts or logic. |
| 044 | `Fix it.` | **clarify** | `implement` | llm | The request is clear and direct, asking for a fix to be implemented. |
| 045 | `Update the DAG.` | **clarify** | `implement` | llm | The request is clear and specific, asking for a code change to be made now. |
| 047 | `Something is wrong with authentication.` | **clarify** | `explain` | llm | The user is asking about a problem with authentication, which requires an explanation of how it works or why it might be failing. |
| 048 | `Change how retries work.` | **clarify** | `implement` | llm | The user is explicitly requesting a change to how retries work, which involves modifying code. |
| 061 | `How should GitLab support fit into the repository layer?` | **plan** | `explain` | llm | The user is asking about the conceptual integration of GitLab support into the repository layer, which requires an explanation. |
| 063 | `How would you approach redesigning the terminal router?` | **plan** | `explain` | llm | The user is asking about a conceptual approach to redesigning the terminal router, which requires an explanation of how it could be done. |
| 069 | `Authentication is behaving strangely.` | **clarify** | `explain` | llm | The user is asking about the behavior of authentication, which requires an explanation. |
| 070 | `The scheduler needs to be changed.` | **clarify** | `implement` | llm | The user is explicitly requesting a change to the scheduler, which implies code changes. |
| 071 | `Can you fix the repository problem?` | **clarify** | `implement` | llm | The user is explicitly requesting a fix to the repository problem, which implies code changes. |
| 073 | `The retry behavior isn't right.` | **clarify** | `explain` | llm | The request is asking about the behavior of a feature (retry), which requires an explanation. |
| 076 | `[boundary] How should authentication be redesigned?` | **plan** | `explain` | llm | The user is asking about how authentication should be redesigned, which requires an explanation of the current state and potential improvements. |
| 078 | `[boundary] Authentication isn't working.` | **clarify** | `explain` | llm | The user is asking about the issue with authentication, which requires an explanation of how it works or why it might not be functioning correctly. |
| 081 | `[boundary] How should retries be redesigned?` | **plan** | `explain` | llm | The user is asking how something (retries) should be redesigned, which falls under the category of conceptual explanation. |
| 083 | `[boundary] Fix retries.` | **clarify** | `implement` | llm | The request is explicitly asking for code changes to be made now. |
| 086 | `[boundary] How should RepositoryIndexer be refactored?` | **plan** | `explain` | llm | The user is asking about how RepositoryIndexer should be refactored, which requires an explanation of the current structure and potential improvements. |
| 088 | `[boundary] RepositoryIndexer is broken.` | **clarify** | `explain` | llm | The user is asking about a problem with the RepositoryIndexer, which requires an explanation of how it works or why it might be broken. |
| 093 | `[boundary] Caching.` | **clarify** | `explore` | llm | The request is about caching, which implies a technical query about the repository's structure or files related to caching. |
| 097 | `How do I add OAuth?` | **explain** | `plan` | llm | The user is asking about the requirements for adding OAuth, which falls under planning. |
| 105 | `Don't modify the scheduler. Where is it implemented?` | **explore** | `explain` | deterministic | Explicit negative constraint against mutation |
| 116 | `Find the bug and fix it.` | **implement** | `explore` | deterministic | Matched repository exploration pattern '^find\s+([A-Za-z0-9_]+)\b' |
| 117 | `Show me the relevant files and then implement the change.` | **implement** | `explore` | deterministic | Matched repository exploration pattern '^show\s+(me\s+)?(the\s+)?([A-Za-z0-9_\s]+)\s+files\b' |
| 118 | `Explain the problem and propose a fix.` | **plan** | `explain` | deterministic | Matched conceptual explanation pattern '^explain\s+([a-z0-9_\s]+)\b' |
| 120 | `Explain the current caching design and propose a better one.` | **plan** | `explain` | deterministic | Matched conceptual explanation pattern '^explain\s+([a-z0-9_\s]+)\b' |
| 122 | `Find the retry code and suggest how it should be redesigned.` | **plan** | `explore` | deterministic | Matched repository exploration pattern '^find\s+([A-Za-z0-9_]+)\b' |
| 129 | `[adversarial] Please fix authentication.` | **clarify** | `implement` | llm | The user is explicitly requesting a fix to authentication, which involves code changes. |
| 138 | `[adversarial] Show me all files related to OAuth, but don't change anything.` | **explore** | `explain` | deterministic | Explicit negative constraint against mutation |
