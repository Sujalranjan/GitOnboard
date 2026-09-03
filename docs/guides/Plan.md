# Complete Implementation Roadmap

This is the **frozen implementation roadmap** for the project. It follows the architecture and scope you finalized: a college-level system, not an enterprise platform.

The goal is not to build four disconnected features. You are building **one pipeline**:

> **GitHub Repository → Understand → Plan → Implement → Verify → Repair → Pull Request**

The four intellectual components are **Repository Intelligence, AI Implementation, Independent Verification, and Self-Repair**. Everything else exists to support those components. 

---

# 0. Final System You Are Building

At the end, the system should work like this:

```text
                         USER
                           │
                           ▼
                    ┌─────────────┐
                    │  Next.js UI │
                    └──────┬──────┘
                           │ REST API
                           ▼
                    ┌─────────────┐
                    │   FastAPI   │
                    └──────┬──────┘
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
          ▼                ▼                 ▼
    Repository        Intelligence      Implementation
    Understanding        Engine            Engine
          │                │                 │
          ▼                ▼                 ▼
      AST Parser       RAG/Search       AI Coding Agent
          │                │                 │
          ▼                │                 ▼
    Knowledge Graph       │             Git Worktree
          │                │                 │
          └────────────────┼─────────────────┘
                           ▼
                    Verification
                       Engine
                           │
                    ┌──────┴──────┐
                    │             │
                   PASS          FAIL
                    │             │
                    ▼             ▼
                    PR          Repair Agent
                                  │
                                  └──────► Verify Again

                         PostgreSQL
                              ▲
                              │
               All persistent application data
```

This architecture is directly aligned with the frozen design. 

---

# 1. Phase 0 — Set Up the Development Environment

**Do this first. Do not start building features before the project structure exists.**

## 1.1 Create repository

```text
ai-software-engineer/
```

Initialize Git.

Create:

```text
main
develop
```

You can keep development simple; you don't need enterprise branching strategies.

---

## 1.2 Create frontend

Use:

```text
Next.js
TypeScript
```

Create:

```text
frontend/
```

The frozen frontend structure has six major routes:

```text
/login
/dashboard
/repository/[id]
/repository/[id]/ask
/implementation/[id]
/implementation/[id]/review
```



---

## 1.3 Create backend

Use:

```text
Python
FastAPI
```

Create:

```text
backend/
```

Install the initial dependencies:

* FastAPI
* Uvicorn
* SQLAlchemy
* PostgreSQL driver
* Pydantic
* GitPython or equivalent Git tooling
* AST/tree-sitter tooling
* HTTP client
* LLM SDK
* embedding library/API
* pytest

---

## 1.4 Set up PostgreSQL

Initially run PostgreSQL locally.

Use Docker Compose if convenient:

```text
frontend
backend
postgres
```

That's enough.

**Do not introduce Kubernetes, microservices, Kafka, Redis clusters, Neo4j, Elasticsearch, CDN, autoscaling, etc.** Your frozen specification explicitly excludes those. 

---

## 1.5 Environment variables

Create:

```text
.env.example
```

Eventually you will have things like:

```text
DATABASE_URL=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_TOKEN=
LLM_API_KEY=
EMBEDDING_API_KEY=
SECRET_KEY=
```

Never put actual credentials in Git.

---

# 2. Phase 1 — Build the Database

Before building complex backend logic, establish the data model.

Your database is PostgreSQL. 

## 2.1 User tables

Create:

```text
users
```

Basic fields:

```text
id
name
email
password/auth_provider
created_at
```

---

## 2.2 Repository tables

Create:

```text
repositories
repository_files
repository_symbols
repository_relationships
```

The relationships are:

```text
User
 │
 └── Repository
       │
       ├── Files
       │    └── Symbols
       │
       └── Relationships
```

This becomes the foundation of your repository intelligence system. 

---

## 2.3 Implementation tables

Create:

```text
implementations
implementation_contracts
implementation_plans
```

An implementation belongs to a repository.

Conceptually:

```text
Repository
    │
    └── Implementation
           │
           ├── Requirement
           ├── Contract
           └── Plan
```

---

## 2.4 Agent tables

Create:

```text
agent_runs
agent_events
file_changes
```

You need to record:

* which agent ran
* when it ran
* what task it received
* status
* files changed
* output
* errors
* iteration number

---

## 2.5 Verification tables

Create:

```text
verification_runs
verification_findings
test_results
```

A verification run should contain:

```text
build result
test result
static analysis result
requirement verification
semantic verification
overall result
```

---

## 2.6 Pull request table

Create:

```text
pull_requests
```

Store:

```text
implementation_id
repository_id
branch
PR URL
status
created_at
```

---

## 2.7 Database milestone

**Stop here and test.**

You should be able to:

```text
Create user
     ↓
Create repository
     ↓
Create implementation
     ↓
Create verification run
     ↓
Store findings
```

If this doesn't work cleanly, don't continue.

---

# 3. Phase 2 — Build the FastAPI Foundation

Now build the backend skeleton.

The frozen backend structure is:

```text
backend/
├── api/
├── core/
├── models/
├── repository/
├── intelligence/
├── planning/
├── agent/
├── verification/
├── repair/
└── main.py
```



---

## 3.1 FastAPI application

Create:

```text
main.py
```

Set up:

```text
/api
```

routing.

---

## 3.2 Database connection

Create:

```text
core/database.py
```

Set up:

* SQLAlchemy
* sessions
* models
* migrations

---

## 3.3 Configuration

Create:

```text
core/config.py
```

Load environment variables.

---

## 3.4 Authentication

Create:

```text
api/auth.py
core/security.py
```

Implement basic login/authentication.

For the college version, don't waste time building enterprise identity management.

---

# 4. Phase 3 — Build GitHub Integration

Now the application needs to actually interact with repositories.

Create:

```text
repository/github.py
repository/git.py
repository/clone.py
```

The frontend should allow:

```text
Connect GitHub
      ↓
Select Repository
      ↓
Clone Repository
```

This is the first real end-to-end feature.

---

## 4.1 Repository connection API

Implement:

```http
GET  /api/repositories
POST /api/repositories/connect
GET  /api/repositories/{id}
POST /api/repositories/{id}/analyze
```

These endpoints are part of the frozen API design. 

---

## 4.2 Clone repository

When the user selects a repository:

```text
GitHub
   ↓
Clone
   ↓
Local repository directory
   ↓
Database repository record
```

Store the local repository path/reference.

---

# 5. Phase 4 — Build Repository Analyzer

This is your **first major technical component**.

Create:

```text
repository/analyzer.py
repository/ast_parser.py
repository/graph.py
```

The pipeline is:

```text
GitHub Repository
       ↓
     Clone
       ↓
 File Scanner
       ↓
   AST Parser
       ↓
 ┌─────┼─────┬─────┬─────┐
 Files Classes Functions Imports Calls
       ↓
Relationship Extractor
       ↓
Knowledge Graph
       ↓
PostgreSQL
```



---

# 6. Phase 5 — Implement AST Parsing

Start with **one or two programming languages**, not every language.

For example:

```text
Python
TypeScript
```

Extract:

### Files

```text
path
language
size
```

### Classes

```text
name
file
line
```

### Functions

```text
name
file
line
parameters
```

### Imports

```text
source
target
```

### Function/method calls

```text
caller
callee
```

---

# 7. Phase 6 — Build the Repository Knowledge Graph

Now turn the AST information into relationships.

Example:

```text
auth/routes.py
      │
      ├── imports → auth/service.py
      │
      └── calls → AuthService.login()

AuthService.login()
      │
      └── calls → UserRepository.find()
```

Store those relationships in:

```text
repository_relationships
```

You don't need Neo4j.

PostgreSQL is the source of truth.

---

## 7.1 Graph queries

Implement functions such as:

```text
get_dependencies(file)
get_dependents(file)
get_callers(function)
get_callees(function)
get_related_files(file)
get_affected_components(component)
```

