/**
 * Browser-side CEREBRO API client.
 *
 * All requests send credentials so the httpOnly session cookie travels with
 * them. No component talks to the API except through this module.
 */
/**
 * Where the browser sends API requests.
 *
 * Empty by default, meaning same-origin: Next.js rewrites /api to the backend
 * (see next.config.ts). That keeps the session cookie first-party everywhere,
 * needs no CORS, and works identically in development, compose and Kubernetes.
 *
 * Override NEXT_PUBLIC_API_BASE_URL only to bypass the proxy and call the API
 * directly. It is inlined at BUILD time, so it cannot be changed by a runtime
 * environment variable in a container.
 *
 * Trailing slashes are stripped: a configured "/" would otherwise produce
 * "//api/auth/login", which a browser resolves as a protocol-relative URL
 * pointing at a host called "api".
 */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/+$/, "");

export interface CerebroUser {
  id: string;
  display_name: string;
  email: string;
  created_at: string;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Turn a FastAPI error body into a single human-readable sentence. */
function extractDetail(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null) return fallback;
  const detail = (body as { detail?: unknown }).detail;

  if (typeof detail === "string") return detail;

  // 422 from Pydantic: a list of per-field errors.
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    if (typeof first.msg === "string") {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined;
      const label = typeof field === "string" ? humanise(field) : null;
      const msg = first.msg.replace(/^Value error,\s*/i, "");
      return label ? `${label}: ${msg}` : msg;
    }
  }
  return fallback;
}

function humanise(field: string): string {
  return field.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    // Network-level failure: the API is unreachable, not rejecting us.
    throw new ApiError(0, "Unable to reach CEREBRO. Check your connection and try again.");
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(response.status, extractDetail(body, "Something went wrong."));
  }
  return body as T;
}

export const api = {
  signup: (input: { display_name: string; email: string; password: string }) =>
    request<CerebroUser>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  login: (input: { email: string; password: string }) =>
    request<CerebroUser>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  me: () => request<CerebroUser>("/api/auth/me"),

  logout: () => request<{ message: string }>("/api/auth/logout", { method: "POST" }),
};
