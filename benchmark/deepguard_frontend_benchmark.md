# DeepGuard Frontend Benchmark

15 rigorous questions targeting the DeepGuard Frontend application (Next.js 15 App Router, React 19, Zustand store, and Tailwind CSS).

> **Evaluation Rule:** Every question specifies concrete `required_evidence`, `expected_symbols`, `expected_answer_points`, and `difficulty` levels (L1–L5). A rigorous agent evaluation must grade answers against these ground-truth expectations.

---

## DGF01 — Architecture (L3)
**Question:** How does the DeepGuard frontend track real-time upload progress, frame-by-frame analysis progress, and final detection confidences across components? Trace analysisStore.ts, its actions, and which components subscribe to its state.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `False`

**Required Evidence Files:**
- `lib/store/analysisStore.ts`
- `src/components/UploadArea.tsx`
- `src/components/NewAnalysisContent.tsx`

**Supporting Evidence:**
- `src/components/AnalysisPage.tsx`
- `src/app/dashboard/analysis/[id]/page.tsx`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/hooks-logic/useAccountSettingsLogic.ts`
- `src/components/StatCard.tsx`

**Expected Symbols:** `useAnalysisStore, setCurrentAnalysis, updateAnalysisProgress, resetAnalysis`

**Expected Concepts:** `Zustand state store, global reactive subscription, upload vs analysis phase transitions, frame-wise confidence arrays, persisted vs ephemeral state`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, graph_traversal`

**Expected Answer Points:**
1. lib/store/analysisStore.ts creates a Zustand store (useAnalysisStore) holding currentAnalysis, analysisHistory, and active progress counters.
1. UploadArea.tsx reads uploadProgress, currentFrame, and totalFrames to display progress bars and frame counter badges.
1. NewAnalysisContent.tsx manages high-level state ('IDLE' | 'UPLOADING' | 'ANALYZING') and dispatches store actions upon upload initiation and completion.
1. AnalysisPage.tsx and the [id] page subscribe to currentAnalysis to render confidence scores, frame lists, and annotated media.
1. Actions include setting analysis results, updating frame progress, and clearing state when a new analysis starts.

**Expected Answer Structure:**
- Zustand store architecture and interface definition
- state properties (progress, frames, confidence report)
- producer components (NewAnalysisContent, UploadArea)
- consumer components (AnalysisPage, dashboard pages)

**Known Traps & Failure Modes:**
- Assuming Redux Toolkit or React Context is used when it is pure Zustand
- Confusing analysisStore.ts with account settings logic hooks

---

## DGF02 — Security (L4)
**Question:** How does the frontend communicate with the backend while preventing token exposure to client-side scripts? Trace the apiFetch wrapper in api.ts, how it handles 401 token expiration, token refresh loops without infinite retries, and how Next.js rewrites/proxies requests.

- **Category:** `security`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 4, Hops: 4, Concepts: 5)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `src/lib/api.ts`
- `next.config.ts`
- `middleware.ts`

**Supporting Evidence:**
- `lib/auth.ts`
- `src/services/authService.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/lib/logger.ts`

**Expected Symbols:** `apiFetch, credentials: 'include', refresh`

**Expected Concepts:** `HttpOnly cookie isolation, Next.js rewrite proxy (API_URL = ''), 401 interception, refresh loop recursion guard (url.includes('/refresh')), replay of original request`

**Expected Tool Capabilities:** `repository_search, file_read, cross_file_trace`

**Expected Answer Points:**
1. apiFetch in src/lib/api.ts sets credentials: 'include' so that HttpOnly session cookies are transmitted automatically without JavaScript accessing raw tokens.
1. Next.js next.config.ts configures rewrites to proxy client API calls to the backend server, avoiding CORS and cookie domain mismatches.
1. When a request returns HTTP 401 Unauthorized, apiFetch intercepts the response.
1. It includes a guard: if the failed request itself was '/refresh', it aborts immediately to prevent infinite recursive refresh loops.
1. Otherwise, it issues a POST /auth/refresh with credentials: 'include'; if successful, it retries the original request.

