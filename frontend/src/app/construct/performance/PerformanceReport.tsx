"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/construct/PageHeader";
import { Donut, sliceColor } from "@/components/dashboard/charts";
import { Card, CardHeader, EmptyState, Skeleton } from "@/components/dashboard/primitives";
import { api } from "@/lib/api";
import type { CerebroPerformance, PerfOperation, PerfSummary } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * The Performance Report.
 *
 * What the models and algorithms actually cost, measured rather than
 * claimed. Three things it deliberately does not do:
 *
 * It does not print a number where there is no measurement. An empty
 * library shows "not measured yet", because a zero that looks like data is
 * worse than an absence that looks like one.
 *
 * It does not score a refusal as a failure. When Ask CEREBRO says it cannot
 * find something, that is correct behaviour; whether it was *right* needs a
 * human, so the rate is reported and never graded.
 *
 * It does not call acceptance correctness. Precision here means "the human
 * kept it", which is the only ground truth the review loop produces — the
 * caption says so, so nobody reads it as something stronger.
 */
const WINDOWS = [7, 30, 90] as const;

export function PerformanceReport() {
  const [data, setData] = useState<CerebroPerformance | null>(null);
  const [days, setDays] = useState<number>(30);
  const [loading, setLoading] = useState(true);

  // No setState in the body: the effect calls this directly, and the lint
  // rule that forbids it is right — a synchronous set here re-renders before
  // the fetch has even started. The window buttons set it instead, which is
  // where the user's intent actually is.
  const load = useCallback(() => {
    api
      .performance(days)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [days]);
  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Performance"
        description="What CEREBRO's models and algorithms cost, and how often their suggestions survive review."
      />

      <div className="flex flex-wrap items-center gap-2">
        {WINDOWS.map((window) => (
          <button
            key={window}
            type="button"
            onClick={() => {
              setLoading(true);
              setDays(window);
            }}
            className={cn(
              "rounded-lg border px-3 py-1.5 text-sm transition-colors",
              days === window
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-ink-muted hover:text-ink",
            )}
          >
            Last {window} days
          </button>
        ))}
        {data && (
          <span className="ml-auto text-xs text-ink-subtle">
            {data.totals.operations} operation{data.totals.operations === 1 ? "" : "s"} measured
          </span>
        )}
      </div>

      {loading && !data ? (
        <Skeleton className="h-64" />
      ) : !data || data.totals.operations === 0 ? (
        <Card>
          <EmptyState>
            Nothing measured yet. Upload a document, run a search or ask a question, and this
            page fills with what each one actually cost.
          </EmptyState>
        </Card>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" data-testid="perf-totals">
            <Stat label="Operations" value={data.totals.operations} hint={`over ${data.window_days} days`} />
            <Stat
              label="Model calls"
              value={data.totals.model_calls}
              hint={`${data.totals.deterministic_calls} ran without a model`}
            />
            <Stat
              label="Total compute"
              value={`${data.totals.total_seconds}s`}
              hint="wall clock, all operations"
            />
            <Stat
              label="Tokens"
              value={
                data.totals.prompt_tokens || data.totals.completion_tokens
                  ? `${(data.totals.prompt_tokens ?? 0) + (data.totals.completion_tokens ?? 0)}`
                  : "—"
              }
              hint={
                data.totals.prompt_tokens
                  ? `${data.totals.prompt_tokens} in · ${data.totals.completion_tokens ?? 0} out`
                  : "no model has run yet"
              }
            />
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader title="Where the time goes" />
              <p className="mt-0.5 text-xs text-ink-subtle">By stage, across the window</p>
              <div className="mt-4 flex items-center gap-5">
                <Donut
                  slices={data.stages.map((s) => ({ label: s.kind, count: Math.round(s.total_ms) }))}
                  total={data.stages.length}
                  label="stages"
                />
                <ul className="min-w-0 flex-1 space-y-1.5">
                  {data.stages.map((stage, index) => (
                    <li key={stage.kind} className="flex items-center gap-2 text-xs">
                      <span
                        className="size-2 shrink-0 rounded-full"
                        style={{ background: sliceColor(index) }}
                      />
                      <span className="flex-1 truncate capitalize text-ink">{stage.kind}</span>
                      <span className="tabular-nums text-ink-muted">
                        {(stage.total_ms / 1000).toFixed(1)}s
                      </span>
                      <span className="w-12 text-right tabular-nums text-ink-subtle">
                        ×{stage.runs}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>

            <Card>
              <CardHeader title="Latency by stage" />
              <p className="mt-0.5 text-xs text-ink-subtle">Median and 95th percentile, in milliseconds</p>
              <div className="mt-4 space-y-3" data-testid="perf-latency">
                {data.stages.map((stage) => (
                  <LatencyRow key={stage.kind} label={stage.kind} summary={stage} peak={peakOf(data)} />
                ))}
              </div>
            </Card>
          </section>

          <section className="grid gap-4 xl:grid-cols-3">
            <Card>
              <CardHeader title="Ingestion cost" />
              <p className="mt-0.5 text-xs text-ink-subtle">What reading documents took</p>
              <dl className="mt-3 space-y-1.5 text-sm">
                <Row label="Documents">{data.ingestion.documents}</Row>
                <Row label="Pages read">{data.ingestion.pages || "—"}</Row>
                <Row label="Bytes">{formatBytes(data.ingestion.bytes)}</Row>
                <Row label="Median per document">{ms(data.ingestion.median_ms)}</Row>
                <Row label="Per page">{ms(data.ingestion.ms_per_page)}</Row>
                <Row label="Fragments">{data.ingestion.fragments}</Row>
                <Row label="Vectors">{data.ingestion.vectors}</Row>
                {data.ingestion.unvectorised > 0 && (
                  // Invisible otherwise, and it decides whether semantic
                  // search can see a document at all.
                  <Row label="Not vectorised" warn>
                    {data.ingestion.unvectorised}
                  </Row>
                )}
              </dl>
            </Card>

            <Card>
              <CardHeader title="Ask CEREBRO" />
              <p className="mt-0.5 text-xs text-ink-subtle">Response cost, and what it did with it</p>
              <dl className="mt-3 space-y-1.5 text-sm" data-testid="perf-recall">
                <Row label="Questions">{data.recall.questions}</Row>
                <Row label="Median response">{ms(data.recall.median_ms)}</Row>
                <Row label="95th percentile">{ms(data.recall.p95_ms)}</Row>
                <Row label="Slowest">{ms(data.recall.slowest_ms)}</Row>
                <Row label="Answered">{data.recall.answered}</Row>
                <Row label="Said it could not find">{data.recall.abstained}</Row>
                <Row label="Citations per answer">
                  {data.recall.citations_per_answer ?? "—"}
                </Row>
              </dl>
              {/* Stated, not scored: a refusal is correct behaviour when the
                  library genuinely lacks the answer, and only a human can
                  say whether each one was right. */}
              <p className="mt-3 border-t border-border pt-2 text-[0.6875rem] leading-relaxed text-ink-subtle">
                A refusal is counted, never graded. Whether each one was correct needs you to
                know the answer was there.
              </p>
            </Card>

            <Card>
              <CardHeader title="Models and algorithms" />
              <p className="mt-0.5 text-xs text-ink-subtle">Who did the work</p>
              <div className="mt-3 space-y-2" data-testid="perf-models">
                {data.models.map((row) => (
                  <div key={row.model} className="rounded-lg border border-border p-2.5">
                    <p className="truncate text-sm font-medium text-ink">{row.model}</p>
                    <p className="mt-0.5 text-xs tabular-nums text-ink-muted">
                      {row.runs} run{row.runs === 1 ? "" : "s"} · median {ms(row.median_ms)} · p95{" "}
                      {ms(row.p95_ms)}
                    </p>
                    {row.failures > 0 && (
                      <p className="mt-0.5 text-xs text-danger">
                        {row.failures} did not complete
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </section>

          <Card>
            <CardHeader title="Suggestion accuracy" />
              <p className="mt-0.5 text-xs text-ink-subtle">How much of what the model proposed survived your review</p>
            {data.accuracy.fields.length === 0 ? (
              <EmptyState>
                Nothing scored yet. Register a document after reviewing its suggestions and this
                fills in.
                {data.accuracy.unscored_documents > 0 &&
                  ` ${data.accuracy.unscored_documents} document${data.accuracy.unscored_documents === 1 ? " was" : "s were"} registered before suggestions were kept, and ${data.accuracy.unscored_documents === 1 ? "is" : "are"} excluded rather than assumed correct.`}
              </EmptyState>
            ) : (
              <>
                <div className="mt-4 space-y-3" data-testid="perf-accuracy">
                  {data.accuracy.fields.map((field) => (
                    <div key={field.field}>
                      <div className="flex items-baseline justify-between text-xs">
                        <span className="font-medium capitalize text-ink">{field.field}</span>
                        <span className="tabular-nums text-ink-muted">
                          kept {field.kept}/{field.suggested}
                          {field.added_by_user > 0 && ` · you added ${field.added_by_user}`}
                        </span>
                      </div>
                      <div className="mt-1 flex gap-1.5">
                        <Meter label="Precision" value={field.precision} />
                        <Meter label="Recall" value={field.recall} />
                        <Meter label="F1" value={field.f1} />
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-4 border-t border-border pt-2 text-[0.6875rem] leading-relaxed text-ink-subtle">
                  {data.accuracy.basis} Scored on {data.accuracy.scored_documents} document
                  {data.accuracy.scored_documents === 1 ? "" : "s"}
                  {data.accuracy.unscored_documents > 0 &&
                    `, with ${data.accuracy.unscored_documents} excluded`}
                  . Counts are shown beside the rates because a percentage over a handful of
                  documents implies a population that is not there.
                </p>
              </>
            )}
          </Card>

          <Card>
            <CardHeader title="Every measurement" />
              <p className="mt-0.5 text-xs text-ink-subtle">The raw rows, for your own arithmetic</p>
            <OperationsTable rows={data.operations} truncated={data.truncated} />
          </Card>
        </>
      )}
    </div>
  );
}

function peakOf(data: CerebroPerformance): number {
  return Math.max(1, ...data.stages.map((s) => s.p95_ms ?? s.median_ms ?? 0));
}

function LatencyRow({
  label,
  summary,
  peak,
}: {
  label: string;
  summary: PerfSummary;
  peak: number;
}) {
  const median = summary.median_ms ?? 0;
  const p95 = summary.p95_ms ?? median;
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="capitalize text-ink">{label}</span>
        <span className="tabular-nums text-ink-muted">
          {ms(summary.median_ms)} · p95 {ms(summary.p95_ms)}
        </span>
      </div>
      {/* Two bars on one track: the typical case, and the tail behind it.
          An average alone hides the slow request the user actually notices. */}
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
        <div className="relative h-full">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-accent/30"
            style={{ width: `${Math.min(100, (p95 / peak) * 100)}%` }}
          />
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-accent"
            style={{ width: `${Math.min(100, (median / peak) * 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function Meter({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex-1">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${Math.round((value ?? 0) * 100)}%` }}
        />
      </div>
      <p className="mt-0.5 text-[0.625rem] tabular-nums text-ink-subtle">
        {label} {value === null ? "—" : value.toFixed(2)}
      </p>
    </div>
  );
}

function OperationsTable({ rows, truncated }: { rows: PerfOperation[]; truncated: boolean }) {
  const [kind, setKind] = useState<string>("all");
  const kinds = ["all", ...new Set(rows.map((r) => r.kind))];
  const shown = kind === "all" ? rows : rows.filter((r) => r.kind === kind);

  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-1.5">
        {kinds.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setKind(name)}
            className={cn(
              "rounded-md border px-2 py-1 text-xs capitalize transition-colors",
              kind === name
                ? "border-accent text-accent"
                : "border-border text-ink-muted hover:text-ink",
            )}
          >
            {name}
          </button>
        ))}
      </div>

      <div className="mt-3 max-h-[26rem] overflow-auto rounded-lg border border-border">
        <table className="w-full text-left text-xs" data-testid="perf-table">
          <thead className="sticky top-0 bg-surface-subtle text-ink-muted">
            <tr>
              <th className="px-2.5 py-2 font-medium">When</th>
              <th className="px-2.5 py-2 font-medium">Operation</th>
              <th className="px-2.5 py-2 font-medium">Model or algorithm</th>
              <th className="px-2.5 py-2 text-right font-medium">ms</th>
              <th className="px-2.5 py-2 text-right font-medium">Tokens</th>
              <th className="px-2.5 py-2 font-medium">Units</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row, index) => (
              <tr
                key={`${row.at}-${index}`}
                className="border-t border-border/60 align-top"
              >
                <td className="whitespace-nowrap px-2.5 py-1.5 tabular-nums text-ink-subtle">
                  {new Date(row.at).toLocaleString()}
                </td>
                <td className="px-2.5 py-1.5 text-ink">
                  {row.operation}
                  {row.status !== "ok" && (
                    <span className="ml-1.5 rounded bg-surface-sunken px-1 text-[0.625rem] text-ink-muted">
                      {row.status}
                    </span>
                  )}
                </td>
                <td className="px-2.5 py-1.5 text-ink-muted">
                  {row.model ?? row.algorithm ?? "—"}
                </td>
                <td className="px-2.5 py-1.5 text-right tabular-nums text-ink">
                  {row.duration_ms.toFixed(0)}
                </td>
                <td className="px-2.5 py-1.5 text-right tabular-nums text-ink-muted">
                  {row.prompt_tokens || row.completion_tokens
                    ? `${row.prompt_tokens ?? 0}/${row.completion_tokens ?? 0}`
                    : "—"}
                </td>
                <td className="px-2.5 py-1.5 text-ink-subtle">{describeUnits(row.units)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <p className="mt-2 text-[0.6875rem] text-ink-subtle">
          Showing the most recent 500 measurements.
        </p>
      )}
    </div>
  );
}

function describeUnits(units: PerfOperation["units"]): string {
  const parts = Object.entries(units)
    .filter(([, value]) => value !== null && value !== false && value !== "")
    .map(([key, value]) =>
      value === true ? key.replace(/_/g, " ") : `${key.replace(/_/g, " ")} ${value}`,
    );
  return parts.join(" · ") || "—";
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card>
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">{value}</p>
      {hint && <p className="mt-0.5 text-[0.6875rem] text-ink-subtle">{hint}</p>}
    </Card>
  );
}

function Row({
  label,
  children,
  warn,
}: {
  label: string;
  children: React.ReactNode;
  warn?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 pb-1.5 last:border-0">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className={cn("text-sm tabular-nums", warn ? "text-danger" : "text-ink")}>{children}</dd>
    </div>
  );
}

/** Milliseconds, or an explicit absence. Never 0 standing in for "unknown". */
function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
}

function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
