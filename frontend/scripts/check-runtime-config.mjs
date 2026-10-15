#!/usr/bin/env node
/**
 * Guards against deployment configuration being frozen into the build.
 *
 * Next.js resolves `rewrites()` destinations when the app is built and, under
 * `output: "standalone"`, writes them literally into the server bundle. A
 * container image built without INTERNAL_API_BASE_URL then ignores whatever the
 * Deployment sets at runtime, and every /api call fails inside the container
 * while working perfectly in development.
 *
 * That shipped once. This check fails the build if it comes back.
 */
import { readFileSync, existsSync } from "node:fs";

const manifestPath = ".next/routes-manifest.json";

if (!existsSync(manifestPath)) {
  console.error(`✗ ${manifestPath} not found — run \`npm run build\` first.`);
  process.exit(1);
}

const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const rewrites = manifest.rewrites ?? {};
const all = [
  ...(rewrites.beforeFiles ?? []),
  ...(rewrites.afterFiles ?? []),
  ...(rewrites.fallback ?? []),
];

// An absolute destination is a host frozen at build time.
const frozen = all.filter((r) => /^https?:\/\//i.test(r.destination ?? ""));

if (frozen.length > 0) {
  console.error("✗ Build-time rewrite destination(s) found in routes-manifest.json:\n");
  for (const r of frozen) {
    console.error(`    ${r.source}  ->  ${r.destination}`);
  }
  console.error(`
  These are resolved at BUILD time and baked into the standalone server, so a
  container image will ignore the runtime environment and proxy to the wrong
  host. Proxy through a route handler that reads process.env per request —
  see src/app/api/[...path]/route.ts.
`);
  process.exit(1);
}

console.log(`✓ No build-time rewrite destinations (${all.length} rewrite(s) checked).`);
