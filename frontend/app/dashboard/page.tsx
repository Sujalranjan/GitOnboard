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

export default function Dashboard() {
  const [repos, setRepos] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importUrl, setImportUrl] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState('');
  
  const searchParams = useSearchParams();
  const searchQuery = searchParams.get('search') || '';

  const fetchRepos = async () => {
    try {
      const data = await repositoryService.getAll();
      setRepos(data.repositories || []);
    } catch (err) {
      console.error("Failed to fetch repos", err);
    } finally {
      setIsLoading(false);
    }
  };

  const getRepositoryPath = (repo: any) => {
    if (repo.repository_path) return repo.repository_path;
    if (repo.url) {
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
    fetchRepos();
  }, []);

  const filteredRepos = repos.filter((repo) => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;
    
    const projectName = (repo.project_name || '').toLowerCase();
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
    try {
      await repositoryService.reanalyze(repoName);
      alert(`Re-analysis for ${repoName} started! You can click the repo to see progress.`);
    } catch (err) {
      console.error("Failed to re-analyze repo", err);
      alert("Error re-analyzing repository.");
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
    <div className="p-8 w-full max-w-7xl mx-auto flex flex-col h-[calc(100vh-64px)] overflow-y-auto">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Dashboard</h1>
        <Button 
          variant="primary" 
          icon={<Plus className="w-4 h-4" />} 
          onClick={() => setIsImportModalOpen(true)}
        >
          Import Repository
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-500">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-4"></div>
          <p>Loading your repositories...</p>
        </div>
      ) : repos.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center max-w-2xl mx-auto flex flex-col items-center">
          <div className="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mb-6">
            <FolderGit2 className="w-8 h-8 text-blue-600" />
          </div>
          <h2 className="text-xl font-bold text-slate-900 mb-2">Welcome to GitOnboard</h2>
          <p className="text-slate-500 mb-8 max-w-md">No repositories imported yet. Import a public GitHub repository to start analyzing its architecture, metrics, and dependencies.</p>
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
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center max-w-md mx-auto">
          <p className="text-slate-500">No repositories found matching "{searchQuery}".</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {filteredRepos.map((repo, idx) => (
            <Link key={idx} href={`/repository/${repo.project_name}`}>
              <Card className="h-full hover:shadow-md transition-shadow cursor-pointer group flex flex-col">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="font-bold text-lg text-blue-600 group-hover:text-blue-700 transition-colors line-clamp-1">{repo.project_name}</h3>
                  <Badge variant="neutral">{repo.language || "Unknown"}</Badge>
                </div>
                
                <div className="space-y-4 flex-grow">
                  <div>
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">Path</span>
                    <p className="text-sm text-slate-600 font-mono bg-slate-50 p-2 rounded line-clamp-1">{getRepositoryPath(repo)}</p>
                  </div>
                  
                  <div>
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">Imported At</span>
                    <p className="text-sm text-slate-700">{new Date(repo.import_time || Date.now()).toLocaleString()}</p>
                  </div>
                </div>

                <div className="mt-6 pt-4 border-t border-slate-100 flex justify-end gap-3">
                  <button 
                    onClick={(e) => handleReanalyze(e, repo.project_name)}
                    className="text-blue-600 hover:text-blue-800 text-sm font-medium flex items-center transition-colors px-2 py-1 rounded hover:bg-blue-50"
                  >
                    Re-analyze
                  </button>
                  <button 
                    onClick={(e) => handleDelete(e, repo.project_name)}
                    className="text-red-500 hover:text-red-700 text-sm font-medium flex items-center transition-colors px-2 py-1 rounded hover:bg-red-50"
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
            <div className="p-3 bg-red-50 text-red-700 rounded-lg border border-red-100 text-sm flex items-start gap-2">
              <span className="font-bold mt-0.5">!</span>
              <p>{importError}</p>
            </div>
          )}
          
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Repository URL <span className="text-slate-400 font-normal">(Python only for MVP)</span>
            </label>
            <input 
              type="text" 
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              placeholder="https://github.com/username/repo" 
              className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-slate-900 transition-shadow bg-white"
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
  );
}