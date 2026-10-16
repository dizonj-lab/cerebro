"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { FilterRail } from "@/components/search/FilterRail";
import { RecollectionPanel } from "@/components/search/RecollectionPanel";
import { ResultActions } from "@/components/search/ResultActions";
import { api, ApiError } from "@/lib/api";
import type {
  CerebroSearchFilters,
  CerebroSearchResults,
  SearchMode,
  SearchScope,
} from "@/lib/api";
import { cn } from "@/lib/cn";

const MODES: { value: SearchMode; label: string; hint: string }[] = [
  {
    value: "hybrid",
    label: "Hybrid",
    hint: "Exact terms and meaning, fused. The default, because neither alone is reliable.",
  },
  { value: "keyword", label: "Keyword", hint: "Exact terms only. No model is used." },
  { value: "semantic", label: "Semantic", hint: "Meaning, using local embeddings." },
];

function countFilters(filters: CerebroSearchFilters): number {
  return (
    (filters.modalities?.length ?? 0) +
    (filters.statuses?.length ?? 0) +
    (filters.topics?.length ?? 0) +
    (filters.tags?.length ?? 0) +
    (filters.uploaded_from ? 1 : 0) +
    (filters.uploaded_to ? 1 : 0)
  );
}

/**
 * The search results page.
 *
 * Filters on the left, results in the centre, Assisted Recollection on the
 * right — one retrieval, grouped three ways. The query lives in the URL so a
 * search is a link that can be shared and reloaded, and the header form can
 * hand off to it with a plain submit.
 */
