"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { CerebroDashboard, CerebroMlStatus, CerebroPreferences } from "@/lib/api";

const REFRESH_MS = 15_000;

interface Telemetry {
  dashboard: CerebroDashboard;
  preferences: CerebroPreferences;
  ml: CerebroMlStatus;
  /** Round trip for the request, measured in this browser. */
  roundTripMs: number;
  at: Date;
}

/**
 * What GOD MODE shows.
 *
 * Every number here is read from the user's own library through the existing
 * endpoints: document, fragment and topic counts, bytes stored, the last
 * week's ingestion, the most recent artifact and its status, and the engines
 * configured for this account. The one measurement taken here is the
 * round trip of the request itself, which the browser can honestly observe.
 *
 * It also shows what the AI and ML actually is: which local models are
 * installed and selected, whether the active embedder is a pretrained model
 * or the deterministic fallback, the algorithms behind retrieval, and the
 * last operations that ran with their durations and token counts as the
 * daemon reported them.
 *
 * There is still no server-side resource metrics backend — no CPU, no memory,
 * no queue depth — so none is displayed. A dial reading a number nobody
 * measured would be worse than an absent dial.
 */
export function GodModePanel() {
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [probe, setProbe] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);

  async function verify() {
    setProbing(true);
    setProbe(null);
    try {
      const result = await api.probeModels();
      // The model's own words, with what the call cost. An installed model
      // is not a working one, and this is the difference.
      setProbe(
        result.generation.ok
          ? `${result.generation.model}: “${result.generation.sample}” in ` +
            `${result.generation.duration_ms} ms · embedding ` +
            `${result.embedding.model} ${result.embedding.dimensions}d ` +
            `in ${result.embedding.duration_ms} ms`
          : `${result.generation.model ?? "no model"}: ${result.generation.error ?? "failed"}`,
      );
    } catch (e) {
      setProbe(e instanceof Error ? e.message : "Could not reach the local daemon.");
    } finally {
      setProbing(false);
    }
  }

  useEffect(() => {
    let live = true;

    async function load() {
      const started = performance.now();
      try {
        const [dashboard, preferences, ml] = await Promise.all([
          api.dashboard(),
          api.preferences(),
          api.mlStatus(),
        ]);
        if (!live) return;
        setTelemetry({
          dashboard,
          preferences,
          ml,
          roundTripMs: Math.round(performance.now() - started),
          at: new Date(),
        });
        setError(null);
      } catch (e) {
        if (live) setError(e instanceof ApiError ? e.message : "CEREBRO is not responding.");
      }
    }

    void load();
    // Polled rather than streamed: there is no event channel, and a 15s
    // poll of two cheap endpoints is honest about how fresh the numbers are.
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);

  if (error) {
    return <p className="p-4 text-sm text-danger">{error}</p>;
  }

  if (!telemetry) {
    return <p className="p-4 text-sm text-ink-muted">Reading your library...</p>;
  }

  const { dashboard, preferences, ml, roundTripMs, at } = telemetry;
  const week = dashboard.activity.slice(-7);
  const weekTotal = week.reduce((sum, day) => sum + day.count, 0);
  const recent = dashboard.recent[0];

  return (
    <div className="flex flex-col gap-3 p-3 text-sm">
      <section className="grid grid-cols-3 gap-2">
        <Stat label="Documents" value={dashboard.documents.total} delta={dashboard.documents.new_this_week} />
        <Stat label="Fragments" value={dashboard.fragments.total} delta={dashboard.fragments.new_this_week} />
        <Stat label="Topics" value={dashboard.topics.total} delta={dashboard.topics.new_this_week} />
      </section>

      <Row label="Stored">
        {formatBytes(dashboard.storage.bytes)}
        {/* No quota exists, so no percentage is shown rather than one against
            an invented ceiling. */}
        {dashboard.storage.quota_bytes === null && (
          <span className="text-ink-subtle"> · no quota configured</span>
        )}
      </Row>

      <Row label="Ingested this week">
        {weekTotal} {weekTotal === 1 ? "document" : "documents"}
      </Row>

      {recent && (
        <Row label="Most recent">
          <span className="truncate">{recent.filename}</span>
          <span className="text-ink-subtle"> · {recent.status}</span>
        </Row>
      )}

      <section className="flex flex-col gap-1.5 border-t border-line pt-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">
          Models
        </h3>

        <Row label="Ollama">
          {ml.ollama.reachable ? (
            <>
              {ml.ollama.base_url}
              <span className="text-ink-subtle"> · {ml.ollama.models.length} installed</span>
            </>
          ) : (
            // Named plainly, with the remedy, rather than shown as a blank.
            <span className="text-danger">not running</span>
          )}
        </Row>

        <Row label="Answering">
          {ml.ollama.answering_model ?? (
            <span className="text-ink-muted">none — passages only</span>
          )}
        </Row>

        <Row label="Embedding">
          {ml.embeddings.model}
          <span className="text-ink-subtle"> · {ml.embeddings.dimensions}d</span>
          {/* The distinction that matters: a hashing projection is not a
              learned model, and the panel must not let it pass for one. */}
          {!ml.embeddings.pretrained && (
            <span className="text-ink-muted"> · deterministic, not pretrained</span>
          )}
        </Row>

        <Row label="Embedded">
          {ml.embeddings.embedded}/{ml.embeddings.fragments} fragments
          {ml.embeddings.missing > 0 && (
            <span className="text-danger"> · {ml.embeddings.missing} missing</span>
          )}
        </Row>

        {ml.embeddings.missing > 0 && (
          <button
            type="button"
            data-testid="backfill-embeddings"
            onClick={() => void api.backfillEmbeddings().then(() => setTelemetry(null))}
            className="self-start rounded-md border border-line px-2 py-1 text-[11px] font-medium text-accent transition-colors hover:bg-surface-subtle"
          >
            Backfill {ml.embeddings.missing} embeddings
          </button>
        )}

        <div className="flex flex-wrap items-center gap-2 py-1">
          <button
            type="button"
            data-testid="verify-models"
            onClick={() => void verify()}
            disabled={probing}
            className="rounded-md border border-line px-2 py-1 text-[11px] font-medium text-accent transition-colors hover:bg-surface-subtle disabled:opacity-50"
          >
            {probing ? "Running..." : "Verify inference"}
          </button>
          {probe && (
            <span data-testid="probe-result" className="min-w-0 flex-1 text-[11px] text-ink-muted">
              {probe}
            </span>
          )}
        </div>

        <Row label="Retrieval">{ml.retrieval.vector_index}</Row>
        <Row label="Keyword">{ml.retrieval.keyword_index}</Row>
        <Row label="Fusion">{ml.retrieval.fusion}</Row>

        {/* Cloud engine stays listed so the panel cannot be read as hiding
            one. There is none. */}
        <Row label="Cloud engine">
          {preferences.cloud_provider ?? "none — processing stays in the CEREBRO environment"}
        </Row>
      </section>

      <section className="flex flex-col gap-1 border-t border-line pt-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">
          Last operations
        </h3>
        {ml.operations.length === 0 ? (
          <p className="text-xs text-ink-subtle">Nothing has run yet this session.</p>
        ) : (
          <ul data-testid="ml-operations" className="flex flex-col gap-1 text-xs">
            {ml.operations.slice(0, 8).map((op, i) => (
              <li key={`${op.operation}-${op.at}-${i}`} className="flex flex-col">
                <span className="text-ink">
                  {op.operation}
                  <span className="text-ink-subtle"> · {op.duration_ms} ms</span>
                </span>
                <span className="truncate text-ink-subtle">
                  {op.model ?? op.algorithm ?? "—"}
                  {op.algorithm && op.model ? ` · ${op.algorithm}` : ""}
                  {op.completion_tokens !== null && ` · ${op.completion_tokens} tokens out`}
                  {op.prompt_tokens !== null && ` · ${op.prompt_tokens} in`}
                  {op.detail ? ` · ${op.detail}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="border-t border-line pt-2 text-xs text-ink-subtle">
        Read at {at.toLocaleTimeString()}, refreshed every {REFRESH_MS / 1000}s. Durations
        and token counts come from the local daemon; the {roundTripMs} ms round trip is
        measured in this browser. CEREBRO keeps no server-side resource metrics.
      </p>
    </div>
  );
}

function Stat({ label, value, delta }: { label: string; value: number; delta: number }) {
  return (
    <div className="rounded-lg border border-line bg-surface-subtle p-2">
      <p className="text-lg font-semibold leading-tight text-ink">{value}</p>
      <p className="text-[11px] uppercase tracking-wide text-ink-subtle">{label}</p>
      {/* Only shown when something actually arrived this week. */}
      {delta > 0 && <p className="text-[11px] text-accent">+{delta} this week</p>}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-3 text-xs">
      <span className="shrink-0 uppercase tracking-wide text-ink-subtle">{label}</span>
      <span className="min-w-0 truncate text-right text-ink">{children}</span>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}
