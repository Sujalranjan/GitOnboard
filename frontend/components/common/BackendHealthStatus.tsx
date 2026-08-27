"use client";

import React, { useState, useEffect, useRef } from "react";
import { Loader2, Server, Database, CheckCircle2, RefreshCw } from "lucide-react";

export function BackendHealthStatus() {
  const [isHealthy, setIsHealthy] = useState<boolean | null>(null);
  const [isDbConnected, setIsDbConnected] = useState<boolean>(false);
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [attempts, setAttempts] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>("Checking backend status...");
  
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const checkHealth = async (): Promise<boolean> => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 4000);
      
      const res = await fetch("/api/health", {
        signal: controller.signal,
        cache: "no-store",
      });
      clearTimeout(timeoutId);

      const data = await res.json().catch(() => null);

      if (res.ok && data && data.status === "healthy" && data.database === "connected") {
        setIsDbConnected(true);
        setIsHealthy(true);
        setIsStarting(false);
        setStatusMessage("Backend and Database are fully connected.");
        return true;
      }

      // Backend or DB is not yet ready during initial cold start
      setIsHealthy(false);
      setIsStarting(true);

      if (data && data.database === "disconnected") {
        setIsDbConnected(false);
        setStatusMessage("API server online. Waiting for database to become ready...");
      } else {
        setIsDbConnected(false);
        setStatusMessage("Backend is starting from cold start. Kindly wait a moment...");
      }
      return false;
    } catch {
      setIsHealthy(false);
      setIsStarting(true);
      setIsDbConnected(false);
      setStatusMessage("Backend is starting from cold start. Kindly wait a moment...");
      return false;
    }
  };

  // Initial check on website open only:
  // Once healthy, polling stops completely. Zero repeated polling when idle.
  useEffect(() => {
    let isMounted = true;

    const runInitialCheck = async () => {
      setAttempts((prev) => prev + 1);
      const ok = await checkHealth();
      if (!isMounted) return;

      if (!ok) {
        // Only retry while cold-starting on initial open
        pollIntervalRef.current = setTimeout(runInitialCheck, 2500);
      } else {
        // Once healthy, go completely silent. No background heartbeat.
        if (pollIntervalRef.current) {
          clearTimeout(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }
    };

    runInitialCheck();

    return () => {
      isMounted = false;
      if (pollIntervalRef.current) {
        clearTimeout(pollIntervalRef.current);
      }
    };
  }, []);

  // When backend is ready, stay completely silent
  if (isHealthy === true || isHealthy === null) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 right-6 z-50 max-w-md w-full animate-in fade-in slide-in-from-bottom-5 duration-300 pointer-events-auto"
    >
      <div className="bg-slate-900/95 dark:bg-slate-900/95 backdrop-blur-md text-white border border-amber-500/40 rounded-xl shadow-2xl p-4 flex items-start space-x-3.5 ring-1 ring-amber-500/20">
        <div className="relative flex-shrink-0 mt-0.5">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
            <Loader2 className="w-4 h-4 animate-spin text-amber-400" />
          </div>
          <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-amber-400 flex items-center gap-1.5">
              {isDbConnected ? (
                <>
                  <Server className="w-3.5 h-3.5" />
                  Backend Initializing
                </>
              ) : (
                <>
                  <Database className="w-3.5 h-3.5" />
                  Cold Start in Progress
                </>
              )}
            </h4>
            <span className="text-[11px] font-mono text-slate-400 px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700">
              check #{attempts}
            </span>
          </div>

          <p className="text-xs text-slate-300 mt-1 leading-relaxed">
            Backend is starting from cold start. Kindly wait, it will connect once ready to serve.
          </p>

          <div className="mt-2.5 flex items-center justify-between">
            <div className="flex items-center space-x-1.5 text-[11px] text-slate-400">
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full ${
                  isDbConnected
                    ? "bg-sky-400 animate-pulse"
                    : "bg-amber-400 animate-pulse"
                }`}
              />
              <span className="truncate">{statusMessage}</span>
            </div>

            <button
              onClick={() => {
                setAttempts((prev) => prev + 1);
                checkHealth();
              }}
              className="text-xs text-amber-400 hover:text-amber-300 flex items-center gap-1 hover:underline transition-colors focus:outline-none flex-shrink-0 ml-2"
            >
              <RefreshCw className="w-3 h-3" />
              Retry now
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
