"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { formatBytes } from "@/components/construct/ArtifactStatus";
import { CompletionMeter } from "@/components/construct/CompletionMeter";
import { Bars, Donut, sliceColor } from "@/components/dashboard/charts";
import { KnowledgeMap } from "@/components/dashboard/KnowledgeMap";
import { Card, CardHeader, EmptyState, Skeleton } from "@/components/dashboard/primitives";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { ApiError, api } from "@/lib/api";
import type { CerebroDashboard } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * The dashboard.
 *
 * One request fills every panel, so the page does not fan out on load, and
 * nothing here calls a language model — the suggestions in Assisted
 * Recollection are the user's own approved topics with the documents that
 * evidence them, not generated recommendations.
 */
interface DashboardViewProps {
  firstName: string;
  /** Topics and expertise the user entered on their profile. */
  focus: string[];
  /**
   * The profile-completion nudge, kept from the previous dashboard. It
   * predates this design and is a working feature, so it is preserved rather
   * than dropped for a cosmetic match; a complete profile shows nothing.
   */
  profile: { percent: number; completed: number; total: number } | null;
}

export function DashboardView({ firstName, focus, profile }: DashboardViewProps) {
  const [data, setData] = useState<CerebroDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .dashboard()
      .then(setData)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load your dashboard."),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  return (
    <div className="mx-auto max-w-[1600px]">
      <DashboardHeading firstName={firstName} focus={focus} />
      <ErrorMessage className="mt-4">{error}</ErrorMessage>

      {profile && (
        <Link
          href="/construct/profile"
          className="mt-4 flex items-center justify-between gap-4 rounded-xl border border-line bg-accent-subtle px-4 py-3 transition-colors hover:border-accent"
        >
          <span className="min-w-0 text-sm text-ink">
            {profile.percent === 0
              ? "Complete your profile to help CEREBRO understand your context."
              : "A little more context will help CEREBRO understand you."}
          </span>
          <span className="flex shrink-0 items-center gap-3">
            <CompletionMeter
              className="w-32"
              percent={profile.percent}
              completed={profile.completed}
              total={profile.total}
            />
            <span className="text-xs font-medium whitespace-nowrap text-accent">
              {profile.percent === 0 ? "Complete profile" : "Edit profile"}
            </span>
          </span>
        </Link>
      )}

      <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <Metrics data={data} loading={loading} />

          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1.1fr)_minmax(0,1fr)]">
            <Card className="min-w-0 lg:col-span-1">
              <CardHeader title="Recent Ingestions" action="View all" href="/construct/library" />
              <RecentIngestions data={data} loading={loading} />
            </Card>

            <Card className="min-w-0 lg:col-span-1">
              <CardHeader title="Knowledge Map" action="View Galaxy" href="/construct/galaxy" />
              {loading ? <Skeleton className="h-[210px]" /> : data && <KnowledgeMap graph={data.knowledge_map} />}
            </Card>

            <div className="flex min-w-0 flex-col gap-4 lg:col-span-1">
              <Card>
                <CardHeader title="Topic Distribution" action="View all" href="/construct/library" />
                <TopicDistribution data={data} loading={loading} />
              </Card>
              <Card>
                <CardHeader title="Ingestion Activity" action="Last 14 days" />
                {loading ? <Skeleton className="h-24" /> : data && <Bars data={data.activity} />}
              </Card>
            </div>
          </div>
        </div>

        <Recollection data={data} loading={loading} />
      </div>
    </div>
  );
}

function DashboardHeading({ firstName, focus }: { firstName: string; focus: string[] }) {
  // Rendered on the client so it matches the reader's own clock and locale.
  const today = useMemo(
    () =>
      new Date().toLocaleDateString(undefined, {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric",
      }),
    [],
  );
  const [scope, setScope] = useState<"Personal" | "Project">("Personal");

  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
          Welcome back, {firstName}
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          Your knowledge. Connected. Discover more.
        </p>
        {focus.length > 0 && (
          <p className="mt-1 text-xs text-ink-subtle">
            <span className="font-medium">Current focus</span> · {focus.join(" · ")}
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden text-xs tabular-nums text-ink-subtle sm:inline">{today}</span>
        {/*
          Projects do not exist in the data model yet, so the Project scope is
          offered but disabled rather than silently showing personal data under
          another name.
        */}
        <div role="group" aria-label="Context" className="flex rounded-lg border border-line bg-surface-subtle p-0.5">
          <button
            type="button"
            onClick={() => setScope("Personal")}
            aria-pressed={scope === "Personal"}
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              scope === "Personal" ? "bg-accent text-accent-ink" : "text-ink-muted",
            )}
          >
            Personal
          </button>
          <button
            type="button"
            aria-disabled="true"
            title="Projects — coming soon"
            className="rounded-md px-3 py-1.5 text-xs font-medium text-ink-subtle"
          >
            Project
          </button>
        </div>
      </div>
    </div>
  );
}

