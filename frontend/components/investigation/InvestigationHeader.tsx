'use client';

import React from 'react';
import Link from 'next/link';
import { Globe, Bell, Sun, Moon, Laptop, User, LogOut } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useTheme } from 'next-themes';

interface HeaderProps {
  repoName: string;
}

export const InvestigationHeader: React.FC<HeaderProps> = ({ repoName }) => {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();

  return (
    <div className="h-14 px-4 bg-[#070D1D] border-b border-[#1D2B43] flex items-center justify-between text-slate-300 flex-shrink-0 select-none">
      {/* Left: Repository info pill */}
      <div className="flex items-center gap-3">
        <Link
          href={`/repository/${repoName}`}
          className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-[#0D162A] border border-[#1D2B43] hover:border-[#2165FF]/50 transition-colors text-xs text-slate-200 font-mono"
        >
          <svg className="w-3.5 h-3.5 fill-current text-slate-400" viewBox="0 0 24 24">
            <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
          </svg>
          <span className="font-medium text-white">{repoName || 'repository'}</span>
          <span className="text-[10px] uppercase font-bold text-slate-400 bg-[#111C31] px-1.5 py-0.5 rounded border border-[#1D2B43]">
            Public
          </span>
        </Link>
      </div>

      {/* Right controls: Theme, notification, user */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Theme mode icon switcher */}
        <div className="flex items-center bg-[#0D162A] border border-[#1D2B43] rounded-lg p-0.5 text-slate-400">
          <button
            onClick={() => setTheme('light')}
            className={`p-1 rounded ${theme === 'light' ? 'bg-[#15233E] text-white' : 'hover:text-slate-200'}`}
            title="Light"
          >
            <Sun className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setTheme('dark')}
            className={`p-1 rounded ${theme === 'dark' ? 'bg-[#15233E] text-[#2165FF]' : 'hover:text-slate-200'}`}
            title="Dark"
          >
            <Moon className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setTheme('system')}
            className={`p-1 rounded ${theme === 'system' ? 'bg-[#15233E] text-white' : 'hover:text-slate-200'}`}
            title="System"
          >
            <Laptop className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Notifications */}
        <button className="p-1.5 rounded-lg bg-[#0D162A] border border-[#1D2B43] text-slate-400 hover:text-slate-200 transition-colors">
          <Bell className="w-4 h-4" />
        </button>

        {/* User avatar / profile */}
        <div className="flex items-center gap-2 pl-2 border-l border-[#1D2B43]">
          {user ? (
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-[#15233E] border border-[#1D2B43] overflow-hidden flex items-center justify-center text-xs font-bold text-[#2165FF]">
                {user.avatar_url ? (
                  <img src={user.avatar_url} alt={user.username} className="w-full h-full object-cover" />
                ) : (
                  user.username?.charAt(0).toUpperCase() || 'U'
                )}
              </div>
              <button
                onClick={() => logout()}
                title="Logout"
                className="text-slate-400 hover:text-red-400 transition-colors p-1"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <Link
              href="/api/auth/github/login"
              className="text-xs px-2.5 py-1 rounded bg-[#2165FF] hover:bg-[#1B53D3] text-white font-medium transition-colors"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </div>
  );
};
