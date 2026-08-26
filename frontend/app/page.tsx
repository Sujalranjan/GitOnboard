"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/common/Button";
import { Modal } from "@/components/common/Modal";
import { LogIn, ArrowRight, ShieldCheck } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export default function LandingPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);

  const handleLogin = () => {
    window.location.href = "/api/auth/github/login";
  };

  const handleForceGitHubLogin = () => {
    window.location.href = "/api/auth/github/login?force_github=true&prompt=consent";
  };

  return (
    <div className="w-full min-h-[calc(100vh-64px)] bg-slate-50 dark:bg-slate-950 flex flex-col items-center justify-center p-8 text-center transition-colors">
      <div className="max-w-2xl mx-auto space-y-8">
        <h1 className="text-5xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
          Repository Intelligence Platform
        </h1>
        <p className="text-xl text-slate-600 dark:text-slate-400">
          Understand, analyze, and visualize your entire codebase architecture with just a few clicks.
        </p>

        <div className="pt-8 flex items-center justify-center gap-4">
          {isAuthenticated ? (
            <Button
              variant="primary"
              size="lg"
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-2"
            >
              Go to Dashboard
              <ArrowRight className="w-5 h-5" />
            </Button>
          ) : (
            <Button
              variant="primary"
              size="lg"
              onClick={handleLogin}
              className="flex items-center gap-2"
            >
              Get Started
              <ArrowRight className="w-5 h-5" />
            </Button>
          )}
        </div>
      </div>

      <Modal
        isOpen={isLoginModalOpen}
        onClose={() => setIsLoginModalOpen(false)}
        title=""
      >
        <div className="p-4 text-center space-y-6">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Welcome</h2>
          <p className="text-gray-500 dark:text-slate-400">Sign in to the Repository Intelligence Platform</p>

          <div className="pt-4 space-y-3">
            <Button
              onClick={handleLogin}
              className="w-full flex items-center justify-center gap-2 py-3"
              variant="primary"
            >
              <ShieldCheck className="w-5 h-5" />
              Sign In (Local / Quick Bypass)
            </Button>

            <Button
              onClick={handleForceGitHubLogin}
              className="w-full flex items-center justify-center gap-2 py-3"
              variant="outline"
            >
              <LogIn className="w-5 h-5" />
              Login with GitHub OAuth
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