function Metrics({ data, loading }: { data: CerebroDashboard | null; loading: boolean }) {
  const cards = [
    { key: "documents", label: "Documents", tint: "text-accent", bg: "bg-accent-subtle", icon: <DocIcon /> },
    { key: "fragments", label: "Knowledge Fragments", tint: "text-[#14b8a6]", bg: "bg-[#14b8a6]/12", icon: <FragmentIcon /> },
    { key: "topics", label: "Topics", tint: "text-[#8b5cf6]", bg: "bg-[#8b5cf6]/12", icon: <TagIcon /> },
  ] as const;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => {
        const metric = data?.[card.key];
        return (
          <Card key={card.key} className="flex items-center gap-3">
            <span className={cn("grid size-10 shrink-0 place-items-center rounded-lg", card.bg, card.tint)}>
              {card.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-xs leading-tight text-ink-muted">{card.label}</span>
              {loading ? (
                <Skeleton className="mt-1 h-7 w-16" />
              ) : (
                <span className="block text-2xl font-semibold tabular-nums text-ink">
                  {metric ? metric.total.toLocaleString() : 0}
                </span>
              )}
              {!loading && metric !== undefined && metric.new_this_week > 0 && (
                <span className="mt-0.5 block text-xs font-medium text-success">
                  ↑ +{metric.new_this_week.toLocaleString()} this week
                </span>
              )}
            </span>
          </Card>
        );
      })}

      <Card className="flex items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-[#38bdf8]/12 text-[#38bdf8]">
          <StorageIcon />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-xs text-ink-muted">Storage Used</span>
          {loading ? (
            <Skeleton className="mt-1 h-7 w-20" />
          ) : (
            <span className="block text-2xl font-semibold tabular-nums text-ink">
              {formatBytes(data?.storage.bytes ?? 0)}
            </span>
          )}
          {/*
            No quota exists, so no percentage is shown. A bar without a
            denominator would be a number we invented.
          */}
          {!loading && data?.storage.percent === null && (
            <span className="mt-0.5 block text-[0.6875rem] text-ink-subtle">No quota set</span>
          )}
        </span>
      </Card>
    </div>
  );
}

