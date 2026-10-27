import type { NextConfig } from "next";

// Flask backend (app.py). Override with BACKEND_URL when it runs elsewhere.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/:path*` }];
  },
  experimental: {
    // OCR + LLM extraction can take minutes; don't let the dev proxy cut it off.
    proxyTimeout: 10 * 60 * 1000,
  },
};

export default nextConfig;