**Expected Answer Structure:**
- HttpOnly cookie transport and credentials flag
- Next.js rewrite proxy configuration
- 401 interception and token refresh flow
- infinite recursion guard logic
- automatic request replay

**Known Traps & Failure Modes:**
- Assuming access tokens are stored in localStorage or sessionStorage (they are in HttpOnly cookies)
- Missing the url.includes('/refresh') safety guard that prevents browser lockup

---

## DGF03 — User Interaction (L3)
**Question:** Trace the user upload interaction in UploadArea.tsx and NewAnalysisContent.tsx. How are file types (mp4, avi, mov vs. jpg, png) and max file sizes (10MB) validated before network dispatch, and how is the frame sampling count configured via FrameInputModal?

- **Category:** `user_interaction`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 3, Concepts: 4)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/components/UploadArea.tsx`
- `src/components/NewAnalysisContent.tsx`
- `src/components/FrameInputModal.tsx`

**Supporting Evidence:**
- `src/styles/NewAnalysis.module.css`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/FeatureList.tsx`

**Expected Symbols:** `handleFileChange, handleDrop, FrameInputModal, MAX_FILE_SIZE_MB, SUPPORTED_FORMATS`

**Expected Concepts:** `drag-and-drop event handling, client-side file size guard (10MB), MIME type and extension validation, frame count customization modal (10–100 frames), error state dispatch`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. UploadArea.tsx handles drag events (dragOver, dragLeave, drop) and standard file input changes.
1. NewAnalysisContent.tsx validates that file.size <= MAX_FILE_SIZE_MB * 1024 * 1024; if exceeded, displays an error alert without network dispatch.
1. Validates file extensions against SUPPORTED_FORMATS depending on selected analysis type (VIDEO vs IMAGE).
1. For video files, FrameInputModal allows the user to configure how many frames to extract (defaulting to 30 or 50 frames).
1. Once confirmed, the component transitions to 'UPLOADING' state and initiates the multipart request.

**Expected Answer Structure:**
- drag-and-drop and file input listener
- client-side size and MIME validation logic
- FrameInputModal configuration and frame limits
- state transitions from IDLE to UPLOADING

**Known Traps & Failure Modes:**
- Assuming file validation happens purely on the backend (the frontend enforces strict pre-flight checks)
- Overlooking FrameInputModal which lets users select frame count before upload

---

## DGF04 — Data Visualization (L3)
**Question:** After a video is analyzed, how does the frontend render the confidence progression over time and individual frame details? Trace ConfidenceOverTimeChart.tsx and FrameAnalysisSection.tsx, including data formatting and animation hooks.

- **Category:** `data_visualization`
- **Answer Type:** `explanation`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/components/ConfidenceOverTimeChart.tsx`
- `src/components/FrameAnalysisSection.tsx`
- `src/hooks/useChartAnimation.ts`

**Supporting Evidence:**
- `src/components/AnalysisPage.tsx`
- `src/styles/FrameAnalysis.module.css`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/DashboardStatCard.tsx`

**Expected Symbols:** `ConfidenceOverTimeChart, FrameAnalysisSection, useChartAnimation`

**Expected Concepts:** `frame-wise confidence time-series, chart rendering (Chart.js / Recharts or custom SVG/canvas), threshold color coding (real vs fake thresholds), frame thumbnail selection, animation timing hook`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. ConfidenceOverTimeChart receives frame_wise_confidences array from the analysis result.
1. Maps indices to frame numbers / timestamps along the X-axis and probability (0.0 to 1.0 or 0-100%) along the Y-axis.
1. Applies color gradient or threshold line indicating high risk (> 50-70% fake probability).
1. useChartAnimation animates line rendering and data point entrance on component mount.
1. FrameAnalysisSection renders interactive frame tiles allowing users to click and inspect specific annotated frames.

**Expected Answer Structure:**
- data ingestion from analysis model
- chart layout and axis mappings
- threshold indicator styling
- useChartAnimation hook behavior
- frame thumbnail navigation

