"use client";

import React, { useEffect, useState } from "react";
import { useTheme } from "@/components/theme-provider";
import { Sun, Moon, Monitor } from "lucide-react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="flex items-center p-1 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 h-9 w-[108px] animate-pulse" />
    );
  }

  const themes = [
    { name: "light", label: "Light theme", icon: Sun },
    { name: "dark", label: "Dark theme", icon: Moon },
    { name: "system", label: "System default", icon: Monitor },
  ];

  return (
    <div 
      className="flex items-center p-1 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 transition-colors"
      role="group"
      aria-label="Theme selection"
    >
      {themes.map(({ name, label, icon: Icon }) => {
        const isActive = theme === name;
        return (
          <button
            key={name}
            type="button"
            onClick={() => setTheme(name)}
            title={label}
            aria-label={label}
            className={`p-1.5 rounded-md transition-all duration-150 flex items-center justify-center ${
              isActive
                ? "bg-white text-blue-600 shadow-sm dark:bg-slate-700 dark:text-blue-400 font-semibold"
                : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            }`}
          >
            <Icon className="h-4 w-4" />
          </button>
        );
      })}
    </div>
  );
}
