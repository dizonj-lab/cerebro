import "server-only";

import { cookies } from "next/headers";

import type { CerebroProfile, CerebroUser } from "@/lib/api";

export const SESSION_COOKIE = process.env.NEXT_PUBLIC_SESSION_COOKIE ?? "cerebro_session";

/**
 * Base URL used for server-to-server calls. In Kubernetes this is the
 * in-cluster Service DNS name, which never leaves the namespace.
 */
const INTERNAL_API_BASE_URL =
  process.env.INTERNAL_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

/**
 * Resolve the current user by validating the session cookie with the API.
 *
 * Returns null for any unauthenticated or unverifiable state. This is the
 * authority on whether a request is authenticated — middleware only checks
 * that a cookie is present, which is a cheap precheck, not verification.
 */
export async function getCurrentUser(): Promise<CerebroUser | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;

  try {
    const response = await fetch(`${INTERNAL_API_BASE_URL}/api/auth/me`, {
      headers: { Cookie: `${SESSION_COOKIE}=${token}` },
      // Session state must never be served from a cache.
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as CerebroUser;
  } catch {
    // API unreachable — treat as unauthenticated rather than crashing the page.
    return null;
  }
}


/** Server-side fetch of any authenticated endpoint, forwarding the cookie. */
async function authedGet<T>(path: string): Promise<T | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  try {
    const response = await fetch(`${INTERNAL_API_BASE_URL}${path}`, {
      headers: { Cookie: `${SESSION_COOKIE}=${token}` },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function getCurrentProfile(): Promise<CerebroProfile | null> {
  return authedGet<CerebroProfile>("/api/profile");
}
