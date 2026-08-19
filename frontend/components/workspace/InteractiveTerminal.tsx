"use client";

import React, { useEffect, useRef, useState } from "react";
import type { Terminal } from "@xterm/xterm";
import type { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { getSandboxTerminalWsUrl } from "@/services/sandboxApi";

interface InteractiveTerminalProps {
  runId: string;
}

type ConnectionStatus = "connecting" | "open" | "closed" | "error";

const XTERM_THEME = {
  background: "#0A0D10",
  foreground: "#E6EDF3",
  cursor: "#E6EDF3",
  cursorAccent: "#0A0D10",
  selectionBackground: "#3B4048",
  black: "#0A0D10",
  red: "#F87171",
  green: "#34D399",
  yellow: "#FBBF24",
  blue: "#60A5FA",
  magenta: "#C084FC",
  cyan: "#22D3EE",
  white: "#E6EDF3",
  brightBlack: "#6B7280",
  brightRed: "#FCA5A5",
  brightGreen: "#6EE7B7",
  brightYellow: "#FDE68A",
  brightBlue: "#93C5FD",
  brightMagenta: "#D8B4FE",
  brightCyan: "#67E8F9",
  brightWhite: "#F9FAFB",
};

/**
 * InteractiveTerminal
 *
 * Real PTY-backed terminal emulator powered by xterm.js and a bi-directional WebSocket stream.
 *
 * Ownership & Lifecycle Invariants:
 * 1. Each useEffect invocation creates an instance-scoped cancellation token (`isCancelled`).
 * 2. If the effect unmounts before dynamic imports or DOM readiness resolve, initialization is aborted.
 * 3. The container DOM element is guaranteed to contain at most ONE xterm instance at any time.
 * 4. Cleanup disposes the exact Terminal, Addons, ResizeObservers, Disposables, and WebSocket connection
 *    owned by that specific effect instance, preventing dual-mount races in React StrictMode.
 */
export function InteractiveTerminal({ runId }: InteractiveTerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");

  // Ref to the currently active terminal instance solely for user-initiated click-to-focus
  const activeTermRef = useRef<Terminal | null>(null);

  useEffect(() => {
    let isCancelled = false;
    let terminal: Terminal | null = null;
    let fitAddon: FitAddon | null = null;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let dataDisposable: { dispose: () => void } | null = null;
    let animFrameId: number | null = null;
    let lastSentSize: { rows: number; cols: number } | null = null;

    const container = containerRef.current;
    if (!container) return;

    async function initialize() {
      // Step 1: Load client-side modules dynamically (avoiding SSR "self is not defined")
      const [{ Terminal: XTerminal }, { FitAddon: XFitAddon }] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
      ]);

      // Guard: Check if effect was cleaned up during async import (e.g. React StrictMode unmount)
      if (isCancelled || !container) {
        return;
      }

      // Step 2: Ensure container is pristine before mounting
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }

      // Step 3: Instantiate Terminal and Addons
      const term = new XTerminal({
        cursorBlink: true,
        cursorStyle: "block",
        cursorInactiveStyle: "outline",
        cursorWidth: 2,
        scrollOnUserInput: true,
        smoothScrollDuration: 100,
        fontFamily: "'JetBrains Mono', 'Fira Code', Menlo, Consolas, 'Courier New', monospace",
        fontSize: 13,
        lineHeight: 1.25,
        theme: XTERM_THEME,
        scrollback: 5000,
        convertEol: true,
        allowProposedApi: true,
      });

      const fit = new XFitAddon();
      term.loadAddon(fit);

      // Prevent browser default tab navigation so Tab triggers shell autocompletion
      term.attachCustomKeyEventHandler((event: KeyboardEvent) => {
        if (event.key === "Tab") {
          if (event.type === "keydown") {
            event.preventDefault();
            if (ws && ws.readyState === WebSocket.OPEN) {
              ws.send("\t");
            }
          }
          return false;
        }
        return true;
      });

      term.open(container);

      // Guard: Check if unmounted while open() was executing
      if (isCancelled) {
        term.dispose();
        while (container.firstChild) {
          container.removeChild(container.firstChild);
        }
        return;
      }

      terminal = term;
      fitAddon = fit;
      activeTermRef.current = term;

      const safeFit = () => {
        if (isCancelled || !container || container.clientWidth === 0 || container.clientHeight === 0) {
          return;
        }
        try {
          fit.fit();
          term.scrollToBottom();
        } catch {
          // Ignore fit errors if geometry is transitioning
        }
      };

      // Fit after DOM render and web fonts ready
      animFrameId = requestAnimationFrame(() => {
        if (!isCancelled) {
          safeFit();
          term.focus();
        }
      });

      if (typeof document !== "undefined" && document.fonts) {
        document.fonts.ready.then(() => {
          if (!isCancelled) {
            safeFit();
          }
        });
      }

      const sendResize = (activeWs: WebSocket) => {
        if (isCancelled || !terminal) return;
        const { rows, cols } = terminal;
        if (!rows || !cols || rows <= 0 || cols <= 0) return;
        if (lastSentSize && lastSentSize.rows === rows && lastSentSize.cols === cols) return;
        lastSentSize = { rows, cols };
        if (activeWs.readyState === WebSocket.OPEN) {
          activeWs.send(JSON.stringify({ type: "resize", rows, cols }));
        }
      };

      // Step 4: Establish WebSocket connection
      function connect() {
        if (isCancelled) return;
        setStatus("connecting");
        lastSentSize = null;

        const socket = new WebSocket(getSandboxTerminalWsUrl(runId));
        socket.binaryType = "arraybuffer";
        ws = socket;

        socket.onopen = () => {
          if (isCancelled) {
            socket.close();
            return;
          }
          setStatus("open");
          safeFit();
          sendResize(socket);
          term.focus();
          term.scrollToBottom();
        };

        socket.onmessage = (event) => {
          if (isCancelled || !terminal) return;
          if (typeof event.data === "string") {
            try {
              const control = JSON.parse(event.data);
              if (control.type === "exit") {
                terminal.write("\r\n\x1b[90m[shell exited]\x1b[0m\r\n", () => {
                  terminal?.scrollToBottom();
                });
                return;
              } else if (control.type === "error") {
                terminal.write(`\r\n\x1b[31m[terminal error] ${control.message}\x1b[0m\r\n`, () => {
                  terminal?.scrollToBottom();
                });
                return;
              }
            } catch {
              // Not a control JSON frame, write string directly
            }
            terminal.write(event.data, () => {
              terminal?.scrollToBottom();
            });
            return;
          }
          terminal.write(new Uint8Array(event.data as ArrayBuffer), () => {
            terminal?.scrollToBottom();
          });
        };

        socket.onclose = () => {
          if (isCancelled) return;
          setStatus("closed");
          reconnectTimer = setTimeout(connect, 1500);
        };

        socket.onerror = () => {
          if (isCancelled) return;
          setStatus("error");
        };
      }

      // Step 5: Keystroke handler forwarding to WebSocket
      dataDisposable = term.onData((data) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(data);
        }
        term.scrollToBottom();
      });

      // Step 6: Resize observer to keep xterm grid aligned with container
      resizeObserver = new ResizeObserver(() => {
        if (isCancelled) return;
        safeFit();
        if (ws) sendResize(ws);
      });
      resizeObserver.observe(container);

      connect();
    }

    initialize();

    return () => {
      isCancelled = true;
      if (activeTermRef.current === terminal) {
        activeTermRef.current = null;
      }
      if (animFrameId) cancelAnimationFrame(animFrameId);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (resizeObserver) resizeObserver.disconnect();
      if (dataDisposable) dataDisposable.dispose();
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.close();
        ws = null;
      }
      if (fitAddon) {
        try {
          fitAddon.dispose();
        } catch {
          // ignore
        }
        fitAddon = null;
      }
      if (terminal) {
        try {
          terminal.dispose();
        } catch {
          // ignore
        }
        terminal = null;
      }
      if (container) {
        while (container.firstChild) {
          container.removeChild(container.firstChild);
        }
      }
    };
  }, [runId]);

  return (
    <div
      className="relative flex-1 min-h-0 w-full h-full overflow-hidden cursor-text bg-[#0A0D10] flex flex-col p-2.5 pb-6"
      onClick={() => activeTermRef.current?.focus()}
    >
      <div
        ref={containerRef}
        className="flex-1 min-h-0 w-full overflow-hidden"
        onClick={() => activeTermRef.current?.focus()}
      />
      {status !== "open" && (
        <div className="absolute top-1.5 right-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#14181E] border border-[#2F343A] text-amber-300/90 pointer-events-none z-10">
          {status === "connecting" && "connecting to shell…"}
          {status === "closed" && "disconnected — reconnecting…"}
          {status === "error" && "connection error — retrying…"}
        </div>
      )}
    </div>
  );
}

export default InteractiveTerminal;
