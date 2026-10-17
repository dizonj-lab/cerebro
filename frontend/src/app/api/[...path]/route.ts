import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Runtime proxy from /api/* to the backend.
 *
 * This deliberately replaces a `rewrites()` entry in next.config.ts. A rewrite
 * destination is resolved when the app is BUILT and, with `output: "standalone"`,
 * is written literally into `.next/standalone/server.js`. A container image
 * built without INTERNAL_API_BASE_URL therefore bakes in the localhost fallback
 * and ignores whatever the Deployment sets at runtime — the proxy then points at
 * port 8000 inside the web container, where nothing is listening.
 *
 * A route handler reads the environment on every request, so the same image runs
 * unchanged in development, compose and Kubernetes.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function apiBaseUrl(): string {
  return (process.env.INTERNAL_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

/** Headers that describe a single hop and must not be forwarded. */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  // fetch decompresses the body, so the upstream's encoding and length no
  // longer describe what we are about to send.
  "content-encoding",
  "content-length",
  "host",
  // Expect: 100-continue is a hop's own negotiation with its immediate peer,
  // and undici refuses outright to send a request carrying one — the whole
  // upload fails with "fetch failed" before it leaves this process. curl adds
  // it to any body over 1KB, so forwarding it broke every large upload from a
  // command line or script while browsers, which never send it, were fine.
  "expect",
]);

/**
 * How long to wait for the API before giving up.
 *
 * Set explicitly rather than left to the runtime's default, because the
 * slowest thing behind this proxy is a local model proposing metadata, and
 * its own budget is the number this has to clear. Enrichment spends at most
 * ~210s (a 150s budget plus one 60s call already in flight), so this leaves
 * room without letting a genuinely stuck request hang a tab forever.
 */
const UPSTREAM_TIMEOUT_MS = 300_000;

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const search = request.nextUrl.search;
  const target = `${apiBaseUrl()}/api/${path.map(encodeURIComponent).join("/")}${search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });

  const method = request.method;
  const hasBody = method !== "GET" && method !== "HEAD";

  let upstream: Response;
  const deadline = AbortSignal.timeout(UPSTREAM_TIMEOUT_MS);
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
      signal: deadline,
    });
  } catch (cause) {
    // Logged with its cause: this message is the last word the user gets, and
    // without the underlying error a proxy fault is indistinguishable from a
    // stopped API. One of these cost a debugging session already.
    console.error(`Proxy ${method} ${target} failed:`, cause);
    // A request that ran out of time is not a missing API, and saying so sent
    // people looking for a stopped container when a local model was merely
    // thinking. The two need different words because they need different
    // actions.
    const timedOut =
      deadline.aborted || (cause instanceof Error && cause.name === "TimeoutError");
    return NextResponse.json(
      {
        detail: timedOut
          ? "CEREBRO took too long to answer. A local model can be slow on a large document — the work may still finish in the background, so try again in a moment."
          : "The CEREBRO API is unreachable. Please try again.",
      },
      { status: timedOut ? 504 : 502 },
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase()) && key.toLowerCase() !== "set-cookie") {
      responseHeaders.set(key, value);
    }
  });

  // Set-Cookie must be copied entry by entry: iterating the Headers object
  // folds multiple cookies into one comma-joined string, which browsers reject.
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }

  return new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

type Context = { params: Promise<{ path: string[] }> };

async function handler(request: NextRequest, context: Context) {
  const { path } = await context.params;
  return proxy(request, path);
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const HEAD = handler;
export const OPTIONS = handler;