**Known Traps & Failure Modes:**
- Assuming chart uses generic hardcoded sample data rather than analysis.frame_wise_confidences
- Missing that useChartAnimation controls the visual transition

---

## DGF05 — Security (L2)
**Question:** How does the frontend prevent unauthenticated users from visiting /dashboard, /dashboard/analysis, or /dashboard/account? Trace middleware.ts, how session tokens are checked on edge requests, and the redirection flow for expired sessions.

- **Category:** `security`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `middleware.ts`
- `lib/auth.ts`

**Supporting Evidence:**
- `src/app/dashboard/layout.tsx`
- `src/app/login/page.tsx`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/app/theme-provider.tsx`

**Expected Symbols:** `middleware, matcher, NextResponse.redirect`

**Expected Concepts:** `Next.js edge middleware, route matcher pattern (/dashboard/:path*), cookie presence validation (refreshToken/accessToken), redirect to /login?redirect=..., public route exemptions (/login, /signup, /try-without-account)`

**Expected Tool Capabilities:** `repository_search, file_read`

**Expected Answer Points:**
1. middleware.ts runs at the Next.js edge runtime before any page renders.
1. Defines a matcher config covering '/dashboard/:path*'.
1. Inspects request.cookies for the presence of session tokens (e.g. 'accessToken' or 'refreshToken').
1. If tokens are missing or invalid, it redirects the client to '/login' with a return URL parameter.
1. Public routes like '/', '/login', '/signup', and '/try-without-account' are bypassed.

**Expected Answer Structure:**
- middleware location and execution environment
- route matching rules
- cookie inspection logic
- redirection mechanism and query preservation

**Known Traps & Failure Modes:**
- Assuming route protection is done solely inside useEffect in client components (it is enforced in Next.js middleware)
- Confusing Next.js edge middleware.ts with Express backend middleware

---

## DGF06 — User Interaction (L3)
**Question:** How does the guest flow work when a user selects 'Try Without Account'? Trace the page component at /try-without-account, how it interfaces with the backend trial endpoints, and what UI restrictions are placed on guest analyses.

- **Category:** `user_interaction`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/app/try-without-account/page.tsx`
- `src/components/NewAnalysisContent.tsx`
- `src/lib/api.ts`

**Supporting Evidence:**
- `lib/store/analysisStore.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/app/login/page.tsx`

**Expected Symbols:** `TryWithoutAccountPage, NewAnalysisContent`

**Expected Concepts:** `anonymous trial workflow, trial mode flag in upload component, limited upload quota / frame caps, conversion CTA prompting account creation`

**Expected Tool Capabilities:** `repository_search, file_read, cross_file_trace`

**Expected Answer Points:**
1. src/app/try-without-account/page.tsx mounts NewAnalysisContent configured in guest/trial mode.
1. Communicates with backend trial endpoints (/trial and /trial/analyze) using generated fingerprint headers.
1. Restricts features: disables history persistence and locks advanced batch options.
1. Upon completion, displays analysis results alongside prominent conversion CTAs to register for full history and export features.

**Expected Answer Structure:**
- page route and component configuration
- API communication and trial headers
- guest UI limitations compared to authenticated dashboard
- post-analysis registration prompt

**Known Traps & Failure Modes:**
- Assuming guest users receive a mock simulated result (they call real trial backend endpoints)
- Missing that trial mode uses the same core NewAnalysisContent component with specialized flags

---

## DGF07 — Data Flow (L2)
**Question:** How does AnalysisHistory.tsx render past analysis records? Trace how historical items are fetched, how processing/completed/failed badges are displayed, and how users navigate to historical analysis details.

- **Category:** `data_flow`
- **Answer Type:** `explanation`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/components/AnalysisHistory.tsx`
- `src/app/dashboard/history/page.tsx`

**Supporting Evidence:**
- `src/hooks/useHistoryAnimation.ts`
- `src/lib/api.ts`
- `src/styles/AnalysisHistory.module.css`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/RecentAnalyses.tsx`

