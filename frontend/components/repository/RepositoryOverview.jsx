"use client";

import React, { useState, useEffect } from 'react';
import { Card, CardHeader } from '../common/Card';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import Link from 'next/link';
import { PythonIcon, JavascriptIcon, TypescriptIcon, ReactIcon, JavaIcon } from '../common/LanguageIcons';
import { 
  Star, 
  GitBranch, 
  ShieldCheck, 
  FileText, 
  Code, 
  Box, 
  RefreshCw, 
  Download,
  AlertTriangle,
  Info,
  ChevronRight,
  Sparkles,
  Share2,
  Search,
  Clock,
  GitCommit
} from 'lucide-react';

const getLanguageConfig = (lang) => {
  const primaryLang = lang ? lang.split(',')[0].trim() : '';
  switch (primaryLang) {
    case 'Python': return { bg: 'bg-blue-500', Icon: PythonIcon };
    case 'JavaScript': return { bg: 'bg-yellow-500', Icon: JavascriptIcon };
    case 'TypeScript': return { bg: 'bg-blue-600', Icon: TypescriptIcon };
    case 'React': return { bg: 'bg-cyan-500', Icon: ReactIcon };
    case 'Java': return { bg: 'bg-red-500', Icon: JavaIcon };
    default: return { bg: 'bg-gray-500', Icon: null };
  }
};