This becomes extremely important later for impact analysis.

---

# 8. Phase 7 — Build Repository UI

Now connect the first backend capability to the frontend.

Repository page:

```text
/repository/[id]
```

Show:

* repository name
* branch
* languages
* file count
* symbol count
* dependencies
* architecture graph
* analysis status

These are explicitly part of the frozen repository interface. 

At this point you should have:

```text
Login
 ↓
Dashboard
 ↓
Connect Repository
 ↓
Analyze
 ↓
Repository Overview
 ↓
Architecture Graph
```

**This is your first major milestone.**

---

# 9. Phase 8 — Build Repository Search

Now implement:

```text
intelligence/search.py
```

Start simple:

```text
PostgreSQL full-text search
```

Search:

* files
* functions
* classes
* symbols
* code snippets

Then add vector search if required.

---

# 10. Phase 9 — Build RAG / Repository Q&A

Create:

```text
intelligence/
├── search.py
├── retrieval.py
├── embeddings.py
├── graph_search.py
└── qa.py
```

The pipeline:

```text
User Question
      ↓
Query Analyzer
      ↓
Keyword Search ──┐
Vector Search ──┤
Graph Search ───┤
                ↓
          Context Builder
                ↓
               LLM
                ↓
         Answer + Sources
```

This is the hybrid repository intelligence layer defined in the frozen design. 

---

## 10.1 Critical requirement

Answers should cite repository evidence.

For example:

> Authentication is handled primarily by `auth/service.py`, which calls `UserRepository`.

Then show:

```text
Sources:
auth/service.py
auth/routes.py
models/user.py
```

Do **not** build a generic ChatGPT clone.

The AI must answer based on the repository.

---

# 11. Phase 10 — Build Repository Q&A Frontend

Create:

```text
/repository/[id]/ask
```

UI:

```text
┌─────────────────────────────────────┐
│ Ask about your repository           │
│                                     │
│ How does authentication work?       │
│                                     │
│ [ Ask ]                             │
└─────────────────────────────────────┘

Answer

Authentication is handled by...

Sources
├── auth/routes.py
├── auth/service.py
└── models/user.py
```

At this point:

**Repository Intelligence is functional.**

---

# 12. Phase 11 — Build Requirement Analyzer

Now you start the actual implementation engine.

Create:

```text
planning/requirements.py
planning/impact_analysis.py
planning/contract.py
planning/planner.py
```

Input:

> Add Google OAuth login.

Output:

```text
Requirement
      ↓
Affected components
      ↓
Acceptance criteria
      ↓
Tests required
```

The implementation pipeline is explicitly:

```text
Natural-language requirement
        ↓
Requirement Analyzer
        ↓
Impact Analysis
        ↓
Implementation Contract
        ↓
Planner
        ↓
Coding Agent
```



---

# 13. Phase 12 — Build Impact Analysis

This is where your knowledge graph becomes useful.

Given:

> Add Google OAuth.

The system should inspect the graph and determine likely affected components:

```text
auth/routes.py
auth/service.py
models/user.py
frontend/Login.tsx
```

The logic should combine:

```text
LLM reasoning
+
Repository search
+
Graph relationships
```

Do not simply ask an LLM:

> "Which files should I modify?"

Give it actual repository evidence.

---

# 14. Phase 13 — Build the Implementation Contract

This is one of the most important pieces.

Convert the requirement into structured data:

```json
{
  "requirement": "Add Google OAuth login",
  "acceptance_criteria": [
    "User can initiate OAuth login",
    "OAuth callback is handled",
    "Existing accounts can be linked",
    "New users can be created",
    "Session is established"
  ],
  "affected_components": [
    "auth/routes.py",
    "auth/service.py",
    "models/user.py",
    "frontend/Login.tsx"
  ],
  "tests_required": [
    "OAuth callback test",
    "Existing account linking test"
  ]
}
```

This contract becomes the **source of truth for verification**. 

This is a key design decision. Do not skip it.

---

