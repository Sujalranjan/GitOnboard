"use client";

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { repositoryService } from '@/services/repository';
import RepositoryOverview from '@/components/repository/RepositoryOverview';
import { useAuth } from '@/context/AuthContext';

export default function RepositoryOverviewPage() {
  const params = useParams();
  const repoName = params.repoName;
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCanceling, setIsCanceling] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (authLoading) return;
    if (!isAuthenticated) {
      router.replace("/");
      return;
    }
    if (!repoName) return;
    
    let pollInterval: NodeJS.Timeout;
    let cancelled = false;

    const fetchScanData = async () => {
      try {
        const json = await repositoryService.scan(repoName as string);
        if (cancelled) return;
        setData(json);
        
        if (json?.status === 'processing') {
          pollInterval = setTimeout(fetchScanData, 3000);
        } else if (json?.status === 'failed') {
          setError(json.message || "Analysis failed.");
          setIsLoading(false);
        } else {
          setIsLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as any).message);
          setIsLoading(false);
        }
      }
    };

    fetchScanData();
    
    return () => {
      cancelled = true;
      if (pollInterval) clearTimeout(pollInterval);
    };
  }, [repoName, authLoading, isAuthenticated, router]);

  if (isLoading && !data) {
    return <div className="p-8 text-center text-slate-500">Loading overview...</div>;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 max-w-xl mx-auto text-center space-y-6">
        <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
          <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-slate-800">Scan Failed</h2>
        <div className="bg-red-50 text-red-700 p-4 rounded-lg border border-red-200 text-sm">
          {error}
        </div>
        <button 
          onClick={() => router.push('/dashboard')}
          className="mt-6 px-4 py-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg text-sm font-medium transition-colors"
        >
          Return to Dashboard
        </button>
      </div>
    );
  }

  if (data && data.status === 'processing') {
    const statusMap: Record<string, number> = {
      "Queued": 10,
      "Downloading": 30,
      "Analyzing": 60,
      "Saving": 90,
      "Completed": 100,
      "Failed": 0
    };
    const currentStatus = data.job_status || "Queued";
    const progress = statusMap[currentStatus] || 10;

    const handleCancel = async () => {
      setIsCanceling(true);
      try {
        await repositoryService.cancel(repoName as string);
        router.push('/dashboard');
      } catch (err) {
        console.error("Failed to cancel repo analysis", err);
        alert("Error canceling repository analysis.");
        setIsCanceling(false);
      }
    };

    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 max-w-2xl mx-auto text-center space-y-6">
        <div className="w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center animate-pulse">
          <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path>
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-slate-800">Processing Repository</h2>
        <p className="text-slate-500">We are currently extracting metrics, generating graphs, and running AI analysis for <span className="font-semibold text-slate-700">{repoName}</span>. This may take a few minutes for larger codebases.</p>
        
        <div className="w-full bg-slate-100 rounded-full h-4 mt-8 overflow-hidden">
          <div className="bg-blue-600 h-4 rounded-full transition-all duration-1000 ease-in-out relative" style={{ width: `${progress}%` }}>
            <div className="absolute top-0 left-0 right-0 bottom-0 bg-white/20 animate-[shimmer_1s_infinite]"></div>
          </div>
        </div>
        <div className="flex justify-between w-full text-sm font-medium text-slate-600 mt-2">
          <span>{currentStatus}...</span>
          <span>{progress}%</span>
        </div>

        <button 
          onClick={handleCancel}
          disabled={isCanceling}
          className="mt-6 px-4 py-2 bg-white border border-amber-200 text-amber-700 hover:bg-amber-50 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          {isCanceling ? "Canceling..." : "Cancel Analysis"}
        </button>
      </div>
    );
  }

  return <RepositoryOverview repoName={repoName as string} data={data} />;
}
