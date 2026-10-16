"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { CerebroDashboard, CerebroPreferences } from "@/lib/api";

const REFRESH_MS = 15_000;

interface Telemetry {
  dashboard: CerebroDashboard;
  preferences: CerebroPreferences;
  /** Round trip for the dashboard request, measured in this browser. */
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
 * There is no server-side metrics backend — no request rates, no CPU, no
 * queue depth — so none is displayed. A dial reading a number nobody
 * measured would be worse than an absent dial.
 */
export function GodModePanel() {
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;

    async function load() {
      const started = performance.now();
      try {
        const [dashboard, preferences] = await Promise.all([api.dashboard(), api.preferences()]);
        if (!live) return;
        setTelemetry({
          dashboard,
          preferences,
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

  const { dashboard, preferences, roundTripMs, at } = telemetry;
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

      <Row label="Local engine">
        {preferences.local_provider ?? "not configured"}
        {preferences.local_model && (
          <span className="text-ink-subtle"> · {preferences.local_model}</span>
        )}
      </Row>

      {/* Stated plainly: there is no cloud engine in CEREBRO, and this row
          exists so GOD MODE cannot be read as hiding one. */}
      <Row label="Cloud engine">
        {preferences.cloud_provider ?? "none — processing stays in the CEREBRO environment"}
      </Row>

      <Row label="API round trip">{roundTripMs} ms</Row>

      <p className="border-t border-line pt-2 text-xs text-ink-subtle">
        Counts read from your library at {at.toLocaleTimeString()}, refreshed every{" "}
        {REFRESH_MS / 1000}s. Round trip measured in this browser; CEREBRO keeps no
        server-side metrics.
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
