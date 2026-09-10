"use client";

import React from 'react';
import Link from 'next/link';

export default function RepositoryList({ repos, onDelete }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {repos.map(repo => (
        <div key={repo.project_name} className="bg-white rounded-lg shadow-md border border-gray-100 flex flex-col justify-between hover:shadow-lg transition-shadow duration-200">
          <Link href={`/repository/${repo.project_name}`} className="p-6 block flex-grow">
            <div className="flex justify-between items-start mb-4">
              <h2 className="text-xl font-bold text-blue-600 truncate" title={repo.project_name}>{repo.project_name}</h2>
              <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded-full font-medium">{repo.language}</span>
            </div>
            
            <div className="space-y-2 mb-4">
              <div>
                <p className="text-xs text-gray-500 font-semibold uppercase">Path</p>
                <p className="text-sm text-gray-700 font-mono truncate" title={repo.repository_path}>{repo.repository_path}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 font-semibold uppercase">Imported At</p>
                <p className="text-sm text-gray-700">{new Date(repo.import_time).toLocaleString()}</p>
              </div>
            </div>
          </Link>
          
          <div className="flex justify-end items-center px-6 py-4 border-t border-gray-100">
            <button 
              onClick={(e) => {
                e.preventDefault();
                onDelete(repo.project_name);
              }}
              className="text-red-500 hover:text-red-700 text-sm font-medium transition-colors"
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