function RecentIngestions({ data, loading }: { data: CerebroDashboard | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-9" />
        ))}
      </div>
    );
  }
  if (!data?.recent.length) {
    return <EmptyState>Nothing ingested yet. Add a document to get started.</EmptyState>;
  }

  return (
    <ul className="flex flex-col">
      {data.recent.map((item) => (
        <li key={item.id}>
          <Link
            href={`/construct/ingest?artifact=${item.id}`}
            className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-surface-subtle"
          >
            <FileBadge modality={item.modality} filename={item.filename} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[0.8125rem] font-medium text-ink">
                {item.filename}
              </span>
              <span className="block truncate text-[0.6875rem] tabular-nums text-ink-subtle">
                {extensionOf(item.filename)} · {formatBytes(item.size_bytes)} ·{" "}
                {new Date(item.created_at).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                })}
              </span>
            </span>
            <StatusChip status={item.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * The status names the reference uses, mapped onto the statuses the ingestion
 * pipeline actually has. No new states are invented: `inspected` is what the
 * API calls an artifact awaiting review, and the chip says so in the
 * reference's language.
 */
const STATUS_LABEL: Record<string, { label: string; tone: string }> = {
  inspected: { label: "Pending Approval", tone: "bg-[#f59e0b]/12 text-[#b45309] dark:text-[#f59e0b]" },
  approved: { label: "Approved", tone: "bg-success/12 text-success" },
  registered: { label: "Registered", tone: "bg-success/12 text-success" },
  rejected: { label: "Rejected", tone: "bg-danger/12 text-danger" },
};

function StatusChip({ status }: { status: string }) {
  const entry = STATUS_LABEL[status] ?? { label: status, tone: "bg-surface-sunken text-ink-muted" };
  return (
    <span className={cn("shrink-0 rounded-md px-1.5 py-0.5 text-[0.625rem] font-medium", entry.tone)}>
      {entry.label}
    </span>
  );
}

function TopicDistribution({ data, loading }: { data: CerebroDashboard | null; loading: boolean }) {
  if (loading) return <Skeleton className="h-[118px]" />;
  const distribution = data?.topic_distribution;
  if (!distribution?.slices.length) {
    return <EmptyState>Topics appear once documents are registered.</EmptyState>;
  }

  return (
    <div className="flex items-center gap-4">
      <Donut slices={distribution.slices} total={distribution.total} label="Topics" />
      <ul className="min-w-0 flex-1 space-y-1.5">
        {distribution.slices.map((slice, i) => (
          <li key={slice.label} className="flex items-center gap-2 text-xs">
            <span
              aria-hidden="true"
              className="size-2 shrink-0 rounded-full"
              style={{ background: sliceColor(i) }}
            />
            <span className="min-w-0 flex-1 truncate text-ink-muted">{slice.label}</span>
            <span className="tabular-nums text-ink">{slice.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Recollection({ data, loading }: { data: CerebroDashboard | null; loading: boolean }) {
  return (
    <Card className="flex h-fit flex-col xl:sticky xl:top-20">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <SparkIcon />
          Assisted Recollection
        </h2>
        <span title="See all — coming soon" className="text-xs font-medium text-ink-subtle">
          See all
        </span>
      </div>

      {loading ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : !data?.recollection.length ? (
        <EmptyState>
          Suggestions are drawn from topics in your registered documents. Register
          one and they will appear here.
        </EmptyState>
      ) : (
        <ul className="flex flex-col">
          {data.recollection.map((item) => (
            <li key={item.topic}>
              <Link
                href={`/construct/library?topic=${encodeURIComponent(item.topic)}`}
                className="-mx-2 flex items-start gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-surface-subtle"
              >
                <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-md bg-surface-sunken text-ink-subtle">
                  <DocIcon />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink">{item.topic}</span>
                  <span className="block text-[0.6875rem] text-ink-muted">
                    Found in {item.document_count} document{item.document_count === 1 ? "" : "s"}
                  </span>
                  {/* Provenance: the documents that actually carry the topic. */}
                  <span className="block truncate text-[0.6875rem] text-ink-subtle">
                    {item.artifacts.map((a) => a.filename).join(", ")}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {/*
        A real search, not a prompt box: it submits to the search page rather
        than calling a model from the dashboard.
      */}
      <form
        action="/construct/search"
        role="search"
        className="mt-3 flex items-center gap-2 rounded-lg border border-line bg-surface-subtle px-3 py-2 focus-within:border-accent"
      >
        <SparkIcon />
        <input
          type="search"
          name="q"
          aria-label="Ask or describe what you're looking for"
          placeholder="Ask or describe what you're looking for..."
          className="w-full bg-transparent text-xs text-ink outline-none placeholder:text-ink-subtle"
        />
      </form>
    </Card>
  );
}

function FileBadge({ modality, filename }: { modality: string; filename: string }) {
  const tone =
    modality === "pdf"
      ? "bg-danger/12 text-danger"
      : modality === "office"
        ? "bg-accent-subtle text-accent"
        : "bg-success/12 text-success";
  return (
    <span className={cn("grid size-9 shrink-0 place-items-center rounded-md text-[0.625rem] font-semibold", tone)}>
      {extensionOf(filename)}
    </span>
  );
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(dot + 1).toUpperCase() : "FILE";
}

/* --- icons, kept local to the dashboard ---------------------------------- */

function Svg({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 20 20" className="size-[18px]" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

const DocIcon = () => (
  <Svg>
    <path d="M5 2.75h6.5L15 6.25v11a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z" />
    <path d="M11.25 2.75v3.5H15M7.5 10.5h5M7.5 13.5h5" />
  </Svg>
);
const FragmentIcon = () => (
  <Svg>
    <circle cx="5.5" cy="10" r="2" /><circle cx="14" cy="5.5" r="2" /><circle cx="14" cy="14.5" r="2" />
    <path d="m7.3 9 4.9-2.6M7.3 11l4.9 2.6" />
  </Svg>
);
const TagIcon = () => (
  <Svg>
    <path d="M10.5 3.5H16a.5.5 0 0 1 .5.5v5.5L9 17 3 11z" /><circle cx="13" cy="7" r="1" />
  </Svg>
);
const StorageIcon = () => (
  <Svg>
    <ellipse cx="10" cy="5.5" rx="6" ry="2.5" /><path d="M4 5.5v9c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-9" />
    <path d="M4 10c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5" />
  </Svg>
);
const SparkIcon = () => (
  <svg viewBox="0 0 20 20" className="size-4 shrink-0 text-accent" fill="currentColor" aria-hidden="true">
    <path d="M10 2.5l1.6 4.4 4.4 1.6-4.4 1.6L10 14.5 8.4 10.1 4 8.5l4.4-1.6z" />
  </svg>
);
