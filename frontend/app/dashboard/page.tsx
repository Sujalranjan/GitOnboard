"use client";

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { repositoryService } from '@/services/repository';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { Plus, FolderGit2 } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

function DashboardContent() {
  const { user, isLoading: authLoading, isAuthenticated } = useAuth();
  const [repos, setRepos] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importUrl, setImportUrl] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState('');
  const [analyzingRepo, setAnalyzingRepo] = useState<string | null>(null);
  const [cancelingRepo, setCancelingRepo] = useState<string | null>(null);
  
  const searchParams = useSearchParams();
  const searchQuery = searchParams.get('search') || '';

  const fetchRepos = async () => {
    try {
      setIsLoading(true);
      console.log('[Dashboard] Fetching repositories...');
      const data = await repositoryService.getAll();
      const repoList = Array.isArray(data) ? data : (data?.repositories || []);
      console.log('[Dashboard] Fetched repos:', repoList);
      repoList.forEach(repo => {
        console.log(`[Dashboard] Repo: ${repo.project_name}, status=${repo.status}, job_status=${repo.job_status}, progress=${repo.progress}`);
      });
      setRepos(repoList);
    } catch (err) {
      console.error('Failed to fetch repositories:', err);
      setRepos([]);
    } finally {
      setIsLoading(false);
    }
  };

  const getRepositoryPath = (repo: any) => {
    if (repo?.url) {
      try {
        const parsed = new URL(repo.url);
        return parsed.pathname.replace(/^\//, '').replace(/\.git$/, '');
      } catch {
        return repo.url;
      }
    }
    return '';
  };

  useEffect(() => {
    console.log('[Dashboard] useEffect triggered: authLoading=', authLoading, 'isAuthenticated=', isAuthenticated, 'repos.length=', repos.length);

    if (!authLoading) {
      if (!isAuthenticated) {
        console.log('[Dashboard] Not authenticated, redirecting to home');
        window.location.href = "/";
      } else {
        console.log('[Dashboard] Authenticated, fetching repos');
        fetchRepos();

        // Subscribe to real-time task updates via SSE for repos with active jobs
        // This ensures we get notified whenever any repo's job status changes
        if (repos.length > 0) {
          console.log('[Dashboard] repos.length > 0, setting up SSE subscriptions');
          const setupSSE = () => {
            const eventSources: EventSource[] = [];

            // Subscribe to each repo that has an active job
            repos.forEach((repo) => {
              const jobStatusLower = (repo.job_status || '').toLowerCase();
              console.log(`[SSE Setup] Checking repo "${repo.project_name}": job_status="${repo.job_status}" (lower="${jobStatusLower}")`);

              if (jobStatusLower && ['queued', 'downloading', 'analyzing', 'saving'].includes(jobStatusLower)) {
                console.log(`[SSE Setup] Subscribing to "${repo.project_name}" (job_status="${repo.job_status}")`);
                try {
                  const eventSource = new EventSource(`/api/repos/${encodeURIComponent(repo.project_name)}/tasks/stream`);
                  console.log(`[SSE] Connected to ${repo.project_name}`);

                  eventSource.onmessage = (event) => {
                    console.log(`[SSE] Message received for ${repo.project_name}:`, event.data);
                    // When tasks update, fetch repos to get latest status
                    fetchRepos();
                  };

                  eventSource.onerror = (err) => {
                    console.error(`[SSE] Error for ${repo.project_name}:`, err);
                    eventSource.close();
                  };

                  eventSources.push(eventSource);
                } catch (err) {
                  console.error(`[SSE] Connection failed for ${repo.project_name}: ${err}`);
                }
              } else {
                console.log(`[SSE Setup] Skipping ${repo.project_name} (job_status not active)`);
              }
            });

            console.log(`[SSE Setup] Created ${eventSources.length} SSE connections`);

            // Return cleanup function to close all SSE connections
            return () => {
              console.log('[SSE Cleanup] Closing SSE connections');
              eventSources.forEach(es => es.close());
            };
          };

          return setupSSE();
        } else {
          console.log('[Dashboard] repos.length is 0, not setting up SSE');
        }
      }
    }
  }, [authLoading, isAuthenticated, repos.length]);

  const repoList = Array.isArray(repos) ? repos : [];
  const filteredRepos = repoList.filter((repo) => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;
    
    const projectName = (repo?.project_name || '').toLowerCase();
    const repoPath = getRepositoryPath(repo).toLowerCase();
    
    return projectName.includes(query) || repoPath.includes(query);
  });

  const handleDelete = async (e: React.MouseEvent, repoName: string) => {
    e.preventDefault();
    if (!window.confirm(`Are you sure you want to delete ${repoName}?`)) return;
    
    try {
      await repositoryService.delete(repoName);
      fetchRepos();
    } catch (err) {
      console.error("Failed to delete repo", err);
      alert("Error deleting repository.");
    }
  };

  const handleReanalyze = async (e: React.MouseEvent, repoName: string) => {
    e.preventDefault();
    setAnalyzingRepo(repoName);
    try {
      await repositoryService.reanalyze(repoName);
      // Let's refetch repos immediately to show the "Queued" status
      fetchRepos();
    } catch (err) {
      console.error("Failed to re-analyze repo", err);
      alert("Error re-analyzing repository.");
    } finally {
      setAnalyzingRepo(null);
    }
  };

  const handleCancel = async (e: React.MouseEvent, repoName: string) => {
    e.preventDefault();
    setCancelingRepo(repoName);
    try {
      await repositoryService.cancel(repoName);
    } catch (err) {
      console.error("Failed to cancel repo analysis", err);
      if ((err as any).message !== "No active analysis to cancel.") {
        alert("Error canceling repository analysis: " + (err as any).message);
      }
    } finally {
      fetchRepos();
      setCancelingRepo(null);
    }
  };

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault();
    setImportError('');
    
    if (!importUrl.startsWith('https://github.com/')) {
      setImportError('Please provide a valid GitHub URL (must start with https://github.com/).');
      return;
    }

    setIsImporting(true);
    try {
      await repositoryService.import(importUrl);
      setIsImportModalOpen(false);
      setImportUrl('');
      fetchRepos();
    } catch (err) {
      setImportError((err as any).message || 'Failed to import repository.');
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div className="w-full h-[calc(100vh-64px)] overflow-y-auto bg-slate-50 dark:bg-slate-950 transition-colors">
      <div className="p-8 w-full max-w-7xl mx-auto flex flex-col">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">Dashboard</h1>
        <Button 
          variant="primary" 
          icon={<Plus className="w-4 h-4" />} 
          onClick={() => setIsImportModalOpen(true)}
        >
          Import Repository
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-500 dark:text-slate-400">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 dark:border-blue-400 mb-4"></div>
          <p>Loading your repositories...</p>
        </div>
      ) : repos.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800 p-12 text-center max-w-2xl mx-auto flex flex-col items-center">
          <div className="w-16 h-16 bg-blue-50 dark:bg-blue-950/60 rounded-full flex items-center justify-center mb-6">
            <FolderGit2 className="w-8 h-8 text-blue-600 dark:text-blue-400" />
          </div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">Welcome to GitOnboard</h2>
          <p className="text-slate-500 dark:text-slate-400 mb-8 max-w-md">No repositories imported yet. Import a public GitHub repository to start analyzing its architecture, metrics, and dependencies.</p>
          <Button 
            variant="primary" 
            size="lg"
            icon={<Plus className="w-5 h-5" />} 
            onClick={() => setIsImportModalOpen(true)}
          >
            Import your first repository
          </Button>
        </div>
      ) : filteredRepos.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800 p-12 text-center max-w-md mx-auto">
          <p className="text-slate-500 dark:text-slate-400">No repositories found matching "{searchQuery}".</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {filteredRepos.map((repo, idx) => (
            <Link key={idx} href={`/repository/${repo.project_name}`}>
              <Card className="h-full hover:shadow-md transition-shadow cursor-pointer group flex flex-col">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="font-bold text-lg text-blue-600 dark:text-blue-400 group-hover:text-blue-700 dark:group-hover:text-blue-300 transition-colors line-clamp-1">{repo.project_name}</h3>
                  <div className="flex gap-2 flex-wrap justify-end">
                    {repo.frameworks?.slice(0, 2).map((fw: string) => (
                      <span key={fw} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
                        {fw}
                      </span>
                    ))}
                    <Badge variant="neutral">{repo.language || "Unknown"}</Badge>
                  </div>
                </div>
                
                <div className="space-y-4 flex-grow">
                  <div>
                    <span className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider block mb-1">Path</span>
                    <p className="text-sm text-slate-600 dark:text-slate-300 font-mono bg-slate-50 dark:bg-slate-800/80 p-2 rounded line-clamp-1">{getRepositoryPath(repo)}</p>
                  </div>
                  
                  {(repo.branch || repo.commit) && (
                    <div>
                      <span className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider block mb-1">Git Info</span>
                      <p className="text-sm text-slate-700 dark:text-slate-300 font-mono bg-slate-50 dark:bg-slate-800/80 p-2 rounded line-clamp-1">
                        {repo.branch ? <span className="text-blue-600 dark:text-blue-400 font-medium">{repo.branch}</span> : ''}
                        {repo.branch && repo.commit ? ' @ ' : ''}
                        {repo.commit ? <span className="text-slate-500 dark:text-slate-400">{repo.commit.substring(0, 7)}</span> : ''}
                      </p>
                    </div>
                  )}
                  
                  {(() => {
                    const statusLower = (repo.status || '').toLowerCase();
                    const jobStatusLower = (repo.job_status || '').toLowerCase();
                    const isActive = ['queued', 'downloading', 'analyzing', 'saving', 'processing'].includes(statusLower) || ['queued', 'downloading', 'analyzing', 'saving'].includes(jobStatusLower);

                    console.log(`[Progress] Repo: ${repo.project_name}, status="${repo.status}", job_status="${repo.job_status}", statusLower="${statusLower}", jobStatusLower="${jobStatusLower}", isActive=${isActive}, progress=${repo.progress}`);

                    if (isActive) {
                      // Use real-time progress from API if available
                      const progress = repo.progress ?? (() => {
                        const statusMap: Record<string, number> = {
                          "queued": 11,      // Changed from 10 to identify which mapping
                          "downloading": 31, // Changed from 30
                          "analyzing": 61,   // Changed from 60
                          "saving": 91,      // Changed from 90
                          "completed": 100,
                          "failed": 0
                        };
                        const currentStatus = (repo.job_status || "Queued").toLowerCase();
                        return statusMap[currentStatus] || 11;
                      })();
                      const currentStatus = repo.job_status || "Queued";

                      console.log(`[Progress] Showing progress bar: ${repo.project_name}, progress=${progress}%, status="${currentStatus}"`);

                      return (
                        <div className="mt-4">
                          <div className="flex justify-between text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                            <span>{currentStatus}...</span>
                            <span>{progress}%</span>
                          </div>
                          <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
                            <div className="bg-blue-500 dark:bg-blue-500 h-2 rounded-full transition-all duration-1000 ease-in-out relative" style={{ width: `${progress}%` }}>
                              <div className="absolute top-0 left-0 right-0 bottom-0 bg-white/20 animate-[shimmer_1s_infinite]"></div>
                            </div>
                          </div>
                        </div>
                      );
                    } else {
                      console.log(`[Progress] NOT showing progress bar: ${repo.project_name} (job_status="${repo.job_status}")`);
                      return (
                        <div>
                          <span className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider block mb-1">Imported At</span>
                          <p className="text-sm text-slate-700 dark:text-slate-300">{new Date(repo.import_time || Date.now()).toLocaleString()}</p>
                        </div>
                      );
                    }
                  })()}
                </div>

                <div className="mt-6 pt-4 border-t border-slate-100 dark:border-slate-800 flex justify-end gap-3">
                  {['Queued', 'Downloading', 'Analyzing', 'Saving', 'Processing'].includes(repo.status) || ['Queued', 'Downloading', 'Analyzing', 'Saving'].includes(repo.job_status) ? (
                    <button 
                      onClick={(e) => handleCancel(e, repo.project_name)}
                      disabled={cancelingRepo === repo.project_name}
                      className="text-amber-600 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 text-sm font-medium flex items-center transition-colors px-2 py-1 rounded hover:bg-amber-50 dark:hover:bg-amber-950/40 disabled:opacity-50"
                    >
                      {cancelingRepo === repo.project_name ? "Canceling..." : "Cancel"}
                    </button>
                  ) : (
                    <button 
                      onClick={(e) => handleReanalyze(e, repo.project_name)}
                      disabled={analyzingRepo === repo.project_name}
                      className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 text-sm font-medium flex items-center transition-colors px-2 py-1 rounded hover:bg-blue-50 dark:hover:bg-blue-950/40 disabled:opacity-50"
                    >
                      {analyzingRepo === repo.project_name ? "Starting..." : "Re-analyze"}
                    </button>
                  )}
                  <button  
                    onClick={(e) => handleDelete(e, repo.project_name)}
                    className="text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 text-sm font-medium flex items-center transition-colors px-2 py-1 rounded hover:bg-red-50 dark:hover:bg-red-950/40"
                  >
                    Delete
                  </button>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <Modal 
        isOpen={isImportModalOpen} 
        onClose={() => setIsImportModalOpen(false)}
        title="Import Repository"
      >
        <form onSubmit={handleImport} className="space-y-4">
          {importError && (
            <div className="p-3 bg-red-50 dark:bg-red-950/60 text-red-700 dark:text-red-300 rounded-lg border border-red-100 dark:border-red-900 text-sm flex items-start gap-2">
              <span className="font-bold mt-0.5">!</span>
              <p>{importError}</p>
            </div>
          )}
          
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Repository URL <span className="text-slate-400 dark:text-slate-500 font-normal">(Python only for MVP)</span>
            </label>
            <input 
              type="text" 
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              placeholder="https://github.com/username/repo" 
              className="w-full border border-slate-300 dark:border-slate-700 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 transition-shadow bg-white dark:bg-slate-800"
              disabled={isImporting}
              autoFocus
            />
          </div>
          
          <div className="pt-4 flex items-center justify-end gap-3">
            <Button 
              variant="ghost" 
              onClick={() => setIsImportModalOpen(false)}
              disabled={isImporting}
            >
              Cancel
            </Button>
            <Button 
              type="submit" 
              variant="primary" 
              disabled={isImporting || !importUrl.trim()}
            >
              {isImporting ? 'Importing...' : 'Import'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
    </div>
  );
}

export default function Dashboard() {
  return (
    <React.Suspense fallback={<div className="p-6 text-slate-500">Loading dashboard...</div>}>
      <DashboardContent />
    </React.Suspense>
  );
}
