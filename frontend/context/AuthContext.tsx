"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";

export interface AuthUser {
  id: number;
  username: string;
  github_id?: string;
  email?: string;
  avatar_url?: string;
}

interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  refreshUser: () => Promise<AuthUser | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  refreshUser: async () => null,
  logout: async () => {},
});

let inFlightAuthPromise: Promise<AuthUser | null> | null = null;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
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
          return data;
        }
        return null;
      } catch {
        return null;
      } finally {
        inFlightAuthPromise = null;
      }
    })();

    const data = await inFlightAuthPromise;
    if (isMounted.current) {
      setUser(data);
      setIsLoading(false);
    }
    return data;
  }, []);

  useEffect(() => {
    isMounted.current = true;
    fetchAuthUser();
    return () => {
      isMounted.current = false;
    };
  }, [fetchAuthUser]);

  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
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