export function SearchView() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get("q") ?? "";

  const [query, setQuery] = useState(initial);
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [scope, setScope] = useState<SearchScope>("all");
  const [filters, setFilters] = useState<CerebroSearchFilters>({});
  const [results, setResults] = useState<CerebroSearchResults | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [topicOptions, setTopicOptions] = useState<string[]>([]);
  const [modalityOptions, setModalityOptions] = useState<string[]>([]);

  // The facets are the user's own confirmed topics and the document types
  // they actually have. No option is offered that nothing could match.
  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const [galaxy, library] = await Promise.all([api.galaxy(), api.artifacts()]);
        if (!live) return;
        setTopicOptions(
          galaxy.nodes
            .filter((node) => node.kind === "topic")
            .map((node) => node.label)
            .sort((a, b) => a.localeCompare(b)),
        );
        setModalityOptions([...new Set(library.items.map((a) => a.modality))].sort());
      } catch {
        // Facets are an aid, not the search. Their absence narrows the rail
        // rather than failing the page.
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  const run = useCallback(
    async (text: string, nextMode: SearchMode, nextScope: SearchScope, f: CerebroSearchFilters) => {
      const trimmed = text.trim();
      if (!trimmed) {
        setResults(null);
        return;
      }
      setBusy(true);
      setError(null);
      try {
        setResults(
          await api.search({
            query: trimmed,
            mode: nextMode,
            scope: nextScope,
            limit: 20,
            filters: f,
          }),
        );
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not reach CEREBRO.");
        setResults(null);
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  // A search runs on submit and whenever a control changes, never on each
  // keystroke: the query in the box is a draft until it is submitted.
  const submitted = useRef(initial);
  useEffect(() => {
    void run(submitted.current, mode, scope, filters);
  }, [run, mode, scope, filters]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    submitted.current = query;
    const next = new URLSearchParams(params.toString());
    if (query.trim()) next.set("q", query.trim());
    else next.delete("q");
    router.replace(`/construct/search?${next.toString()}`);
    void run(query, mode, scope, filters);
  }

  const activeFilters = useMemo(() => countFilters(filters), [filters]);
  const empty =
    results !== null && results.total_knowledge === 0 && results.total_documents === 0;

  return (
    <div className="flex flex-col gap-5">
      <form onSubmit={submit} role="search" className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          name="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search your knowledge"
          placeholder="Search your knowledge..."
          autoFocus
          className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-subtle focus:border-accent"
        />
        <button
          type="submit"
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-hover"
        >
          Search
        </button>
      </form>

      <div
        role="group"
        aria-label="Search mode"
        data-testid="search-modes"
        className="flex flex-wrap items-center gap-1 rounded-lg border border-line bg-surface-subtle p-1"
      >
        {MODES.map((option) => (
          <button
            key={option.value}
            type="button"
            title={option.hint}
            aria-pressed={mode === option.value}
            onClick={() => setMode(option.value)}
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              mode === option.value
                ? "bg-surface text-ink shadow-subtle"
                : "text-ink-muted hover:text-ink",
            )}
          >
            {option.label}
          </button>
        ))}
        <p className="ml-2 hidden text-xs text-ink-subtle sm:block">
          {MODES.find((m) => m.value === mode)?.hint}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[13rem_minmax(0,1fr)_18rem]">
        <FilterRail
          filters={filters}
          onChange={setFilters}
          scope={scope}
          onScopeChange={setScope}
          topicOptions={topicOptions}
          modalityOptions={modalityOptions}
          onClear={() => setFilters({})}
          activeCount={activeFilters}
        />

        <section aria-label="Search results" className="flex min-w-0 flex-col gap-4">
          {busy && <p className="text-sm text-ink-muted">Searching...</p>}
          {error && <p className="text-sm text-danger">{error}</p>}

          {results && !busy && (
            <p data-testid="result-summary" className="text-xs text-ink-subtle">
              {results.total_knowledge} passage{results.total_knowledge === 1 ? "" : "s"} and{" "}
              {results.total_documents} document{results.total_documents === 1 ? "" : "s"} for
              “{results.query}” · {results.mode} · {Math.round(results.took_ms)} ms
            </p>
          )}

          {/*
            A note means one half of a hybrid search was unavailable. It is
            shown rather than silently returning a shortened result set.
          */}
          {results?.note && (
            <p className="rounded-md border border-line bg-surface-subtle px-3 py-2 text-xs text-ink-muted">
              {results.note}
            </p>
          )}

          {empty && (
            <div data-testid="no-results" className="rounded-lg border border-line p-6 text-sm">
              <p className="font-medium text-ink">Nothing in your library matches that.</p>
              <p className="mt-1 text-ink-muted">
                Try semantic mode for a paraphrase, clear a filter, or ingest the document
                this should have come from.
              </p>
            </div>
          )}

          {results && results.concepts.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-ink-subtle">Concepts:</span>
              {results.concepts.map((concept) => (
                <button
                  key={concept.label}
                  type="button"
                  onClick={() =>
                    setFilters((f) => ({
                      ...f,
                      topics: [...new Set([...(f.topics ?? []), concept.label])],
                    }))
                  }
                  className="rounded-full border border-line px-2.5 py-0.5 text-xs text-ink-muted transition-colors hover:border-accent hover:text-ink"
                >
                  {concept.label} · {concept.count}
                </button>
              ))}
            </div>
          )}

          {results && results.knowledge.length > 0 && (
            <div className="flex flex-col gap-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">
                Knowledge
              </h2>
              {results.knowledge.map((hit) => (
                <article
                  key={hit.fragment_id}
                  data-testid="knowledge-result"
                  className="rounded-lg border border-line bg-surface p-4"
                >
                  <header className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-medium text-ink">{hit.title || hit.filename}</h3>
                    <span className="text-xs text-ink-subtle">
                      {hit.relevance} · found by {hit.matched_by.join(" and ")}
                    </span>
                  </header>
                  {/*
                    The excerpt carries <mark> from PostgreSQL's own
                    highlighter, which emits only that tag around matched
                    terms. Everything else in it is the document's own text.
                  */}
                  <p
                    className="mt-1.5 text-sm leading-relaxed text-ink-muted [&_mark]:bg-accent-subtle [&_mark]:text-ink"
                    dangerouslySetInnerHTML={{ __html: hit.excerpt }}
                  />
                  <p className="mt-2 text-xs text-ink-subtle">
                    {hit.filename}
                    {describeLocation(hit.source_location)}
                  </p>
                  <ResultActions
                    artifactId={hit.artifact_id}
                    filename={hit.filename}
                    title={hit.title}
                    sourceLocation={hit.source_location}
                    topic={hit.topics[0] ?? null}
                    onAsk={() =>
                      setQuestion(
                        `About “${hit.title || hit.filename}”: ${hit.content.slice(0, 120)}`,
                      )
                    }
                    onFilterTopic={(topic) =>
                      setFilters((f) => ({
                        ...f,
                        topics: [...new Set([...(f.topics ?? []), topic])],
                      }))
                    }
                  />
                </article>
              ))}
            </div>
          )}

          {results && results.documents.length > 0 && (
            <div className="flex flex-col gap-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">
                Documents
              </h2>
              {results.documents.map((hit) => (
                <article
                  key={hit.artifact_id}
                  data-testid="document-result"
                  className="rounded-lg border border-line bg-surface p-4"
                >
                  <header className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-medium text-ink">{hit.title || hit.filename}</h3>
                    <span className="text-xs text-ink-subtle">{hit.relevance}</span>
                  </header>
                  <p className="mt-1 text-xs text-ink-subtle">
                    {hit.modality} ·{" "}
                    {hit.status === "registered" ? (
                      "registered"
                    ) : (
                      <span data-testid="not-knowledge" className="text-ink-muted">
                        {hit.status} — not part of your knowledge yet
                      </span>
                    )}
                  </p>
                  <ResultActions
                    artifactId={hit.artifact_id}
                    filename={hit.filename}
                    title={hit.title}
                    topic={hit.topics[0] ?? null}
                    onAsk={() => setQuestion(`What does “${hit.title || hit.filename}” say about `)}
                    onFilterTopic={(topic) =>
                      setFilters((f) => ({
                        ...f,
                        topics: [...new Set([...(f.topics ?? []), topic])],
                      }))
                    }
                  />
                </article>
              ))}
            </div>
          )}
        </section>

        <RecollectionPanel
          question={question}
          onQuestionChange={setQuestion}
          topic={filters.topics?.[0] ?? null}
        />
      </div>
    </div>
  );
}

function describeLocation(location: Record<string, number | string>): string {
  const parts = Object.entries(location)
    .filter(([, value]) => value !== null && value !== "")
    .map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`);
  // Nothing is shown when extraction established no location: a modality
  // without pages has none, and "page 1" would be invented.
  return parts.length > 0 ? ` · ${parts.join(", ")}` : "";
}
