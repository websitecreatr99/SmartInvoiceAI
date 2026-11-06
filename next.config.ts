import type { NextConfig } from "next";

// FastAPI backend (app.py on the fastapi branch). Override with BACKEND_URL when it runs elsewhere.
// Read at build time: rewrites are compiled into the build, so set it when building the image.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  // Self-contained server in .next/standalone for the Docker image (ignored by Vercel).
  output: "standalone",
  async rewrites() {
    // Only the endpoints the UI uses; /metrics, /docs and the legacy upload routes stay private.
    return [
      { source: "/api/jobs", destination: `${BACKEND_URL}/jobs` },
      { source: "/api/jobs/:path*", destination: `${BACKEND_URL}/jobs/:path*` },
      { source: "/api/health", destination: `${BACKEND_URL}/health` },
    ];
  },
  experimental: {
    // Uploads of large documents can be slow; don't let the proxy cut them off.
    proxyTimeout: 10 * 60 * 1000,
  },
};

export default nextConfig;
