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
  /** "system" | "light" | "dark" */
  theme: string;
  ai_processing_mode: "local" | "cloud";
  local_provider: string | null;
  local_model: string | null;
  cloud_provider: string | null;
  cloud_model: string | null;
  cloud_ai_consent: boolean;
  cloud_ai_consent_at: string | null;

  /**
   * The embedding and chunking budget. Null means "inherit whatever this
   * deployment is configured with", which is why every one of these is
   * nullable rather than merely optional: sending null clears an override,
   * sending nothing leaves it alone.
   */
  embedding_model: string | null;
  embedding_dimensions: number | null;
  embedding_context_limit: number | null;
  chunk_target_tokens: number | null;
  chunk_overlap_tokens: number | null;
  /** What is actually in force once the nulls above are resolved. */
  effective?: CerebroEffectiveIngestSettings | null;
}

export interface CerebroEffectiveIngestSettings {
  embedding_model: string | null;
  embedding_dimensions: number | null;
  embedding_context_limit: number;
  chunk_target_tokens: number;
  chunk_overlap_tokens: number;
  chunk_target_chars: number;
  /** Which of the five the user chose rather than inherited. */
  overridden: string[];
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
  technologies: string[];
  concepts: string[];
}

export interface CerebroArtifactSummary {
  id: string;
  filename: string;
  modality: string;
  size_bytes: number;
  /** "processing" means stored but not yet read — a large file in flight. */
  status: "processing" | "inspected" | "approved" | "registered" | "rejected";
  /** Why a rejected artifact was rejected, when extraction refused it late. */
  rejection_reason?: string | null;
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
  /** value -> the sentence in the document it was found in. */
  evidence?: Record<string, string>;
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
  /** The enrichment job, empty when the model has never been asked. */
  enrichment_job: CerebroEnrichmentJob;
  preview: string | null;
}

/** One request serves the whole dashboard. */
export interface CerebroDashboard {
  documents: { total: number; new_this_week: number };
  fragments: { total: number; new_this_week: number };
  topics: { total: number; new_this_week: number };
  /** quota_bytes and percent stay null until a quota exists. */
  storage: { bytes: number; quota_bytes: number | null; percent: number | null };
  recent: {
    id: string;
    filename: string;
    modality: string;
    size_bytes: number;
    status: CerebroArtifactSummary["status"];
    created_at: string;
  }[];
  activity: { date: string; count: number }[];
  topic_distribution: { slices: { label: string; count: number }[]; total: number };
  knowledge_map: {
    center: string | null;
    nodes: { label: string; count: number }[];
    edges: { source: string; target: string; weight: number }[];
    /** What an edge means. Co-occurrence, not an inferred semantic relation. */
    basis: string;
  };
  recollection: {
    topic: string;
    document_count: number;
    artifacts: { id: string; filename: string; modality: string }[];
  }[];
}

/* --- Knowledge Galaxy ---------------------------------------------------- */

export interface GraphNode {
  id: string;
  label: string;
  /** "cluster" (a confirmed topic) or "fragment" (a knowledge fragment). */
  type: "cluster" | "fragment";
  category: string;
  document_count: number;
  fragment_count: number;
  relationship_count: number;
  provenance: string;
  source_artifact_id: string | null;
  source_fragment_id: string | null;
  source_location: Record<string, number | string> | null;
  source_filename: string | null;
  source_title: string | null;
  excerpt: string | null;
  kind: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  /** "co_occurrence" or "contains" — never a verified semantic relation. */
  kind: string;
  weight: number;
  relevance: string;
  /** Why this edge is drawn, in a sentence. */
  explanation: string;
  /** The documents it rests on, by name. */
  evidence: string[];
  evidence_count: number;
  /** A count of supporting documents, stated as such — not a score. */
  confidence: string;
  status: string;
  /** False for an edge resting on one document: shown only on selection. */
  strong: boolean;
}

export interface CerebroGalaxy {
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters: string[];
  truncated: boolean;
}

export interface CerebroNodeDetails {
  id: string;
  label: string;
  type: string;
  category: string;
  description: string | null;
  provenance: string;
  fragment_count: number;
  document_count: number;
  created_at: string | null;
  source_artifact_id: string | null;
  source_fragment_id: string | null;
  source_location: Record<string, number | string> | null;
  related: { id: string; label: string; relevance: string; explanation: string }[];
  documents: {
    artifact_id: string;
    filename: string;
    title: string | null;
    source_location: Record<string, number | string> | null;
    excerpt: string | null;
  }[];
  people: { name: string; documents: string[] }[];
}