# 15. Phase 14 — Build Implementation Planner

Now generate a step-by-step implementation plan.

Example:

```text
1. Add Google OAuth configuration
2. Add OAuth provider
3. Add callback endpoint
4. Add account-linking logic
5. Update user model
6. Update login UI
7. Add OAuth tests
```

Each step should connect to:

```text
affected component
acceptance criterion
expected change
```

---

# 16. Phase 15 — Build Implementation Workspace UI

Create:

```text
/implementation/[id]
```

The main interface should contain:

```text
Requirement
Plan
Agent
Changes
Verification
History
```

The frozen design explicitly makes this the main product page. 

---

# 17. Phase 16 — Build Coding Agent Adapter

Now connect an existing coding-capable AI agent/LLM.

**Do not train your own model.**

The project specification explicitly says to orchestrate an existing coding-capable model/agent. 

Create:

```text
agent/
├── orchestrator.py
├── adapter.py
├── worktree.py
├── execution.py
└── events.py
```

---

## 17.1 Agent adapter

Define a common interface:

```text
CodingAgent
    ├── prepare()
    ├── execute()
    ├── get_changes()
    └── get_output()
```

Then your backend doesn't care exactly which provider you're using.

For the first implementation, support **one agent**.

Multiple agents can be added later.

---

# 18. Phase 17 — Git Worktree

Never let the agent directly modify the canonical branch.

Create:

```text
main repository
       │
       ├── main
       │
       └── implementation-worktree
```

The agent works only inside the worktree.

Pipeline:

```text
Implementation Contract
        ↓
Agent Prompt
        ↓
Coding Agent
        ↓
Git Worktree
        ↓
Read / Modify / Test
        ↓
Git Diff
```

This is the exact implementation mechanism defined in the frozen design. 

---

# 19. Phase 18 — Capture Agent Events

Record:

```text
Agent started
Reading file
Modified file
Running command
Running test
Agent finished
Agent failed
```

Store these in:

```text
agent_events
```

Then display them in the frontend:

```text
✓ Analyzing repository
✓ Creating implementation
✓ Modifying auth/service.py
✓ Modifying Login.tsx
● Running tests
```

---

# 20. Phase 19 — Build Diff Engine

After the agent finishes:

```text
Git Diff
   ↓
Parse changes
   ↓
Changed files
   ↓
Added lines
Removed lines
Modified functions
```

Store this in:

```text
file_changes
```

Frontend:

```text
Changes
────────────────────
auth/service.py
auth/routes.py
models/user.py
frontend/Login.tsx
```

Then provide a diff viewer.

---

# 21. Phase 20 — Build Verification Engine

This is the **most important engineering component after repository intelligence**.

Create:

```text
verification/
├── runner.py
├── build.py
├── tests.py
├── static.py
├── requirements.py
├── semantic.py
└── report.py
```

The verification pipeline should be:

```text
Generated Code
      │
      ├── Build
      ├── Tests
      ├── Static Checks
      │
      ▼
Requirement Check
      │
      ▼
Semantic Review
      │
      ▼
Final Result
```



---

# 22. Phase 21 — Deterministic Verification

Start with checks that don't require AI.

### Build

```text
npm run build
```

or:

```text
python build/test command
```

depending on repository.

### Tests

Run repository tests.

### Static analysis

Examples:

```text
lint
type checking
syntax checking
dependency checks
```

The output becomes:

```text
Build       ✓
Tests       ✓
Static      ✓
```

---

# 23. Phase 22 — Requirement Verification

Now compare the implementation against the Implementation Contract.

For every acceptance criterion:

```text
Criterion
    ↓
Evidence
    ↓
PASS / FAIL
```

Example:

```text
✓ OAuth login button
✓ OAuth callback
✗ Existing account linking
✓ Session creation
```

This is different from simply running tests.

A test can pass while the requested feature is incomplete.

---

# 24. Phase 23 — Semantic Verification

Now use an LLM as an **independent verifier**.

Give it:

