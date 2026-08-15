# Frontend AI Agent Guidelines

This document governs AI agent behavior when working in the `frontend/` directory.

## Technology Stack
- **Framework**: Next.js 16 (App Router in `frontend/app/`)
- **Library**: React 19 (`react`, `react-dom`)
- **Styling**: Tailwind CSS 4 (`@tailwindcss/postcss`)
- **Graph Visualization**: ReactFlow (`reactflow`), Dagre (`dagre`), D3 Force (`d3-force`)
- **Icons & Animation**: Lucide React (`lucide-react`), Framer Motion (`framer-motion`)
- **Theming**: Next Themes (`next-themes`)
- **Language**: TypeScript (`typescript`)

## Core Frontend Rules
1. **API Consumption Only**: The frontend consumes backend APIs exclusively via HTTP fetch/client services (`frontend/services/`). Never attempt direct database or filesystem access.
2. **Never Invent Endpoints**: All API requests must target endpoints documented in [API.md](../API.md) and implemented in FastAPI routers (`backend/routers/`).
3. **No Business Logic Duplication**: Keep business logic (AST parsing, graph building, metrics calculation) in the backend. The frontend handles visualization, user interaction, and state presentation.
4. **App Router Structure**:
   - `frontend/app/page.tsx`: Landing page.
   - `frontend/app/dashboard/page.tsx`: Repository management & import dashboard.
   - `frontend/app/repository/[repoName]/page.tsx`: Repository overview workspace.
   - `frontend/app/repository/[repoName]/[tab]/page.tsx`: Tabbed analysis views (Files, Dependencies, Architecture, Call Graph, Symbols, Search, Semantic, Summary, Metrics).
   - `frontend/app/repository/[repoName]/trace/page.tsx`: Feature execution flow tracer.
5. **Real-Time Task Updates**: Consume long-running task progress using the Server-Sent Events (SSE) stream at `/api/repos/{repo_name}/tasks/stream`.
6. **Validation**: Always run `npm run lint` or `next build` to verify type and build correctness before concluding frontend tasks.
