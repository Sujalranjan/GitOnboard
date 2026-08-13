"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";

export interface ThemeProviderProps {
  children?: React.ReactNode;
  attribute?: string;
  defaultTheme?: string;
  enableSystem?: boolean;
  disableTransitionOnChange?: boolean;
  storageKey?: string;
  themes?: string[];
  value?: Record<string, string>;
  forcedTheme?: string;
}

export interface UseThemeProps {
  theme?: string;
  setTheme: (theme: string) => void;
  forcedTheme?: string;
  resolvedTheme?: string;
  themes: string[];
  systemTheme?: "dark" | "light";
}

const ThemeContext = createContext<UseThemeProps>({
  theme: "system",
  setTheme: () => {},
  forcedTheme: undefined,
  resolvedTheme: undefined,
  themes: ["light", "dark", "system"],
  systemTheme: undefined,
});

export const useTheme = () => useContext(ThemeContext);

export function ThemeProvider({
  children,
  attribute = "class",
  defaultTheme = "system",
  enableSystem = true,
  disableTransitionOnChange = false,
  storageKey = "theme",
  themes = ["light", "dark", "system"],
  forcedTheme,
}: ThemeProviderProps) {
  const [theme, setThemeState] = useState<string>(() => {
    if (typeof window === "undefined") return defaultTheme;
    try {
      return localStorage.getItem(storageKey) || defaultTheme;
    } catch {
      return defaultTheme;
    }
  });

  const [systemTheme, setSystemTheme] = useState<"dark" | "light" | undefined>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  const getSystemTheme = useCallback((): "dark" | "light" => {
    if (typeof window === "undefined" || !window.matchMedia) return "light";
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }, []);

  const applyThemeToDocument = useCallback(
    (targetTheme: string) => {
      if (typeof window === "undefined") return;

      const d = document.documentElement;
      const sys = getSystemTheme();
      const resolved = targetTheme === "system" && enableSystem ? sys : targetTheme;

      if (attribute === "class") {
        themes.forEach((t) => d.classList.remove(t));
        if (resolved) {
          d.classList.add(resolved);
        }
      } else if (attribute.startsWith("data-")) {
        const attrName = attribute.replace("data-", "");
        if (resolved) {
          d.setAttribute(attrName, resolved);
        }
      }
    },
    [attribute, enableSystem, getSystemTheme, themes]
  );

  const setTheme = useCallback(
    (newTheme: string) => {
      setThemeState(newTheme);
      try {
        localStorage.setItem(storageKey, newTheme);
      } catch {}
      applyThemeToDocument(newTheme);
    },
    [storageKey, applyThemeToDocument]
  );

  useEffect(() => {
    const sys = getSystemTheme();
    setSystemTheme(sys);
    const active = forcedTheme || theme;
    applyThemeToDocument(active);
  }, [theme, forcedTheme, applyThemeToDocument, getSystemTheme]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const listener = (e: MediaQueryListEvent) => {
      const newSys = e.matches ? "dark" : "light";
      setSystemTheme(newSys);
      if (theme === "system") {
        applyThemeToDocument("system");
      }
    };

    if (media.addEventListener) {
      media.addEventListener("change", listener);
      return () => media.removeEventListener("change", listener);
    } else if (media.addListener) {
      media.addListener(listener);
      return () => media.removeListener(listener);
    }
  }, [theme, applyThemeToDocument, getSystemTheme]);

  const activeTheme = forcedTheme || theme;
  const resolvedTheme = activeTheme === "system" ? systemTheme : activeTheme;

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      forcedTheme,
      resolvedTheme,
      themes,
      systemTheme,
    }),
    [theme, setTheme, forcedTheme, resolvedTheme, themes, systemTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
