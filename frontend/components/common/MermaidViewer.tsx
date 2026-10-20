"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";

interface MermaidProps {
  chart: string;
}

// In-memory module cache keyed by `theme:chartContent` to ensure instantaneous renders without blinking
const svgCache = new Map<string, string>();

const MermaidViewerComponent: React.FC<MermaidProps> = ({ chart }) => {
  const { resolvedTheme } = useTheme();
  const cleanChart = chart.trim();
  const isDark = resolvedTheme === "dark";
  const cacheKey = `${isDark ? "dark" : "light"}:${cleanChart}`;

  const [svgContent, setSvgContent] = useState<string>(() => svgCache.get(cacheKey) || "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (!cleanChart) return;

    // If already in cache for this theme, ensure state has it and return immediately
    const cached = svgCache.get(cacheKey);
    if (cached) {
      if (svgContent !== cached) {
        setSvgContent(cached);
      }
      return;
    }

    const renderChart = async () => {
      try {
        setError(null);
        // Dynamically import mermaid in browser client only
        const mermaidModule = await import("mermaid");
        const mermaid = mermaidModule.default || mermaidModule;

        mermaid.initialize({
          startOnLoad: false,
          theme: isDark ? "dark" : "default",
          securityLevel: "loose",
          suppressErrorRendering: true,
          themeVariables: isDark
            ? {
                darkMode: true,
                background: "#090d16",
                primaryColor: "#1e1b4b",
                primaryTextColor: "#f8fafc",
                primaryBorderColor: "#6366f1",
                lineColor: "#818cf8",
                secondaryColor: "#1e293b",
                tertiaryColor: "#0f172a",
              }
            : {
                darkMode: false,
                background: "#ffffff",
                primaryColor: "#eef2ff",
                primaryTextColor: "#0f172a",
                primaryBorderColor: "#818cf8",
                lineColor: "#6366f1",
                secondaryColor: "#f1f5f9",
                tertiaryColor: "#f8fafc",
              },
        });

        // Clean unique ID without special characters
        const safeId = `mermaid_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
        const { svg } = await mermaid.render(safeId, cleanChart);

        svgCache.set(cacheKey, svg);

        if (isMounted) {
          setSvgContent(svg);
        }
      } catch (err: any) {
        console.warn("[Mermaid] Render error:", err);
        if (isMounted) {
          setError(err?.message || "Syntax error in diagram definition");
        }
      }
    };

    renderChart();

    return () => {
      isMounted = false;
    };
  }, [cleanChart, isDark, cacheKey, svgContent]);

  if (error) {
    return (
      <div className="my-2 rounded-xl border border-amber-300 dark:border-amber-800/60 bg-amber-50/70 dark:bg-amber-950/20 p-3 font-mono text-xs text-slate-800 dark:text-slate-200 overflow-x-auto shadow-sm">
        <div className="text-amber-700 dark:text-amber-400 text-[11px] mb-1 font-sans font-semibold">Mermaid syntax error (fallback display):</div>
        <pre className="whitespace-pre font-mono text-xs text-slate-700 dark:text-slate-300">{chart}</pre>
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div className="my-3 flex items-center justify-center p-6 glass-panel-subtle rounded-xl border border-slate-200/60 dark:border-slate-800/60 text-xs text-slate-400 font-mono animate-pulse">
        Rendering diagram...
      </div>
    );
  }

  return (
    <div
      className="my-3 overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-800/80 glass-panel-subtle p-4 shadow-sm flex justify-center [&_svg]:max-w-full [&_svg]:h-auto"
      dangerouslySetInnerHTML={{ __html: svgContent }}
    />
  );
};

export const MermaidViewer = React.memo(MermaidViewerComponent, (prev, next) => prev.chart === next.chart);
MermaidViewer.displayName = "MermaidViewer";
