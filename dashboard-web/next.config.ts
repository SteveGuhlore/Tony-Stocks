import type { NextConfig } from "next"
import path from "path"

// The FastAPI backend (tradingbot-api.service) binds to 127.0.0.1:8001 on the VM.
// It is intentionally NOT exposed on the network — only the Next.js server (:3000) is
// reached remotely (SSH tunnel or Tailscale serve). So we proxy /api/* from the web
// server to the local backend. This makes the frontend talk to the API SAME-ORIGIN,
// which is what lets a phone over Tailscale reach it (the browser hits the .ts.net
// origin, Next.js forwards to localhost:8001). Override with API_PROXY_TARGET if needed.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8001"

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_PROXY_TARGET}/api/:path*` },
    ]
  },
}

export default nextConfig
