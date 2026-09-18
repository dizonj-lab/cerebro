import type { NextConfig } from "next";

/**
 * Server-to-server API base. In Kubernetes this is in-cluster Service DNS; in
 * compose it is the service name; locally it is the uvicorn port.
 */
const INTERNAL_API_BASE_URL = process.env.INTERNAL_API_BASE_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Emits a self-contained server bundle for the container image.
  output: "standalone",

  /**
   * Proxy /api to the backend so the browser only ever talks to this origin.
   *
   * This is what makes the session cookie first-party in every environment,
   * removes the need for CORS, and lets the stack run without an ingress
   * controller (a plain port-forward to this service is enough).
   */
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${INTERNAL_API_BASE_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
