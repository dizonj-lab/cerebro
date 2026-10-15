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

interface RequestInitEx extends RequestInit {
  /** Send the body untouched (FormData), letting the browser set the boundary. */
  rawBody?: boolean;
}

async function request<T>(path: string, init?: RequestInitEx): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: init?.rawBody
        ? { ...init?.headers }
        : { "Content-Type": "application/json", ...init?.headers },
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

export interface CerebroProfile {
  full_name: string | null;
  bio: string | null;
  location: string | null;
  timezone: string | null;
  avatar_url: string | null;
  role_title: string | null;
  organization: string | null;
  industry: string | null;
  years_experience: number | null;
  expertise: string[];
  interests: string[];
  current_topics: string[];
  learning_goals: string | null;
  career_goals: string | null;
  completion_percent: number;
  completed_fields: number;
  total_fields: number;
}

export interface CerebroPreferences {
  response_style: string;
  ai_suggestions: boolean;
  recall_suggestions: boolean;
  knowledge_visibility: string;
  ai_processing_mode: "local" | "cloud";
  local_provider: string | null;
  local_model: string | null;
  cloud_provider: string | null;
  cloud_model: string | null;
  cloud_ai_consent: boolean;
  cloud_ai_consent_at: string | null;
}

export interface CerebroAccount {
  id: string;
  display_name: string;
  email: string;
  created_at: string;
  last_login_at: string | null;
}

export interface CerebroArtifactMetadata {
  title: string | null;
  description: string | null;
  language: string | null;
  author: string | null;
  created_date: string | null;
  topics: string[];
  people: string[];
  organizations: string[];
  projects: string[];
  tags: string[];
}

export interface CerebroArtifactSummary {
  id: string;
  filename: string;
  modality: string;
  size_bytes: number;
  status: "inspected" | "approved" | "registered" | "rejected";
  sha256: string;
  title: string | null;
  created_at: string;
  registered_at: string | null;
}

/** Summary of deterministic text extraction. Empty for artifacts ingested
 *  before extraction was wired into upload. */
export interface CerebroArtifactExtraction {
  block_count?: number;
  character_count?: number;
  structure?: Record<string, number>;
  errors?: string[];
  method?: string;
  ai_used?: boolean;
  modality?: string;
  object_key?: string;
}

/** Proposed metadata. Nothing is saved until the user approves it. */
export interface CerebroEnrichmentSuggestion {
  suggestions: Partial<CerebroArtifactMetadata>;
  field_methods: Record<string, string>;
  /** False means no model contributed; `notes` says why. */
  ai_used: boolean;
  engine: string;
  model: string | null;
  /** False would mean content left the CEREBRO environment. No engine does. */
  local: boolean;
  notes: string[];
}

export interface CerebroArtifact extends CerebroArtifactSummary {
  content_type: string | null;
  metadata: CerebroArtifactMetadata;
  field_methods: Record<string, string>;
  inspection: Record<string, never> | Record<string, unknown>;
  extraction: CerebroArtifactExtraction;
  provenance: Record<string, unknown>;
  integrity: Record<string, boolean>;
  preview: string | null;
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

  profile: () => request<CerebroProfile>("/api/profile"),

  saveProfile: (input: Partial<CerebroProfile>) =>
    request<CerebroProfile>("/api/profile", { method: "PATCH", body: JSON.stringify(input) }),

  preferences: () => request<CerebroPreferences>("/api/preferences"),

  savePreferences: (input: Partial<CerebroPreferences>) =>
    request<CerebroPreferences>("/api/preferences", {
      method: "PATCH",
      body: JSON.stringify(input),
    }),

  account: () => request<CerebroAccount>("/api/account"),

  changePassword: (input: { current_password: string; new_password: string }) =>
    request<{ message: string }>("/api/account/password", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  artifacts: () =>
    request<{ items: CerebroArtifactSummary[]; total: number }>("/api/artifacts"),

  artifact: (id: string) => request<CerebroArtifact>(`/api/artifacts/${id}`),

  uploadArtifact: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    // No Content-Type header: the browser must set the multipart boundary.
    return request<CerebroArtifact>("/api/artifacts", { method: "POST", body, rawBody: true });
  },

  /**
   * Where the original uploaded file is served from.
   *
   * A URL rather than a fetch: the browser opens it in a tab, so the session
   * cookie travels with the navigation and nothing has to be held in memory.
   */
  artifactContentUrl: (id: string) => `${API_BASE_URL}/api/artifacts/${id}/content`,

  /** Ask the configured local model to propose metadata. Saves nothing. */
  suggestArtifact: (id: string) =>
    request<CerebroEnrichmentSuggestion>(`/api/artifacts/${id}/suggest`, { method: "POST" }),

  reviewArtifact: (id: string, input: { metadata: CerebroArtifactMetadata; approve: boolean }) =>
    request<CerebroArtifact>(`/api/artifacts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),

  deleteArtifact: (id: string) =>
    request<void>(`/api/artifacts/${id}`, { method: "DELETE" }),
};
