"use client";

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Search, Bell, User, LogOut } from 'lucide-react';
import { Button } from '../common/Button';

export function Header() {
  const [user, setUser] = useState(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get('search') || '');

  useEffect(() => {
    fetch('/api/auth/github/me')
      .then(res => res.ok ? res.json() : null)
      .then(data => setUser(data))
      .catch(() => setUser(null));
  }, []);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    if (val.trim()) {
      router.push(`/dashboard?search=${encodeURIComponent(val)}`);
    } else {
      router.push('/dashboard');
    }
  };

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/github/logout', {
        method: 'POST',
        credentials: 'include',
      });
      localStorage.clear();
      sessionStorage.clear();
      window.location.href = '/';
    } catch (err) {
      console.error('Logout failed:', err);
    }
  };

  return (
    <header className="h-16 border-b border-slate-200 bg-white flex items-center justify-between px-4 sm:px-6 z-10 flex-shrink-0">
      <div className="flex items-center">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded flex items-center justify-center">
            <div className="w-4 h-4 bg-white transform rotate-45"></div>
          </div>
          <span className="text-xl font-bold text-slate-900 tracking-tight">Git<span className="text-blue-600">Onboard</span></span>
        </Link>
      </div>
      
      <div className="flex-1 max-w-xl px-8 hidden md:block">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-4 w-4 text-slate-400" />
          </div>
          <input 
            type="text" 
            value={query}
            onChange={handleSearchChange}
            placeholder="Search repositories, files, symbols..." 
            className="block w-full pl-10 pr-10 py-2 border border-slate-200 rounded-lg bg-slate-50 text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-colors"
          />
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
            <span className="text-xs text-slate-400 border border-slate-200 rounded px-1.5 py-0.5 bg-white font-mono">⌘ K</span>
          </div>
        </div>
      </div>
      
      <div className="flex items-center gap-2 sm:gap-4">
        {user ? (
          <>
            <Button variant="ghost" size="icon" className="relative text-slate-500 hidden sm:flex">
              <Bell className="h-5 w-5" />
            </Button>
            <div className="h-8 w-8 rounded-full bg-slate-200 border border-slate-300 overflow-hidden flex items-center justify-center">
              {user.avatar ? (
                <img src={user.avatar} alt={user.username} className="h-full w-full object-cover" />
              ) : (
                <User className="h-5 w-5 text-slate-500" />
              )}
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-slate-500 hover:text-red-600 flex items-center gap-1">
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </Button>
          </>
        ) : (
          <Button variant="primary" size="sm" onClick={() => window.location.href = "/api/auth/github/login"}>
            Log In
          </Button>
        )}
      </div>
    </header>
  );
}