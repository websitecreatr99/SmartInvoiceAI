import type { NextConfig } from "next";

// FastAPI backend (app.py on the fastapi branch). Override with BACKEND_URL when it runs elsewhere.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/:path*` }];
  },
  experimental: {
    // The legacy /process endpoint blocks until OCR + LLM finish; don't let the dev proxy cut it off.
    proxyTimeout: 10 * 60 * 1000,
  },
};

export default nextConfig;
