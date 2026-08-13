import React from 'react';
import { Sidebar } from '@/components/layout/Sidebar';

export default async function RepositoryLayout(props: any) {
  const params = await props.params;
  const repoName = params.repoName;

  return (
    <div className="flex w-full h-full bg-slate-50 dark:bg-slate-950 transition-colors">
      <Sidebar repoName={repoName} />
      <main className="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 relative transition-colors">
        {props.children}
      </main>
    </div>
  );
}