**Expected Symbols:** `AnalysisHistory, fetchHistory, useHistoryAnimation`

**Expected Concepts:** `historical record query (GET /analysis/history), status badge rendering with variant colors, confidence badge calculation, link to dynamic route /dashboard/analysis/[id]`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. AnalysisHistory fetches records on mount via apiFetch('/analysis/history') or reads from analysisStore.
1. Renders tabular or card-based records with filename, timestamp, frames analyzed, and status badges.
1. Status badges apply green for 'completed', yellow/blue for 'processing', and red for 'failed'.
1. Confidence scores are styled with warning colors if detected as deepfake.
1. Clicking a row navigates to /dashboard/analysis/${analysis.id} for the full analytical report.

**Expected Answer Structure:**
- data fetching trigger and endpoint
- table layout and status badge mappings
- risk level visual indicators
- dynamic routing navigation

**Known Traps & Failure Modes:**
- Confusing AnalysisHistory.tsx (full history view) with RecentAnalyses.tsx (dashboard widget)
- Assuming data is mock-generated rather than fetched from backend Supabase records

---

## DGF08 — Architecture (L3)
**Question:** Trace how user account settings, profile information, and active device sessions are displayed and updated in /dashboard/account. Which components handle password changes, and how does logging out of all devices trigger client-side session cleanup?

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 5, Hops: 3, Concepts: 4)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/app/dashboard/account/page.tsx`
- `src/components/AccountProfile.tsx`
- `src/components/AccountSettings.tsx`
- `src/components/AccountDataManagement.tsx`
- `src/hooks-logic/useAccountSettingsLogic.ts`

**Supporting Evidence:**
- `src/styles/Account.module.css`
- `src/lib/api.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/UserProfileCard.tsx`

**Expected Symbols:** `useAccountSettingsLogic, handleUpdateProfile, handleLogoutAllDevices, handleChangePassword`

**Expected Concepts:** `modular account dashboard tabs, custom hook for business logic (useAccountSettingsLogic), device session revocation API call, client store purge and redirect to /login`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. src/app/dashboard/account/page.tsx composes AccountProfile, AccountSettings, and AccountDataManagement.
1. useAccountSettingsLogic.ts encapsulates form state, validation, and API mutation handlers.
1. AccountSettings handles name, avatar, and password modification via PATCH/POST endpoints.
1. AccountDataManagement triggers 'Logout from all devices' calling apiFetch('/auth/logout-all', { method: 'POST' }).
1. On success, client clears Zustand store, wipes cached profile state, and redirects to /login.

**Expected Answer Structure:**
- page composition and component hierarchy
- logic separation in useAccountSettingsLogic.ts
- password and profile update flows
- logout-all-devices invocation and client-side cleanup

**Known Traps & Failure Modes:**
- Looking for form handlers directly inside page.tsx instead of useAccountSettingsLogic.ts
- Confusing single-device logout with global device revocation

---

## DGF09 — User Interaction (L2)
**Question:** Trace the forget password user journey in ForgetPasswordModal.tsx. How are the request OTP and verify OTP steps partitioned, what error handling is surfaced to the user, and how does the modal return the user to login?

- **Category:** `user_interaction`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/components/ForgetPasswordModal.tsx`
- `src/components/Login.tsx`
- `src/services/authService.ts`

