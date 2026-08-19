"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { WorkspaceLayout } from "@/components/workspace/WorkspaceLayout";

export default function RepoWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const rawRepoName = (params?.repoName as string) || "";
  const repoName = decodeURIComponent(rawRepoName);
  const [validatedRepo, setValidatedRepo] = useState<string | null>(repoName || null);
  const [loading, setLoading] = useState<boolean>(!repoName);

  useEffect(() => {
    async function validateOrFetchRepo() {
      if (repoName) {
        setValidatedRepo(repoName);
        setLoading(false);
        return;
      }

      try {
        const res = await fetch("/api/repos");
        if (res.ok) {
          const data = await res.json();
          const repoList = Array.isArray(data) ? data : (data?.repositories || []);
          if (repoList.length > 0) {
            const first = repoList[0];
            const firstRepo = first.project_name || first.name || (first.url ? first.url.split("/").pop().replace(".git", "") : "default");
            setValidatedRepo(firstRepo);
            setLoading(false);
            return;
          }
        }
      } catch (err) {
        console.warn("Failed to fetch available repos:", err);
      }
      setValidatedRepo("default");
      setLoading(false);
    }

    validateOrFetchRepo();
  }, [repoName, router]);

  if (loading) {
    return (
      <div className="h-screen w-screen bg-[#0A0D10] text-[#E6EDF3] flex items-center justify-center font-mono text-sm">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          <span>Resolving repository context...</span>
        </div>
      </div>
    );
  }

  return <WorkspaceLayout initialRepoName={validatedRepo || "default"} />;
}
