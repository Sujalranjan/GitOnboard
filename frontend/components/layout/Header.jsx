"use client";

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { Search, Bell, User, LogOut } from 'lucide-react';
import { Button } from '../common/Button';
import { ThemeToggle } from '../ThemeToggle';

export function Header() {
  const pathname = usePathname();
  const [user, setUser] = useState(null);
  const router = useRouter();
  const searchParams = useSearchParams();

  if (pathname === '/workspace') {
    return null;
  }
  const [query, setQuery] = useState(searchParams.get('search') || '');
  const [debounceTimeout, setDebounceTimeout] = useState(null);

  useEffect(() => {
    fetch('/api/auth/github/me')
      .then(res => res.ok ? res.json() : null)
      .then(data => setUser(data))
      .catch(() => setUser(null));
  }, []);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    
    if (debounceTimeout) clearTimeout(debounceTimeout);
    
    const timeout = setTimeout(() => {
      if (val.trim()) {
        router.replace(`/dashboard?search=${encodeURIComponent(val)}`, { scroll: false });
      } else {
        router.replace('/dashboard', { scroll: false });
      }
    }, 300);
    
    setDebounceTimeout(timeout);
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
    <header className="h-16 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between px-4 sm:px-6 z-10 flex-shrink-0 transition-colors">
      <div className="flex items-center">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded flex items-center justify-center">
            <div className="w-4 h-4 bg-white dark:bg-slate-900 transform rotate-45"></div>
          </div>
          <span className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">Git<span className="text-blue-600 dark:text-blue-400">Onboard</span></span>
        </Link>
      </div>
      
      <div className="flex-1 max-w-xl px-8 hidden md:block">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-4 w-4 text-slate-400 dark:text-slate-500" />
          </div>
          <input 
            type="text" 
            value={query}
            onChange={handleSearchChange}
            placeholder="Search repositories, files, symbols..." 
            className="block w-full pl-10 pr-10 py-2 border border-slate-200 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-colors"
          />
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
            <span className="text-xs text-slate-400 dark:text-slate-500 border border-slate-200 dark:border-slate-700 rounded px-1.5 py-0.5 bg-white dark:bg-slate-800 font-mono">⌘ K</span>
          </div>
        </div>
      </div>
      
      <div className="flex items-center gap-2 sm:gap-4">
        <ThemeToggle />
        {user ? (
          <>
            <Button variant="ghost" size="icon" className="relative text-slate-500 dark:text-slate-400 hidden sm:flex">
              <Bell className="h-5 w-5" />
            </Button>
            <div className="h-8 w-8 rounded-full bg-slate-200 dark:bg-slate-700 border border-slate-300 dark:border-slate-600 overflow-hidden flex items-center justify-center">
              {user.avatar ? (
                <img src={user.avatar} alt={user.username} className="h-full w-full object-cover" />
              ) : (
                <User className="h-5 w-5 text-slate-500 dark:text-slate-400" />
              )}
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-slate-500 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 flex items-center gap-1">
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