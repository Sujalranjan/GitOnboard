"use client";

import React, { useEffect, useRef, useState } from "react";

interface MermaidProps {
  chart: string;
}

export const MermaidViewer: React.FC<MermaidProps> = ({ chart }) => {
  const [svgContent, setSvgContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const cleanChart = chart.trim();

    if (!cleanChart) return;

    const renderChart = async () => {
      try {
        setError(null);
        // Dynamically import mermaid in browser client only
        const mermaidModule = await import("mermaid");
        const mermaid = mermaidModule.default || mermaidModule;

        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          securityLevel: "loose",
          suppressErrorRendering: true,
          themeVariables: {
            darkMode: true,
            background: "#0D162A",
            primaryColor: "#1E40AF",
            primaryTextColor: "#F8FAFC",
            primaryBorderColor: "#3B82F6",
            lineColor: "#60A5FA",
            secondaryColor: "#1E293B",
            tertiaryColor: "#0F172A",
          },
        });

        // Clean unique ID without special characters
        const safeId = `mermaid_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
        const { svg } = await mermaid.render(safeId, cleanChart);

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
  }, [chart]);

  if (error) {
    return (
      <div className="my-2 rounded-lg border border-slate-700/60 bg-slate-900/90 p-3 font-mono text-xs text-slate-100 overflow-x-auto">
        <div className="text-amber-400 text-[11px] mb-1 font-sans">Mermaid syntax error (fallback display):</div>
        <pre className="whitespace-pre font-mono text-xs text-slate-300">{chart}</pre>
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div className="my-3 flex items-center justify-center p-6 bg-slate-900/40 rounded-xl border border-slate-800 text-xs text-slate-400 font-mono animate-pulse">
        Rendering diagram...
      </div>
    );
  }

  return (
    <div
      className="my-3 overflow-x-auto rounded-xl border border-slate-700/60 bg-[#0D162A]/90 p-4 shadow-md flex justify-center [&_svg]:max-w-full [&_svg]:h-auto"
      dangerouslySetInnerHTML={{ __html: svgContent }}
    />
  );
};
