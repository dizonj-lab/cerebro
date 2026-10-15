import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a self-contained server bundle for the container image.
  output: "standalone",

  /*
   * There is deliberately no `rewrites()` entry for /api here.
   *
   * Rewrite destinations are resolved at build time and, under
   * `output: "standalone"`, written literally into the server bundle — so a
   * container image would ignore INTERNAL_API_BASE_URL at runtime. The proxy
   * lives in src/app/api/[...path]/route.ts instead, which reads the
   * environment per request.
   */
};

export default nextConfig;
