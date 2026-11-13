import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy /api/* to FastAPI so the browser talks to a single origin (no CORS, works behind previews/tunnels).
  async rewrites() {
    const target = process.env.API_PROXY_TARGET || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${target}/api/:path*` }];
  },
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