export interface CerebroTimelineEvent {
  id: string;
  artifact_id: string;
  title: string;
  filename: string;
  date: string;
  /** Where the date came from. Never inferred. */
  basis: "document_metadata" | "registered_at";
  category: string;
  topics: string[];
  description: string | null;
  /** The opening of the document itself, quoted. Null when it has no fragments. */
  preview: string | null;
  modality: string;
}

export interface CerebroRecallSource {
  index: number;
  fragment_id: string;
  artifact_id: string;
  filename: string;
  title: string | null;
  source_location: Record<string, number | string>;
  excerpt: string;
  score: number;
  /** Confirmed topics of the source document, for mapping onto the Galaxy. */
  topics?: string[];
}

export interface CerebroRecallAnswer {
  /** Null when no local model phrased one; the sources still stand alone. */
  answer: string | null;
  sources: CerebroRecallSource[];
  grounded: boolean;
  model: string | null;
  note: string | null;
  /** Passages the answer cited, after citations to absent passages were cut. */
  cited?: number[];
  abstained?: boolean;
  telemetry?: CerebroRecallTelemetry | null;
}

/** One event from the streaming endpoint. */
export type RecallEvent =
  | { type: "sources"; sources: CerebroRecallSource[] }
  | { type: "delta"; text: string }
  | { type: "error"; message: string }
  | {
      type: "done";
      answer: string | null;
      grounded: boolean;
      model: string | null;
      note: string | null;
      abstained: boolean;
      cited: number[];
      telemetry: CerebroRecallTelemetry | null;
    };

export type SearchMode = "keyword" | "semantic" | "hybrid";
export type SearchScope = "all" | "library" | "knowledge";

export interface CerebroSearchFilters {
  modalities?: string[];
  statuses?: string[];
  topics?: string[];
  tags?: string[];
  people?: string[];
  organizations?: string[];
  projects?: string[];
  uploaded_from?: string | null;
  uploaded_to?: string | null;
}

export interface CerebroKnowledgeHit {
  fragment_id: string;
  artifact_id: string;
  filename: string;
  title: string | null;
  content: string;
  /** The matched passage, with terms marked by the keyword retrieval. */
  excerpt: string;
  source_location: Record<string, number | string>;
  topics: string[];
  score: number;
  /** Which retrievals found it: keyword, semantic, or both. */
  matched_by: string[];
  /** Words, never a percentage — a fused rank is not a confidence. */
  relevance: string;
}

export interface CerebroDocumentHit {
  artifact_id: string;
  filename: string;
  modality: string;
  /** Carried so a draft is never read as established knowledge. */
  status: string;
  created_at: string;
  title: string | null;
  topics: string[];
  tags: string[];
  score: number;
  relevance: string;
}

export interface CerebroSearchResults {
  query: string;
  mode: SearchMode;
  scope: SearchScope;
  documents: CerebroDocumentHit[];
  knowledge: CerebroKnowledgeHit[];
  concepts: { label: string; count: number }[];
  total_documents: number;
  total_knowledge: number;
  took_ms: number;
  /** Set when half a hybrid search was unavailable. */
  note: string | null;
}

export interface CerebroRecallTelemetry {
  model: string;
  duration_ms: number | null;
  /** Counted by the local daemon, not estimated in the browser. */
  prompt_tokens: number | null;
  completion_tokens: number | null;
  passages: number;
  top_score: number;
}

export interface CerebroMlStatus {
  ollama: {
    reachable: boolean;
    base_url: string | null;
    models: string[];
    answering_model: string | null;
    embedding_model: string | null;
    error: string | null;
  };
  embeddings: {
    provider: string;
    model: string;
    dimensions: number;
    /** False for the deterministic hashing embedder, which is not learned. */
    pretrained: boolean;
    fragments: number;
    embedded: number;
    missing: number;
  };
  retrieval: { vector_index: string; keyword_index: string; fusion: string };
  /** Null means nothing could measure it; it is shown as N/A, never guessed. */
  resources: {
    cpu_percent: number | null;
    memory_mb: number | null;
    memory_percent: number | null;
    gpu_percent: number | null;
    gpu_memory_mb: number | null;
    source: string;
    cpu_note?: string;
  };
  operations: {
    operation: string;
    model: string | null;
    duration_ms: number;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    algorithm: string | null;
    detail: string | null;
    status: string;
    execution_id: string;
    stage: string | null;
    at: number;
  }[];
}

