"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { WorkspaceLayout } from "@/components/workspace/WorkspaceLayout";

function RootWorkspaceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryRepo = searchParams.get("repo");
  const [targetRepo, setTargetRepo] = useState<string | null>(queryRepo);
  const [loading, setLoading] = useState<boolean>(!queryRepo);

  useEffect(() => {
    async function resolveRepo() {
      if (queryRepo) {
        setTargetRepo(queryRepo);
        setLoading(false);
        return;
      }

      try {
        const res = await fetch("/api/repos");
        if (res.ok) {
          const repos = await res.json();
          if (Array.isArray(repos) && repos.length > 0) {
            const firstRepo = repos[0].name || repos[0].url?.split("/").pop() || "default";
            setTargetRepo(firstRepo);
            router.replace(`/repository/${encodeURIComponent(firstRepo)}/workspace`);
            return;
          }
        }
      } catch (err) {
        console.warn("Failed to fetch repositories:", err);
      }

      setTargetRepo("default");
      setLoading(false);
    }

    resolveRepo();
  }, [queryRepo, router]);

  if (loading) {
    return (
      <div className="h-screen w-screen bg-[#0A0D10] text-[#E6EDF3] flex items-center justify-center font-mono text-sm">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          <span>Resolving active repository...</span>
        </div>
      </div>
    );
  }

  return <WorkspaceLayout initialRepoName={targetRepo || "default"} />;
}

export default function RootWorkspacePage() {
  return (
    <Suspense
      fallback={
        <div className="h-screen w-screen bg-[#0A0D10] text-[#E6EDF3] flex items-center justify-center font-mono text-sm">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            <span>Loading workspace...</span>
          </div>
        </div>
      }
    >
      <RootWorkspaceContent />
    </Suspense>
  );
}
