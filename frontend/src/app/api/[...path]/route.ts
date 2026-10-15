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
]);

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
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    // The API is unreachable. Answer in the same JSON shape the API uses for
    // errors, so the client renders a real message instead of choking on an
    // HTML or plain-text error page.
    return NextResponse.json(
      { detail: "The CEREBRO API is unreachable. Please try again." },
      { status: 502 },
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