export interface CerebroTimelineEventDetail {
  id: string;
  artifact_id: string;
  fragment_id: string;
  title: string;
  description: string | null;
  category: string;
  /** The word that put this event in its lane, or null for "Other". */
  category_basis: string | null;
  event_type: string;
  date: string;
  end_date: string | null;
  /** day | month | quarter | year — kept, never flattened. */
  precision: string;
  /** The date expression matched in the text, verbatim. */
  expression: string;
  /** "event", or "reference" for a date the document cites (a paper, a link). */
  kind: "event" | "reference";
  /** Why it is a reference: citation | link | reference list | copyright. */
  reference_basis: string | null;
  /** The sentence the event came from, verbatim. */
  evidence: string;
  source_location: Record<string, number | string>;
  filename: string;
  author: string | null;
  entities: Record<string, string[]>;
  extraction_method: string;
  approval_status: string;
  relationship?: string;
  /** What the document says about its own size and dates. */
  document: CerebroDocumentFacts;
}

/**
 * The document's own facts, each with where it came from.
 *
 * `created` and `modified` are the file's own metadata and are frequently
 * null — a document that does not state when it was written does not get a
 * date invented for it, and the upload time is deliberately not used as a
 * stand-in. `registered` is the one date CEREBRO itself knows.
 */
export interface CerebroDocumentFacts {
  /** The document's own title, as confirmed at review. Null if none was. */
  title: string | null;
  title_basis: string | null;
  pages: number | null;
  blocks: number | null;
  characters: number | null;
  created: string | null;
  modified: string | null;
  registered: string | null;
  created_basis: string | null;
  modified_basis: string | null;
  registered_basis: string | null;
}

/**
 * One dated entry a CV states about its author.
 *
 * `extracted` keeps what the CV actually said, beside whatever the user
 * corrected it to, so a correction never destroys the record of the source.
 * A null date means the CV stated none — never "today".
 */
/** A summary shared by every stage and model row in the report. */
export interface PerfSummary {
  runs: number;
  failures: number;
  failure_rate: number | null;
  median_ms: number | null;
  p95_ms: number | null;
  slowest_ms: number | null;
  total_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
}

export interface PerfOperation {
  at: string;
  kind: string;
  operation: string;
  model: string | null;
  algorithm: string | null;
  duration_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  status: string;
  units: Record<string, string | number | boolean | null>;
}