export default function RepositoryOverview({ repoName, data: scanData }) {
  const [healthData, setHealthData] = useState(null);
  const [statsData, setStatsData] = useState(null);
  const [findingsData, setFindingsData] = useState(null);
  const [featureData, setFeatureData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchRealData = async () => {
      setIsLoading(true);
      try {
        const [healthRes, statsRes, findingsRes, featuresRes] = await Promise.all([
          fetch(`/api/repos/${repoName}/health/scores`),
          fetch(`/api/repos/${repoName}/stats`),
          fetch(`/api/repos/${repoName}/health/findings`),
          fetch(`/api/repos/${repoName}/features`)
        ]);

        if (healthRes.ok) setHealthData(await healthRes.json());
        if (statsRes.ok) setStatsData(await statsRes.json());
        if (findingsRes.ok) setFindingsData(await findingsRes.json());
        if (featuresRes.ok) setFeatureData(await featuresRes.json());
      } catch (err) {
        console.error("Failed to load overview data", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchRealData();
  }, [repoName]);

  const overview = scanData?.overview || {};
  const healthScore = healthData?.health_score || 0;
  const status = healthData?.status || "Analyzing";
  
  const filesCount = overview.total_files || statsData?.total_files || 0;
  const funcsCount = overview.total_functions || statsData?.total_functions || 0;
  const classesCount = overview.total_classes || statsData?.total_classes || 0;
  
  const loc = statsData?.lines_of_code || 0;
  const complexity = statsData?.average_functions_per_module ? statsData.average_functions_per_module.toFixed(1) : "0";
  const testCov = statsData?.custom_metrics?.test_coverage_approx_percent || "0%";
  const commentRatio = statsData?.custom_metrics?.documentation_coverage_percent ? `${statsData.custom_metrics.documentation_coverage_percent.toFixed(1)}%` : "0%";
  
  const findings = findingsData?.findings || [];
  const topFindings = findings.slice(0, 3);
  const discoveredFeatures = featureData?.features || [];

  const getStatusColor = (statusText) => {
    switch (statusText) {
      case 'Excellent': return 'text-green-600';
      case 'Good': return 'text-blue-600';
      case 'Fair': return 'text-amber-600';
      case 'Needs Work': return 'text-red-600';
      default: return 'text-slate-600';
    }
  };

  const getSeverityIcon = (severity) => {
    if (severity === "CRITICAL" || severity === "ERROR") return <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />;
    if (severity === "WARNING") return <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />;
    return <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />;
  };

  const handleReanalyze = async () => {
    try {
      await fetch(`/api/repos/${repoName}/reanalyze`, { method: 'POST' });
      // The parent page will pick up the processing status on reload
      window.location.reload();
    } catch (err) {
      alert("Error re-analyzing repository.");
    }
  };

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-6">
      
      {/* Top Header Stats */}
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-slate-900 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm">
            <span className="text-white font-bold text-xl">{repoName.charAt(0).toUpperCase()}</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-3xl font-bold text-slate-900 tracking-tight">{repoName}</h1>
              <Star className="w-5 h-5 text-slate-400 hover:text-amber-400 cursor-pointer transition-colors" />
            </div>
            <div className="flex items-center gap-3 mt-2">
              {overview.language && (() => {
                const config = getLanguageConfig(overview.language);
                return (
                  <Badge variant="neutral" icon={
                    config.Icon ? <config.Icon className="w-3 h-3 mr-1" /> : <div className={`w-3 h-3 rounded-full ${config.bg} mr-1`} />
                  }>
                    {overview.language}
                  </Badge>
                );
              })()}
              {overview.branch && (
                <Badge variant="neutral" icon={<GitBranch className="w-3 h-3 mr-1" />}>
                  {overview.branch}
                </Badge>
              )}
              {overview.commit && (
                <Badge variant="neutral" icon={<GitCommit className="w-3 h-3 mr-1" />}>
                  {overview.commit.substring(0, 7)}
                </Badge>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-4 bg-white border border-slate-200 rounded-xl p-2 shadow-sm">
            <div className="px-4 py-1 flex flex-col items-center border-r border-slate-100">
              <div className={`flex items-center mb-1 ${getStatusColor(status)}`}>
                <ShieldCheck className="w-4 h-4 mr-1" />
                <span className="text-xs font-semibold uppercase tracking-wider">Health Score</span>
              </div>
              <span className="text-2xl font-bold text-slate-900 leading-none">{healthScore}</span>
            </div>
            <div className="px-4 py-1 flex flex-col items-center border-r border-slate-100">
              <div className="flex items-center text-blue-600 mb-1">
                <FileText className="w-4 h-4 mr-1" />
                <span className="text-lg font-bold text-slate-900 leading-none">{filesCount}</span>
              </div>
              <span className="text-xs text-slate-500">Files</span>
            </div>
            <div className="px-4 py-1 flex flex-col items-center border-r border-slate-100">
              <div className="flex items-center text-blue-600 mb-1">
                <Code className="w-4 h-4 mr-1" />
                <span className="text-lg font-bold text-slate-900 leading-none">{funcsCount}</span>
              </div>
              <span className="text-xs text-slate-500">Functions</span>
            </div>
            <div className="px-4 py-1 flex flex-col items-center">
              <div className="flex items-center text-blue-600 mb-1">
                <Box className="w-4 h-4 mr-1" />
                <span className="text-lg font-bold text-slate-900 leading-none">{classesCount}</span>
              </div>
              <span className="text-xs text-slate-500">Classes</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => window.location.reload()} icon={<RefreshCw className="w-4 h-4" />}>Refresh</Button>
            <Button variant="primary" onClick={handleReanalyze} icon={<RefreshCw className="w-4 h-4" />}>Re-analyze</Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Overview Card */}
        <Card className="lg:col-span-1 flex flex-col" noPadding>
          <CardHeader title="Repository Overview" />
          <div className="p-6 flex-1 flex flex-col justify-between">
            <div>
              <p className="text-sm text-slate-600 leading-relaxed mb-6">
                {repoName} has {filesCount} files analyzed successfully.
              </p>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 flex items-center"><Code className="w-4 h-4 mr-2" /> Language</span>
                  <div className="flex items-center gap-1.5 font-medium text-slate-900">
                    {(() => {
                      const config = getLanguageConfig(overview.language || 'Python');
                      return config.Icon ? <config.Icon className="w-4 h-4" /> : <div className={`w-2 h-2 rounded-full ${config.bg}`} />;
                    })()}
                    <span>{overview.language || "Unknown"}</span>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 flex items-center"><GitBranch className="w-4 h-4 mr-2" /> Default Branch</span>
                  <span className="font-medium text-slate-900">{overview.branch || "unknown"}</span>
                </div>
                {overview.commit && (
                  <div className="flex justify-between items-center">
                    <span className="text-slate-500 flex items-center"><GitCommit className="w-4 h-4 mr-2" /> Latest Commit</span>
                    <span className="font-medium text-slate-900 font-mono text-xs bg-slate-100 px-2 py-1 rounded">{overview.commit.substring(0, 7)}</span>
                  </div>
                )}
                {overview.commit_timestamp && (
                  <div className="flex justify-between items-center">
                    <span className="text-slate-500 flex items-center"><Clock className="w-4 h-4 mr-2" /> Last Updated</span>
                    <span className="font-medium text-slate-900">
                      {new Date(overview.commit_timestamp).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Health Score Ring */}
        <Card className="lg:col-span-1 flex flex-col items-center justify-center text-center">
          <h3 className="font-semibold text-slate-800 w-full text-left mb-6">Health Score</h3>
          <div className="relative w-40 h-40 flex items-center justify-center">
            <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
              <path
                className="text-slate-100"
                strokeWidth="3"
                stroke="currentColor"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path
                className="text-blue-600"
                strokeWidth="3"
                strokeDasharray={`${healthScore}, 100`}
                strokeLinecap="round"
                stroke="currentColor"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <div className="absolute flex flex-col items-center justify-center">
              <span className="text-4xl font-bold text-slate-900">{healthScore}</span>
              <span className="text-sm text-slate-500">/100</span>
              <span className={`text-xs font-medium mt-1 ${getStatusColor(status)}`}>{status}</span>
            </div>
          </div>
        </Card>

        {/* Key Metrics Grid */}
        <Card className="lg:col-span-1 flex flex-col bg-transparent shadow-none border-none" noPadding>
          <h3 className="font-semibold text-slate-800 mb-4 px-1">Key Metrics</h3>
          <div className="grid grid-cols-2 gap-4 flex-1">
            <Card className="flex flex-col justify-center p-4 shadow-sm border border-slate-200">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Lines of Code</span>
              <span className="text-2xl font-bold text-slate-900">{loc}</span>
            </Card>
            <Card className="flex flex-col justify-center p-4 shadow-sm border border-slate-200">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Comment Ratio</span>
              <span className="text-2xl font-bold text-slate-900">{commentRatio}</span>
            </Card>
            <Card className="flex flex-col justify-center p-4 shadow-sm border border-slate-200">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Complexity</span>
              <span className="text-2xl font-bold text-slate-900">{complexity}</span>
            </Card>
            <Card className="flex flex-col justify-center p-4 shadow-sm border border-slate-200">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Test Coverage</span>
              <span className="text-2xl font-bold text-slate-900">{testCov}</span>
            </Card>
          </div>
        </Card>

      </div>
      
      {/* Bottom Section (AI Summary, Findings, Actions) */}
      {/* Bottom Section (Insights & Composition) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Repository Composition */}
        <Card className="lg:col-span-1 flex flex-col">
          <div className="flex justify-between items-center mb-6">
            <h3 className="font-semibold text-slate-800 flex items-center"><Box className="w-4 h-4 mr-2 text-blue-500" /> Composition</h3>
          </div>
          <div className="flex-1 flex flex-col justify-between space-y-6">
            <div>
              <p className="text-sm text-slate-600 mb-4">Breakdown of repository elements:</p>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-600 font-medium">Functions</span>
                    <span className="text-slate-900 font-bold">{funcsCount}</span>
                  </div>
                  <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(100, (funcsCount / Math.max(1, funcsCount + classesCount)) * 100)}%` }} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-600 font-medium">Classes</span>
                    <span className="text-slate-900 font-bold">{classesCount}</span>
                  </div>
                  <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.min(100, (classesCount / Math.max(1, funcsCount + classesCount)) * 100)}%` }} />
                  </div>
                </div>
              </div>
            </div>
            
            <div className="bg-slate-50 p-4 rounded-lg border border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                  <Sparkles className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">AI Understanding</p>
                  <p className="text-xs text-slate-500">
                    {discoveredFeatures.length > 0 
                      ? `${discoveredFeatures.length} features mapped (${Math.round(discoveredFeatures.reduce((acc, f) => acc + (f.confidence || 0), 0) / discoveredFeatures.length * 100)}% confidence)`
                      : "No features mapped yet."}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </Card>
        
        {/* Detailed Health Breakdown */}
        <Card className="lg:col-span-1 flex flex-col">
          <div className="flex justify-between items-center mb-6">
            <h3 className="font-semibold text-slate-800 flex items-center"><ShieldCheck className="w-4 h-4 mr-2 text-green-500" /> Health Breakdown</h3>
            <Link href={`/repository/${repoName}/health`} className="text-xs text-blue-600 hover:underline cursor-pointer">Details &rarr;</Link>
          </div>
          
          <div className="space-y-5 flex-1">
            {[
              { label: 'Maintainability', score: healthData?.categories?.maintainability?.score || 0, color: 'bg-emerald-500' },
              { label: 'Reliability', score: healthData?.categories?.reliability?.score || 0, color: 'bg-blue-500' },
              { label: 'Security', score: healthData?.categories?.security?.score || 0, color: 'bg-violet-500' }
            ].map((cat, idx) => (
              <div key={idx}>
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="text-slate-700 font-medium">{cat.label}</span>
                  <span className="text-slate-900 font-bold">{Math.round(cat.score)}/100</span>
                </div>
                <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${cat.color}`} style={{ width: `${Math.max(5, cat.score)}%` }} />
                </div>
              </div>
            ))}
            
            <div className="mt-4 pt-4 border-t border-slate-100">
              <p className="text-sm text-slate-600">
                Your overall score of <span className="font-bold text-slate-900">{healthScore}</span> is weighted heavily towards maintainability and security. 
              </p>
            </div>
          </div>
        </Card>

        {/* Action Center */}
        <Card className="lg:col-span-1 flex flex-col">
          <div className="flex justify-between items-center mb-6">
            <h3 className="font-semibold text-slate-800 flex items-center"><AlertTriangle className="w-4 h-4 mr-2 text-amber-500" /> Action Center</h3>
          </div>
          
          <div className="space-y-3 flex-1 flex flex-col">
            {isLoading ? (
              <p className="text-sm text-slate-500">Evaluating actions...</p>
            ) : (
              <>
                {(() => {
                  const critical = findings.filter(f => f.severity === 'CRITICAL' || f.severity === 'ERROR').length;
                  const warning = findings.filter(f => f.severity === 'WARNING').length;
                  
                  if (critical === 0 && warning === 0) {
                    return (
                      <div className="flex flex-col items-center justify-center py-6 text-center h-full">
                        <div className="w-12 h-12 rounded-full bg-green-50 flex items-center justify-center mb-3">
                          <ShieldCheck className="w-6 h-6 text-green-500" />
                        </div>
                        <p className="text-sm font-medium text-slate-900">All clear!</p>
                        <p className="text-xs text-slate-500 mt-1">No major issues require your attention right now.</p>
                      </div>
                    );
                  }
                  
                  return (
                    <>
                      {critical > 0 && (
                        <div className="p-3 bg-red-50 border border-red-100 rounded-lg flex items-start gap-3">
                          <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-sm font-bold text-red-900">{critical} Critical Issues</p>
                            <p className="text-xs text-red-700 mt-0.5">These vulnerabilities or bugs need immediate fixing.</p>
                          </div>
                        </div>
                      )}
                      
                      {warning > 0 && (
                        <div className="p-3 bg-amber-50 border border-amber-100 rounded-lg flex items-start gap-3">
                          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-sm font-bold text-amber-900">{warning} Warnings</p>
                            <p className="text-xs text-amber-700 mt-0.5">Code smells or structural issues to review.</p>
                          </div>
                        </div>
                      )}
                    </>
                  );
                })()}
                
                <div className="mt-auto pt-4">
                  <Link href={`/repository/${repoName}/health`} className="w-full inline-flex justify-center items-center px-4 py-2 bg-white border border-slate-200 text-sm font-medium rounded-lg text-slate-700 hover:bg-slate-50 transition-colors">
                    Review all findings
                  </Link>
                </div>
              </>
            )}
          </div>
        </Card>

      </div>
    </div>
  );
}