**Supporting Evidence:**
- `src/styles/ForgetPassword.module.css`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/Signup.tsx`

**Expected Symbols:** `ForgetPasswordModal, step, handleSendOtp, handleResetPassword`

**Expected Concepts:** `multi-step modal state machine (STEP_EMAIL -> STEP_OTP -> STEP_SUCCESS), countdown timer for resend OTP, inline error alerts, modal visibility callback to parent Login component`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. ForgetPasswordModal manages an internal step state (e.g. 1: Enter Email, 2: Enter OTP & New Password).
1. Step 1 calls authService.sendResetOtp(email); upon success, advances to Step 2 and starts a resend cooldown timer.
1. Step 2 collects 6-digit OTP and new password, calling authService.resetPassword(email, otp, newPassword).
1. Displays validation errors (invalid email, wrong OTP, weak password) via styled error boxes.
1. On successful reset, shows confirmation message and closes modal, focusing user back on the login form.

**Expected Answer Structure:**
- modal mounting and step state representation
- Step 1: OTP request and timer initialization
- Step 2: verification and password update API dispatch
- error handling and return to login transition

**Known Traps & Failure Modes:**
- Assuming password reset is a separate route rather than an overlay modal on /login
- Overlooking the two-stage step transition inside the modal

---

## DGF10 — Configuration (L1)
**Question:** How is dark/light theme switching implemented across DeepGuard? Trace theme-provider.tsx, ThemeToggleButton.tsx, and how theme classes are applied to Tailwind CSS and CSS Modules.

- **Category:** `configuration`
- **Answer Type:** `explanation`
- **Difficulty:** `L1` (Files: 3, Hops: 1, Concepts: 3)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/app/theme-provider.tsx`
- `src/components/ThemeToggleButton.tsx`
- `tailwind.config.js`

**Supporting Evidence:**
- `src/lib/theme.tsx`
- `src/styles/Global.module.css`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/Sidebar.tsx`

**Expected Symbols:** `ThemeProvider, ThemeToggleButton, useTheme, darkMode: 'class'`

**Expected Concepts:** `next-themes or custom React Context, class-based dark mode in Tailwind, localStorage persistence, hydration mismatch avoidance (suppressHydrationWarning), Sun/Moon icon toggle`

**Expected Tool Capabilities:** `repository_search, file_read`

**Expected Answer Points:**
1. src/app/theme-provider.tsx wraps the root application layout providing theme context.
1. tailwind.config.js specifies darkMode: 'class', toggling dark styles when 'dark' class is present on <html> or <body>.
1. ThemeToggleButton.tsx renders Sun/Moon icons and calls toggleTheme on click.
1. Stores preference in localStorage to persist user selection across reloads.
1. Includes hydration protection to prevent flicker during server-side rendering.

**Expected Answer Structure:**
- provider configuration in root layout
- Tailwind class strategy
- toggle component interaction
- localStorage persistence and SSR hydration guards

**Known Traps & Failure Modes:**
- Assuming pure system media query without manual user override toggle
- Confusing global Tailwind styles with localized CSS module theme tokens

---

## DGF11 — Cross File Reasoning (L2)
**Question:** How does the frontend render repository contributor statistics and project info? Trace ContributorList.tsx and GithubRepoCard.tsx from data retrieval to grid display.

- **Category:** `cross_file_reasoning`
- **Answer Type:** `explanation`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/components/ContributorList.tsx`
- `src/components/GithubRepoCard.tsx`
- `src/app/dashboard/contributions/page.tsx`

**Supporting Evidence:**
- `src/lib/api.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/FeatureList.tsx`

**Expected Symbols:** `ContributorList, GithubRepoCard, ContributionsPage`

**Expected Concepts:** `API data fetching (/github/contributors, /github/stats), contributor card grid layout, avatar image loading with fallback, star and fork badge rendering`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. src/app/dashboard/contributions/page.tsx queries backend GitHub endpoints on mount via apiFetch.
1. GithubRepoCard renders repository name, description, star count, and fork count with external GitHub link.
1. ContributorList iterates over contributor objects, displaying avatar, username, commit contributions, and profile URL.
1. Uses responsive CSS grid for layout and includes loading skeletons while data is in flight.

**Expected Answer Structure:**
- page mounting and API invocation
- GithubRepoCard presentation
- ContributorList iteration and avatar handling
- responsive grid layout

**Known Traps & Failure Modes:**
- Assuming contributors are hardcoded in the frontend rather than retrieved from backend GitHub API proxy

---

## DGF12 — Architecture (L3)
**Question:** DeepGuard features custom page and dashboard transitions. Trace the custom animation hooks (e.g. useDashboardAnimations.ts, useAnalysisResultsAnimation.ts) and explain how entry and exit animations are structured without degrading rendering performance.