export interface PerfAccuracyField {
  field: string;
  suggested: number;
  kept: number;
  final: number;
  added_by_user: number;
  dropped_by_user: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

export interface CerebroPerformance {
  window_days: number;
  generated_at: string;
  totals: {
    operations: number;
    model_calls: number;
    deterministic_calls: number;
    total_seconds: number;
    prompt_tokens: number | null;
    completion_tokens: number | null;
  };
  stages: (PerfSummary & { kind: string })[];
  models: (PerfSummary & { model: string })[];
  ingestion: PerfSummary & {
    documents: number;
    pages: number;
    bytes: number;
    ms_per_page: number | null;
    fragments: number;
    vectors: number;
    unvectorised: number;
  };
  recall: PerfSummary & {
    questions: number;
    answered: number;
    abstained: number;
    abstention_rate: number | null;
    citations: number;
    citations_per_answer: number | null;
  };
  search: PerfSummary;
  accuracy: {
    scored_documents: number;
    unscored_documents: number;
    fields: PerfAccuracyField[];
    precision: number | null;
    basis: string;
  };
  operations: PerfOperation[];
  truncated: boolean;
}

/** An enrichment job's state, as it sits on the artifact row. */
export interface CerebroEnrichmentJob {
  status?: "queued" | "running" | "done" | "failed";
  /** Windows of the document read so far, and how many there are. */
  progress?: number;
  total?: number | null;
  model?: string | null;
  error?: string | null;
  notes?: string[];
  ai_used?: boolean;
}

export interface CerebroEnrichmentQueue {
  jobs: {
    artifact_id: string;
    filename: string;
    status: string;
    progress: number;
    total: number | null;
    model: string | null;
    /** Place in the line, so "waiting" has a number attached. */
    position: number;
  }[];
  running: number;
  waiting: number;
  max_concurrent: number;
}

export interface CerebroAnchor {
  id: string;
  event_type: string;
  title: string;
  organization: string | null;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  /** day | month | year | unknown — never widened by guessing. */
  date_precision: string;
  source_artifact_id: string | null;
  source_location: Record<string, number | string>;
  evidence_text: string | null;
  extracted: Partial<CerebroAnchor>;
  /** "cv_extraction" or "user_entered". */
  provenance_type: string;
  approval_status: string;
  user_edited: boolean;
}

export interface CvExtraction {
  found: number;
  added: number;
  refreshed: number;
  preserved_user_edits: number;
}

export interface CerebroCv {
  /** none | processing | needs_review | approved. */
  status: string;
  filename: string | null;
  uploaded_at: string | null;
  artifact_id: string | null;
  anchors: CerebroAnchor[];
  suggested: number;
  approved: number;
}

export interface CerebroTimeline {
  events: CerebroTimelineEventDetail[];
  lanes: { name: string; count: number }[];
  histogram: {
    month: string;
    count: number;
    /** Volume: pages where documents report them, one per document otherwise. */
    pages: number;
    documents: number;
    by_category: Record<string, number>;
    basis: string;
  }[];
  range: { earliest: string | null; latest: string | null };
  sources: [string, string][];
  entity_values: Record<string, string[]>;
  /** Approved CV anchors: a backdrop for the lanes, never a date source. */
  anchors: CerebroAnchor[];
  extraction: {
    method: string;
    version: number;
    fragments_scanned: number;
    events: number;
    duplicates_dropped: number;
    unknown_dates: number;
    took_ms: number;
  };
  /** Cited dates: hidden unless asked for, and always counted. */
  references: { included: boolean; hidden: number; total: number };
  total: number;
  took_ms: number;
}

export interface CerebroBulkUpload {
  items: { filename: string; accepted: boolean; artifact: CerebroArtifact | null; error: string | null }[];
  accepted: number;
  rejected: number;
}

export interface CerebroBulkReview {
  items: { id: string; registered: boolean; artifact: CerebroArtifact | null; error: string | null }[];
  registered: number;
  failed: number;
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

  dashboard: () => request<CerebroDashboard>("/api/dashboard"),

  galaxy: () => request<CerebroGalaxy>("/api/graph"),

