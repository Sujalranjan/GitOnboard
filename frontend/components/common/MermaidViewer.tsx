"use client";

import React, { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  securityLevel: "loose",
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

interface MermaidProps {
  chart: string;
}

export const MermaidViewer: React.FC<MermaidProps> = ({ chart }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const cleanChart = chart.trim();

    if (!cleanChart) return;

    const renderChart = async () => {
      try {
        setError(null);
        const id = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
        const { svg } = await mermaid.render(id, cleanChart);
        if (isMounted) {
          setSvgContent(svg);
        }
      } catch (err: any) {
        console.warn("[Mermaid] Render error:", err);
        if (isMounted) {
          setError(err?.message || "Failed to render Mermaid diagram");
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
        <div className="text-amber-400 text-[11px] mb-1 font-sans">Diagram preview (syntax fallback):</div>
        <pre className="whitespace-pre">{chart}</pre>
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div className="my-2 flex items-center justify-center p-6 bg-slate-900/40 rounded-lg border border-slate-800 text-xs text-slate-400 font-mono animate-pulse">
        Rendering diagram...
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-3 overflow-x-auto rounded-xl border border-slate-700/60 bg-[#0D162A]/90 p-4 shadow-md flex justify-center [&_svg]:max-w-full [&_svg]:h-auto"
      dangerouslySetInnerHTML={{ __html: svgContent }}
    />
  );
};
