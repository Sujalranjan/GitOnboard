"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";

export interface AuthUser {
  id: number;
  username: string;
  github_id?: string;
  email?: string;
  avatar_url?: string;
}

export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "backend-unavailable";

interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  authStatus: AuthStatus;
  refreshUser: () => Promise<AuthUser | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  authStatus: "loading",
  refreshUser: async () => null,
  logout: async () => {},
});

let inFlightAuthPromise: Promise<AuthUser | null> | null = null;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthStatus>("loading");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const isMounted = useRef(true);

  const fetchAuthUser = useCallback(async (): Promise<AuthUser | null> => {
    if (inFlightAuthPromise) {
      return inFlightAuthPromise;
    }

    inFlightAuthPromise = (async () => {
      try {
        const res = await fetch("/api/auth/github/me");
        if (res.ok) {
          const data = await res.json();
          if (isMounted.current) {
            setUser(data);
            setAuthStatus("authenticated");
            setIsLoading(false);
          }
          return data;
        }

        // 502/503/504 means backend is down or proxy timed out
        if ([502, 503, 504].includes(res.status)) {
          if (isMounted.current) {
            setUser(null);
            setAuthStatus("backend-unavailable");
            setIsLoading(false);
          }
          return null;
        }

        // 401/403/404 confirmed from live backend that user has no valid session
        if (isMounted.current) {
          setUser(null);
          setAuthStatus("unauthenticated");
          setIsLoading(false);
        }
        return null;
      } catch {
        if (isMounted.current) {
          setUser(null);
          setAuthStatus("backend-unavailable");
          setIsLoading(false);
        }
        return null;
      } finally {
        inFlightAuthPromise = null;
      }
    })();

    return inFlightAuthPromise;
  }, []);

  useEffect(() => {
    isMounted.current = true;
    fetchAuthUser();

    // If backend was unreachable, poll gently every 3s until backend comes up and responds
    let retryTimer: NodeJS.Timeout | null = null;
    if (authStatus === "backend-unavailable") {
      retryTimer = setTimeout(() => {
        if (isMounted.current) {
          fetchAuthUser();
        }
      }, 3000);
    }

    return () => {
      isMounted.current = false;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [fetchAuthUser, authStatus]);

  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/github/logout", { method: "POST" });
    } catch {
      // Ignore network failure during logout
    }
    setUser(null);
    window.location.href = "/";
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        authStatus,
        refreshUser: fetchAuthUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