```text
Original requirement
Implementation Contract
Affected components
Git diff
Relevant repository context
Test results
Static analysis results
```

Ask it:

```text
Does this implementation satisfy the contract?

What requirements are missing?

Did it modify unrelated behavior?

Are there architectural problems?
```

The result becomes:

```text
verification_findings
```

---

# 25. Phase 24 — Build Verification Report

Generate:

```text
Implementation Complete

Build                  ✓
Existing Tests         ✓
Requirement Coverage   ✓
Architecture           ✓
Semantic Review        ✓

Overall: VERIFIED
```

Or:

```text
Overall: FAILED

Finding:
Account linking is not implemented.

Severity:
HIGH

Affected criterion:
Existing users can link their Google account.
```

The frozen UI explicitly defines this review model. 

---

# 26. Phase 25 — Build Repair Engine

Now create:

```text
repair/repair_loop.py
```

Pipeline:

```text
Implementation
      ↓
Verification
      ↓
   PASS ───────────────→ PR
      │
     FAIL
      ↓
Findings
      ↓
Repair Agent
      ↓
New Changes
      ↓
Verification
```

The frozen design specifies:

```text
MAX_REPAIR_ATTEMPTS = 3
```



Do not make it endlessly autonomous.

---

# 27. Phase 26 — Repair Prompt

The repair agent receives:

```text
Original requirement
Implementation Contract
Previous changes
Verification findings
Failed tests
Static analysis errors
```

Then:

```text
Fix the identified problems.
Do not modify unrelated functionality.
Re-run relevant tests.
```

Then verify again.

---

# 28. Phase 27 — Build History

Store every implementation iteration.

Example:

```text
Implementation #17

Iteration 1
───────────
Agent → FAIL
Finding: Missing account linking

Iteration 2
───────────
Repair → FAIL
Finding: Missing callback error handling

Iteration 3
───────────
Repair → PASS
```

This gives you the history screen and, more importantly, useful evaluation data.

---

# 29. Phase 28 — Pull Request Generation

Only after:

```text
Verification = PASS
```

allow:

```text
Create Pull Request
```

API:

```http
POST /api/implementations/{id}/pull-request
```



PR should contain:

```text
Title
Description
Changed files
Implementation summary
Verification result
Tests
```

The final journey becomes:

```text
Requirement
 ↓
Plan
 ↓
Agent
 ↓
Changes
 ↓
Verification
 ↓
Repair if required
 ↓
VERIFIED
 ↓
Pull Request
```

---

# 30. Phase 29 — Build the Review Page

Create:

```text
/implementation/[id]/review
```

This is the final output screen.

Show:

```text
Implementation Complete

Status: ✓ VERIFIED

Files Changed
────────────────
auth/service.py
auth/routes.py
models/user.py
frontend/Login.tsx

Verification
────────────────
Build             ✓
Tests             ✓
Requirements      ✓
Architecture      ✓
Semantic Review   ✓

[ Create Pull Request ]
```

This should be the page you use heavily during your final project demonstration.

---

# 31. Phase 30 — Complete Dashboard

Only now finish the dashboard.

Show:

### Repositories

```text
my-ecommerce       Python       ✓
task-manager       TypeScript   ✓
```

### Recent implementations

```text
Add Google OAuth       PASS
Password reset         PASS
Email verification     FAIL → Repairing
```

### Recent agent runs

```text
Agent #42    Completed
Agent #41    Failed
Agent #40    Completed
```

### Recent PRs

```text
PR #17    Verified
PR #16    Verified
```

This matches the frozen dashboard concept. 

---

# 32. Phase 31 — Testing

Now systematically test the whole system.

## Unit tests

```text
tests/unit/

test_ast_parser.py
test_graph.py
test_planner.py
test_verifier.py
test_repair.py
```

Test the deterministic logic independently.

---

## Integration tests

```text
tests/integration/

test_repository.py
test_intelligence.py
test_agent.py
test_verification.py
```

Test:

```text
GitHub
 ↓
Repository analysis
 ↓
Graph
 ↓
Search
```