  /** Unified search. Hybrid by default: neither retrieval alone is reliable. */
  search: (input: {
    query: string;
    mode?: SearchMode;
    scope?: SearchScope;
    limit?: number;
    filters?: CerebroSearchFilters;
  }) =>
    request<CerebroSearchResults>("/api/search", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  /** Completions drawn from the user's own confirmed metadata. */
  searchSuggestions: (prefix: string) =>
    request<{ prefix: string; suggestions: string[] }>(
      `/api/search/suggestions?q=${encodeURIComponent(prefix)}`,
    ),

  /** What AI and ML is actually installed, selected and running. */
  mlStatus: () => request<CerebroMlStatus>("/api/ml/status"),

  /** Actually run the models: one short generation and one embedding. */
  probeModels: () =>
    request<{
      base_url: string;
      models: string[];
      generation: {
        model: string | null;
        ok: boolean;
        sample?: string;
        duration_ms?: number;
        prompt_tokens?: number | null;
        completion_tokens?: number | null;
        error?: string;
      };
      embedding: {
        provider: string;
        model: string;
        ok: boolean;
        dimensions?: number;
        declared_dimensions?: number;
        duration_ms?: number;
        error?: string;
      };
    }>("/api/ml/probe", { method: "POST" }),

  /** Embed fragments that have no vector for the active model. */
  backfillEmbeddings: () =>
    request<{
      provider: string;
      model: string;
      dimensions: number;
      embedded: number;
      remaining: number;
    }>("/api/ml/embeddings/backfill", { method: "POST" }),

  /** Retrieval-first. The model, if any, only sees retrieved passages. */
  recall: (input: { question: string; topic?: string | null }) =>
    request<CerebroRecallAnswer>("/api/recall", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  /** One cluster's fragments, fetched when it is opened. */
  expandCluster: (topic: string) =>
    request<CerebroGalaxy>(`/api/graph/expand?topic=${encodeURIComponent(topic)}`),

  graphNode: (id: string) =>
    request<CerebroNodeDetails>(`/api/graph/node?id=${encodeURIComponent(id)}`),

  /** Events dated by the documents themselves, with their evidence. */
  timeline: (params?: {
    categories?: string[];
    sources?: string[];
    entity_type?: string;
    entity?: string;
    start?: string;
    end?: string;
    /** Include dates the documents cite rather than state as events. */
    references?: boolean;
  }) => {
    const query = new URLSearchParams();
    for (const value of params?.categories ?? []) query.append("categories", value);
    for (const value of params?.sources ?? []) query.append("sources", value);
    if (params?.entity_type) query.set("entity_type", params.entity_type);
    if (params?.entity) query.set("entity", params.entity);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    if (params?.references) query.set("references", "true");
    const suffix = query.toString();
    return request<CerebroTimeline>(`/api/timeline${suffix ? `?${suffix}` : ""}`);
  },

  timelineRelated: (event: string) =>
    request<{ event: CerebroTimelineEventDetail; related: CerebroTimelineEventDetail[] }>(
      `/api/timeline/related?event=${encodeURIComponent(event)}`,
    ),

  knowledgeTimeline: () =>
    request<{ events: CerebroTimelineEvent[] }>("/api/graph/timeline"),

  artifacts: () =>
    request<{ items: CerebroArtifactSummary[]; total: number }>("/api/artifacts"),

  artifact: (id: string) => request<CerebroArtifact>(`/api/artifacts/${id}`),

  /** Delete an artifact, the knowledge from it, and its stored bytes. */
  deleteArtifact: (id: string) =>
    request<void>(`/api/artifacts/${id}`, { method: "DELETE" }),

  /** Ask for an artifact still waiting to be read to be read now. */
  processArtifact: (id: string) =>
    request<CerebroArtifact>(`/api/artifacts/${id}/process`, { method: "POST" }),

  /** Measured cost and accuracy of this user's own AI/ML operations. */
  performance: (days = 30) =>
    request<CerebroPerformance>(`/api/performance?days=${days}`),

  /** The CV's state and its anchors — always and only this user's. */
  cv: () => request<CerebroCv>("/api/cv"),

  uploadCv: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<CerebroCv & { extraction: CvExtraction }>("/api/cv", {
      method: "POST",
      body,
      rawBody: true,
    });
  },

  correctAnchor: (id: string, changes: Partial<CerebroAnchor>) =>
    request<CerebroAnchor>(`/api/cv/anchors/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  addAnchor: (values: Partial<CerebroAnchor>) =>
    request<CerebroAnchor>("/api/cv/anchors", {
      method: "POST",
      body: JSON.stringify(values),
    }),

  approveAnchors: () => request<CerebroCv>("/api/cv/approve", { method: "POST" }),

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

  /**
   * Queue this artifact for enrichment by the local model.
   *
   * Accepted, not done. Enrichment runs in a background queue, so this
   * returns at once and the page polls `enrichmentQueue` for progress —
   * which is why leaving the page no longer abandons the work.
   */
  suggestArtifact: (id: string) =>
    request<CerebroEnrichmentJob & { artifact_id: string }>(
      `/api/artifacts/${id}/suggest`,
      { method: "POST" },
    ),

  /** What is waiting or running for this user, and how many may run at once. */
  enrichmentQueue: () => request<CerebroEnrichmentQueue>("/api/artifacts/enrichment/queue"),

  /** Several files in one request. Each succeeds or fails on its own. */
  uploadArtifacts: (list: File[]) => {
    const body = new FormData();
    for (const file of list) body.append("files", file);
    return request<CerebroBulkUpload>("/api/artifacts/bulk", {
      method: "POST",
      body,
      rawBody: true,
    });
  },

  /** Confirm metadata for several artifacts, registering each. */
  reviewArtifacts: (
    items: { id: string; metadata: CerebroArtifactMetadata }[],
    approve: boolean,
  ) =>
    request<CerebroBulkReview>("/api/artifacts/bulk", {
      method: "PATCH",
      body: JSON.stringify({ items, approve }),
    }),

  reviewArtifact: (id: string, input: { metadata: CerebroArtifactMetadata; approve: boolean }) =>
    request<CerebroArtifact>(`/api/artifacts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),

};
