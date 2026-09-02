import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Routes handled by app/api/[...path]/route.ts with 300s maxDuration
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