and:

```text
Requirement
 ↓
Planner
 ↓
Agent
 ↓
Diff
 ↓
Verification
```

---

## E2E tests

```text
tests/e2e/

test_implementation.py
test_repair.py
test_pull_request.py
```

The frozen specification already defines this testing structure. 

---

# 33. Phase 32 — Build Your Evaluation Dataset

This is **not optional** if you want the project to have a strong academic component.

Create:

```text
evaluation/
├── benchmark/
├── datasets/
├── results/
└── metrics/
```



Start with:

**10–20 software requirements.**

For example:

```text
1. Add Google OAuth
2. Add password reset
3. Add email verification
4. Add user profile editing
5. Add role-based authorization
6. Add pagination
7. Add search
8. Add file upload
9. Add notification system
10. Add audit logging
```

---

# 34. Phase 33 — Measure the System

For every task, record:

| Metric                 | Question                              |
| ---------------------- | ------------------------------------- |
| Requirement accuracy   | Did the system understand the task?   |
| Impact accuracy        | Did it identify the right components? |
| First-pass success     | Did the agent succeed initially?      |
| Verification precision | Were reported defects real?           |
| Verification recall    | Were actual defects detected?         |
| Repair success         | Did repair fix the problem?           |
| Repair iterations      | How many attempts were needed?        |
| Completion time        | How long did the task take?           |

These are the evaluation metrics already defined in the frozen project. 

---

# 35. Phase 34 — Security

Because you're executing AI-generated code, this part matters.

The minimum architecture:

```text
AI Generated Code
       ↓
Isolated Worktree
       ↓
Restricted Execution
       ↓
Build / Tests / Static Checks
```



Implement:

* isolated worktree
* execution timeout
* restricted environment
* backend-only API keys
* encrypted/secure GitHub credentials
* no provider secrets in frontend

Don't turn this into an enterprise security project.

The objective is simply:

> **AI-generated code must not get unrestricted access to your host system.**

---

# 36. Phase 35 — Deployment

Now deploy the completed prototype.

Keep deployment boring.

## Recommended deployment architecture

```text
                    Internet
                       │
                       ▼
                ┌─────────────┐
                │   Frontend  │
                │   Next.js   │
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │   FastAPI   │
                │   Backend   │
                └──────┬──────┘
                       │
              ┌────────┴────────┐
              │                 │
              ▼                 ▼
        PostgreSQL         Local storage
                              /worktrees
```

You do **not** need:

```text
Kubernetes
CDN
multi-region
autoscaling
service mesh
distributed queues
```

Your frozen project explicitly rejects these for this scope. 

---

# 37. Phase 36 — Dockerize the Application

Create:

```text
docker/
    Dockerfile
```

and:

```text
docker-compose.yml
```

The repository structure already includes both. 

At minimum:

```text
Docker Compose
 ├── frontend
 ├── backend
 └── postgres
```

This is sufficient for:

* local development
* evaluator setup
* demonstration
* reproducibility

---

# 38. Phase 37 — Production-Like Deployment, But Small

Use one simple server/cloud deployment.

For example:

```text
Single VM
   │
   └── Docker Compose
        ├── Next.js
        ├── FastAPI
        └── PostgreSQL
```

If using managed PostgreSQL is easier, that's fine:

```text
VM
 ├── Next.js
 └── FastAPI

Managed PostgreSQL
```

The point is not the vendor.

The point is:

> **Someone else should be able to run your complete system from your README.**

---

# 39. Phase 38 — Deployment Checklist

Before declaring the project finished:

### Frontend

```text
✓ Production build works
✓ API URL configured
✓ Login works
✓ Repository pages work
✓ Q&A works
✓ Implementation page works
✓ Diff viewer works
✓ Verification page works
```

### Backend

```text
✓ FastAPI starts
✓ Database connection works
✓ GitHub integration works
✓ Repository analysis works
✓ RAG works
✓ Planner works
✓ Agent works
✓ Verification works
✓ Repair works
✓ PR generation works
```