- **Category:** `architecture`
- **Answer Type:** `explanation`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 4)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/hooks/useDashboardAnimations.ts`
- `src/hooks/useAnalysisResultsAnimation.ts`
- `src/hooks/useChartAnimation.ts`

**Supporting Evidence:**
- `src/styles/Dashboard.module.css`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/styles/Global.module.css`

**Expected Symbols:** `useDashboardAnimations, useAnalysisResultsAnimation, useChartAnimation`

**Expected Concepts:** `ref-based DOM animation binding, staggered card entrance timing, hardware-accelerated CSS transforms (translateY, opacity), cleanup and unmount safety`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. Custom hooks in src/hooks/ isolate animation side-effects from component business logic.
1. useDashboardAnimations attaches refs to dashboard stat cards and welcome banners, triggering staggered opacity/transform keyframes on mount.
1. useAnalysisResultsAnimation sequences score counter increments and chart reveal after analysis completes.
1. Leverages CSS transitions / transforms rather than heavy JavaScript loops to ensure 60fps rendering.
1. Ensures animation refs are cleaned up on unmount to prevent memory leaks.

**Expected Answer Structure:**
- hook separation architecture
- staggered transition sequencing
- CSS transform optimization
- component lifecycle attachment and cleanup

**Known Traps & Failure Modes:**
- Assuming heavy Framer Motion library is mandatory when custom ref-driven CSS module hooks are used
- Overlooking that hooks are organized under src/hooks/ with clean naming

---

## DGF13 — Data Flow (L1)
**Question:** Trace BugReportForm.tsx. How are form data, browser environment details, and optional attachments structured before being sent to the backend /support route?

- **Category:** `data_flow`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L1` (Files: 2, Hops: 1, Concepts: 2)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/components/BugReportForm.tsx`
- `src/lib/api.ts`

**Supporting Evidence:**
- `src/lib/logger.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/ForgetPasswordModal.tsx`

**Expected Symbols:** `BugReportForm, handleSubmit, apiFetch`

**Expected Concepts:** `support form input state, automatic user-agent / navigator diagnostic collection, multipart/JSON payload serialization, submission toast feedback`

**Expected Tool Capabilities:** `repository_search, file_read`

**Expected Answer Points:**
1. BugReportForm manages form state for title, description, category, and severity.
1. Optionally attaches browser metadata (navigator.userAgent, window resolution) to assist backend reproduction.
1. Dispatches payload to apiFetch('/support/bug-report', { method: 'POST', body: ... }).
1. Displays success notification or error message, clearing form inputs on completion.

**Expected Answer Structure:**
- form state and input bindings
- diagnostic environment extraction
- API request construction
- UI feedback and reset logic

**Known Traps & Failure Modes:**
- Assuming bug reports are pushed directly to GitHub API from client (they route through backend support handler)

---

## DGF14 — Data Visualization (L3)
**Question:** How does the image inspection view differ from video analysis? Trace ImageAnalysisSection.tsx and DeepfakeAlertCard.tsx to explain how single-frame confidence results and heatmaps/bounding boxes are displayed.

- **Category:** `data_visualization`
- **Answer Type:** `comparison`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `src/components/ImageAnalysisSection.tsx`
- `src/components/DeepfakeAlertCard.tsx`
- `src/components/AnalysisPage.tsx`

