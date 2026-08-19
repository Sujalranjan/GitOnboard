# Terminal xterm Rendering and Duplicate Instance Lifecycle Regression

## Symptoms
When using the interactive terminal in the AI Workspace IDE, the following issues were observed:
1. **Prompt & Path Missing / Barely Visible**: The terminal prompt (`root@...:/app/data/worktrees/GitOnboard# `) was absent from the terminal viewport or appeared displaced at the very bottom of the entire web page.
2. **Transient Focus & Inactive Cursor**: Clicking the terminal made the cursor briefly solid white, followed immediately by a transition to a hollow outline box (`[]`).
3. **Ignored Keyboard Input**: Typing produced no characters on screen, and commands could not be submitted.
4. **Visual Disconnect**: The terminal container was visually present, but completely unresponsive to keyboard interaction.

---

## Root Causes

Two related but distinct regressions were identified:

### 1. Rendering Failure (Missing/Unbundled xterm.css)
* **Mechanism**: `@xterm/xterm/css/xterm.css` was not bundled into the client CSS payload when referenced solely via PostCSS `@import` in `globals.css`.
* **Impact**:
  * The canvas layers (`.xterm-text-layer`, `.xterm-cursor-layer`) and the accessibility layer (`.xterm-accessibility`) lost their critical `position: absolute; left: 0; top: 0;` styling.
  * Instead of overlaying at `(0, 0)`, the canvas layers stacked vertically in standard document block flow.
  * The text canvas was pushed below the cursor canvas, and `.xterm-accessibility` rendered unstyled plain text that flowed out of the terminal container to the bottom of the page.

### 2. Focus & Input Failure (Asynchronous Remounting Race Condition)
* **Mechanism**:
  * In React 18/19 and Next.js development (React StrictMode), effects execute a `mount -> cleanup -> mount` cycle.
  * `InteractiveTerminal.tsx` used dynamic imports (`await Promise.all([import('@xterm/xterm'), import('@xterm/addon-fit')])`) inside an async initialization function.
  * When Mount 1 was unmounted, `unmountedRef.current` was set to `true`. However, Mount 2 immediately reset `unmountedRef.current = false`.
  * When Mount 1's dynamic import resolved, it evaluated `unmountedRef.current === false` (reset by Mount 2) and proceeded to instantiate **Terminal Instance #1**, appending its `<div class="xterm">` into the DOM.
  * Mount 2 then resolved and instantiated **Terminal Instance #2**, appending it into the **exact same container element**.
* **Runtime Evidence**:
  ```text
  [TERMINAL MOUNT] runId: GitOnboard
  [TERMINAL DISPOSE] runId: GitOnboard
  [TERMINAL MOUNT] runId: GitOnboard
  [XTERM FOCUS] { activeElement: textarea, textarea: textarea, isMatch: false }
  [FOCUSOUT] { target: textarea.xterm-helper-textarea, relatedTarget: textarea.xterm-helper-textarea }
  ```
* **Why Focus Failed**:
  * Two helper textareas existed simultaneously in the DOM.
  * Clicking the terminal caused both instances to react, resulting in a focusout from Textarea #1 to Textarea #2 and dropping focus to `document.body`.
  * Because the active terminal's helper textarea did not retain focus, browser `keydown` events never reached the textarea, preventing `term.onData` from firing.

---

## Why the Shell / PTY Was NOT the Problem
Direct live verification against the backend WebSocket endpoint (`ws://127.0.0.1:8000/api/v1/sandbox/GitOnboard/terminal`) proved that the backend PTY and shell process were completely healthy:
```text
[PTY_TEST] Connected to WebSocket successfully
[PTY_TEST] Received frame (initial prompt): "root@90449e5a3e4a:/app/data/worktrees/GitOnboard# "
[PTY_TEST] Sending test input: "echo PTY_ALIVE_CHECK\n"
[PTY_TEST] Received frame: "PTY_ALIVE_CHECK"
```
The shell was generating its prompt, transmitting data, and responding to stdin. The bug resided entirely on the client rendering and lifecycle coordination layer.

---

## Permanent Architectural Fix

1. **Effect-Scoped Cancellation Token**:
   * Removed the shared `unmountedRef` in favor of an instance-scoped local variable `let isCancelled = false` within `useEffect`.
   * If an effect is cleaned up before dynamic imports or DOM readiness resolve, `isCancelled` prevents any terminal creation, DOM modification, or WebSocket subscription.
2. **Strict DOM Container Isolation**:
   * Prior to mounting a new xterm instance, the container element is cleared (`while (container.firstChild) container.removeChild(container.firstChild)`), guaranteeing that at most one terminal instance exists in the DOM.
3. **Explicit Resource Ownership & Disposal**:
   * Each effect instance holds local references to its `Terminal`, `FitAddon`, `ResizeObserver`, `dataDisposable`, and `WebSocket`.
   * On unmount, all resources owned by that specific lifecycle instance are disposed and nullified, preventing orphaned listeners or zombie connections.
4. **Direct Dependency CSS Import**:
   * Imported `@xterm/xterm/css/xterm.css` directly as a JavaScript module import inside `InteractiveTerminal.tsx` and `app/layout.tsx` to guarantee CSS bundle inclusion.

---

## Architectural Invariants to Preserve

Future modifications must preserve the following invariants:
* **Invariant 1**: Exactly one live xterm instance per `InteractiveTerminal` component.
* **Invariant 2**: Stale asynchronous initializations must never mount or attach listeners after their effect is disposed.
* **Invariant 3**: Every terminal instance, addon, and WebSocket connection must be cleanly disposed in its effect cleanup.
* **Invariant 4**: xterm stylesheets must be imported via module imports to ensure proper bundler resolution.

---

## Change Reference
* **Date**: 2026-08-19
* **Files Modified**:
  * `frontend/components/workspace/InteractiveTerminal.tsx`
  * `frontend/app/globals.css`
  * `frontend/app/layout.tsx`