### Database

```text
✓ Tables created
✓ Migrations work
✓ Data persists
✓ Implementation history persists
```

### Deployment

```text
✓ Docker build works
✓ Docker Compose works
✓ Environment variables documented
✓ README setup instructions work
✓ Complete demo can run from clean installation
```

---

# 40. Phase 39 — Final End-to-End Validation

Now perform the exact demonstration you will eventually give your evaluator.

## Test repository

Connect:

```text
Example GitHub repository
```

Then:

### Step 1

```text
Connect repository
```

### Step 2

```text
Analyze repository
```

### Step 3

Ask:

> How does authentication work?

Verify that the system returns repository-grounded sources.

### Step 4

Request:

> Add Google OAuth login.

### Step 5

Show:

```text
Requirement
 ↓
Affected components
 ↓
Acceptance criteria
 ↓
Implementation Contract
 ↓
Plan
```

### Step 6

Run agent.

### Step 7

Show:

```text
Agent events
 ↓
Git diff
```

### Step 8

Run verification.

### Step 9

Intentionally demonstrate a failure if possible:

```text
Missing criterion
 ↓
Verification FAIL
```

### Step 10

Run repair.

```text
Repair
 ↓
Verification
 ↓
PASS
```

### Step 11

Create PR.

That single workflow demonstrates almost the entire project.

---

# 41. Recommended Build Order

If you want the shortest possible version of the roadmap, follow **exactly this order**:

```text
01. Project repository
        ↓
02. Frontend + FastAPI skeleton
        ↓
03. PostgreSQL + database models
        ↓
04. Authentication
        ↓
05. GitHub integration
        ↓
06. Repository cloning
        ↓
07. File scanner
        ↓
08. AST parser
        ↓
09. Symbol extraction
        ↓
10. Relationship extraction
        ↓
11. Knowledge graph
        ↓
12. Repository page
        ↓
13. Search
        ↓
14. Embeddings/vector retrieval
        ↓
15. Graph retrieval
        ↓
16. RAG Q&A
        ↓
17. Q&A frontend
        ↓
18. Requirement analyzer
        ↓
19. Impact analysis
        ↓
20. Implementation Contract
        ↓
21. Implementation planner
        ↓
22. Implementation workspace UI
        ↓
23. Coding-agent adapter
        ↓
24. Git worktree
        ↓
25. Agent execution
        ↓
26. Diff engine
        ↓
27. Build verification
        ↓
28. Test verification
        ↓
29. Static verification
        ↓
30. Requirement verification
        ↓
31. Semantic verification
        ↓
32. Verification report
        ↓
33. Repair engine
        ↓
34. Repair loop
        ↓
35. History
        ↓
36. PR generation
        ↓
37. Review page
        ↓
38. Unit tests
        ↓
39. Integration tests
        ↓
40. E2E tests
        ↓
41. Evaluation benchmark
        ↓
42. Metrics
        ↓
43. Security hardening
        ↓
44. Dockerization
        ↓
45. Deployment
        ↓
46. Final end-to-end validation
```

---

# 42. Milestones You Should Use

Don't measure progress by "I built some frontend today." Measure it by working system capabilities.

### Milestone 1 — Repository ingestion

```text
GitHub
 ↓
Clone
 ↓
Parse
 ↓
PostgreSQL
```

**Done when:** repository structure is stored.

---

### Milestone 2 — Repository Intelligence

```text
Repository
 ↓
Graph + Search
 ↓
Q&A
```

**Done when:** you can ask meaningful questions about a real repository and receive source-backed answers.

---

### Milestone 3 — Planning

```text
Requirement
 ↓
Impact Analysis
 ↓
Implementation Contract
 ↓
Plan
```

**Done when:** the system can produce a structured implementation plan.

---

### Milestone 4 — AI Implementation

```text
Plan
 ↓
Agent
 ↓
Worktree
 ↓
Diff
```

**Done when:** the agent can implement a real change in an isolated worktree.

---

### Milestone 5 — Verification