**Supporting Evidence:**
- `src/styles/ImageAnalysis.module.css`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/FrameAnalysisSection.tsx`
- `src/components/ConfidenceOverTimeChart.tsx`

**Expected Symbols:** `ImageAnalysisSection, DeepfakeAlertCard, AnalysisPage`

**Expected Concepts:** `single image presentation layout, DeepfakeAlertCard threat level badge, absence of temporal time-series slider, annotated image zoom and inspection`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. AnalysisPage branches between video and image analysis based on media type.
1. ImageAnalysisSection renders a static annotated viewport displaying the image with face bounding boxes.
1. Omits the ConfidenceOverTimeChart and FrameAnalysisSection which are video-exclusive.
1. DeepfakeAlertCard presents a prominent risk assessment (Likely Deepfake vs Likely Authentic) with confidence percentage and forensic summary.

**Expected Answer Structure:**
- media type branching in AnalysisPage
- ImageAnalysisSection layout specifics
- DeepfakeAlertCard visual structure
- differences from video analysis views

**Known Traps & Failure Modes:**
- Assuming image analysis renders an empty video chart instead of switching to ImageAnalysisSection
- Confusing DeepfakeAlertCard with generic DashboardStatCard

---

## DGF15 — Cross File Reasoning (L5)
**Question:** Trace a complete user analysis journey: User logs in via Login.tsx, navigates to /dashboard/new-analysis, drops a video file in UploadArea.tsx, selects 30 frames in FrameInputModal.tsx, clicks analyze, observes the upload progress and loading spinner, is redirected to /dashboard/analysis/[id], and views the final confidence score in AnalysisHeader.tsx and chart in ConfidenceOverTimeChart.tsx. Detail every state transition, API call, and Zustand action along the way.

- **Category:** `cross_file_reasoning`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L5` (Files: 9, Hops: 7, Concepts: 7)
- **Repository:** `deepguard_frontend` (Commit: `86d8dcc06668`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `src/components/Login.tsx`
- `src/components/NewAnalysisContent.tsx`
- `src/components/UploadArea.tsx`
- `src/components/FrameInputModal.tsx`
- `lib/store/analysisStore.ts`
- `src/lib/api.ts`
- `src/app/dashboard/analysis/[id]/page.tsx`
- `src/components/AnalysisHeader.tsx`
- `src/components/ConfidenceOverTimeChart.tsx`

**Supporting Evidence:**
- `src/components/AnalysisPage.tsx`
- `middleware.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `src/components/Sidebar.tsx`
- `src/components/UserProfileCard.tsx`

**Expected Symbols:** `Login, NewAnalysisContent, UploadArea, useAnalysisStore, apiFetch, AnalysisHeader, ConfidenceOverTimeChart`

**Expected Concepts:** `end-to-end user journey, auth cookie acquisition, router.push navigation, Zustand store updates, multipart streaming progress, dynamic route rendering, data visualization assembly`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, cross_file_trace, graph_traversal`

**Expected Answer Points:**
1. Step 1: User submits credentials in Login.tsx; apiFetch calls POST /auth/login setting HttpOnly session cookies; router.push('/dashboard') executes.
1. Step 2: User opens /dashboard/new-analysis; NewAnalysisContent mounts UploadArea in IDLE state.
1. Step 3: User drops video; file size and extension validated; FrameInputModal prompts for frame count (user selects 30).
1. Step 4: Analyze triggered; NewAnalysisContent transitions state to 'UPLOADING'; updates Zustand progress; posts multipart FormData to /analysis.
1. Step 5: Backend responds with created analysis ID; NewAnalysisContent transitions to 'ANALYZING' with loading spinner.
1. Step 6: Frontend polls /analysis/${id} or awaits response; on completion, sets analysis in Zustand store and router.push('/dashboard/analysis/${id}').
1. Step 7: Dynamic [id] page reads analysis from store/API; mounts AnalysisPage, AnalysisHeader (showing risk score and badge), and ConfidenceOverTimeChart (drawing the 30-frame curve).

**Expected Answer Structure:**
- Step 1: Authentication and cookie acquisition
- Step 2: Navigation to new analysis workspace
- Step 3: File drag-and-drop and frame modal selection
- Step 4: Upload dispatch and Zustand progress tracking
- Step 5: Analysis processing state and spinner
- Step 6: Dynamic route redirection
- Step 7: Final report rendering and visual assembly

**Known Traps & Failure Modes:**
- Omitting the FrameInputModal interaction before upload starts
- Missing the role of Zustand analysisStore in passing the result to the [id] dynamic page
- Assuming raw tokens are parsed in client JavaScript during login

---