```text
Diff
 ↓
Build
 ↓
Tests
 ↓
Static
 ↓
Requirement
 ↓
Semantic
```

**Done when:** the system can identify an intentionally incomplete implementation.

---

### Milestone 6 — Self-Repair

```text
FAIL
 ↓
Finding
 ↓
Repair
 ↓
Verify
 ↓
PASS
```

**Done when:** the system can successfully repair at least some intentionally introduced failures.

---

### Milestone 7 — Complete Product

```text
Requirement
 ↓
Implementation
 ↓
Verification
 ↓
Repair
 ↓
PR
```

**Done when:** the entire pipeline works without manual intervention except approval/final review.

---

### Milestone 8 — Academic Evaluation

```text
10–20 tasks
 ↓
Run benchmark
 ↓
Collect metrics
 ↓
Compare results
 ↓
Analyze failures
```

**Done when:** you have actual quantitative results for your final report.

---

# 43. What You Should NOT Build

This is important because your biggest risk is **scope creep**, not technical difficulty.

Do not suddenly decide you need:

```text
❌ Kubernetes
❌ Microservices
❌ Kafka
❌ Neo4j
❌ Elasticsearch
❌ Redis cluster
❌ CDN
❌ Multi-region deployment
❌ Autoscaling
❌ Enterprise SSO
❌ SOC 2
❌ Runtime monitoring platform
❌ Autonomous production deployment
❌ Custom foundation model
❌ IDE replacement
❌ Mobile application
❌ Billing
❌ Team/project management
❌ Enterprise governance
```

Your specification explicitly identifies these as unnecessary for this project. 

If you find yourself working on infrastructure instead of:

> **understanding code, planning changes, implementing changes, verifying changes, or repairing changes**

you are probably drifting out of scope.

---

# 44. The Actual Priority Order

If time becomes limited, prioritize like this:

### Tier 1 — Absolutely required

```text
Repository ingestion
AST parsing
Knowledge graph
Repository Q&A
Requirement analysis
Implementation Contract
Implementation planning
Coding agent
Git worktree
Diff analysis
Verification
Repair loop
```

### Tier 2 — Required for a polished product

```text
Authentication
Dashboard
Repository UI
Implementation workspace
Verification report
History
PR generation
```

### Tier 3 — Academic quality

```text
Unit tests
Integration tests
E2E tests
Evaluation dataset
Metrics
Failure analysis
```

### Tier 4 — Nice to have

```text
Multiple agents
Advanced architecture rules
More languages
Better graph visualization
Advanced Git history analysis
```

If Tier 1 isn't working, **do not touch Tier 4**.

---

# 45. Final Definition of Done

The project is finished when a user can do this:

```text
1. Login
      ↓
2. Connect GitHub repository
      ↓
3. System analyzes repository
      ↓
4. Explore repository architecture
      ↓
5. Ask questions about the codebase
      ↓
6. Enter a software requirement
      ↓
7. System identifies affected components
      ↓
8. System creates Implementation Contract
      ↓
9. System generates implementation plan
      ↓
10. Coding agent implements the change
      ↓
11. Changes happen inside isolated worktree
      ↓
12. System collects Git diff
      ↓
13. Build runs
      ↓
14. Tests run
      ↓
15. Static checks run
      ↓
16. Requirements are checked
      ↓
17. Semantic verification runs
      ↓
18. If failed → repair agent
      ↓
19. Verification runs again
      ↓
20. If passed → VERIFIED
      ↓
21. Generate Pull Request
```

That is the project.

Everything else is supporting infrastructure.

The frozen document describes the same fundamental journey from GitHub connection through analysis, planning, implementation, independent verification, repair, and finally a verified PR. 

**Build in that order. Don't build the frontend first for weeks, and don't build the AI agent first.** Build vertically: get a thin version of the entire pipeline working, then deepen each stage. The first serious target should be:

> **One repository + one requirement + one agent + one verification cycle + one successful repair.**

Once that works end-to-end, the rest is expansion rather than architectural guesswork.
