"use client";

import { useMemo, useState } from "react";

import { colorFor } from "@/components/galaxy/palette";
import type { CerebroTimelineEvent } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * The Knowledge Timeline.
 *
 * Events are registered artifacts placed at the date the document states, or
 * the date it was registered when it states none. Which of the two is always
 * shown — an inferred date would be a fabricated fact.
 *
 * The axis has two levels: years as milestones, months beneath them. A month
 * carries the count of artifacts that fall in it, so a dense period reads as
 * dense rather than as a pile of overlapping dots.
 */
export function KnowledgeTimeline({
  events,
  selectedTopic,
  selectedArtifactId,
  onSelect,
  collapsed = false,
  onToggleCollapsed,
}: {
  events: CerebroTimelineEvent[];
  selectedTopic: string | null;
  selectedArtifactId: string | null;
  onSelect: (event: CerebroTimelineEvent) => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}) {
  const [focusedMonth, setFocusedMonth] = useState<string | null>(null);

  const { months, years, total } = useMemo(() => groupByMonth(events), [events]);

  if (!events.length) {
    return (
      <section className="bg-[#101725] px-4 py-5 text-center">
        <p className="text-sm text-white/60">
          Your timeline fills as you register documents. Dates come from the document
          itself where it states one.
        </p>
      </section>
    );
  }

  // Focusing a month filters the cards below without hiding the axis, so the
  // shape of the whole collection stays visible while reading one part of it.
  const shown = focusedMonth
    ? months.find((m) => m.key === focusedMonth)?.events ?? events
    : events;

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#101725]">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5">
        <div className="flex items-baseline gap-2">
          <h2 className="text-xs font-semibold text-white">Knowledge Timeline</h2>
          <span className="text-[0.625rem] text-white/45">
            {total} document{total === 1 ? "" : "s"} · {years.length} year
            {years.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {focusedMonth && (
            <button
              type="button"
              onClick={() => setFocusedMonth(null)}
              className="rounded border border-white/15 px-1.5 py-0.5 text-[0.625rem] font-medium text-white/70 transition-colors hover:text-white"
            >
              Show all
            </button>
          )}
          <span className="hidden text-[0.625rem] text-white/35 lg:inline">
            Dates stated by the document, or when registered.
          </span>
          {onToggleCollapsed && (
            <button
              type="button"
              onClick={onToggleCollapsed}
              aria-expanded={!collapsed}
              aria-label={collapsed ? "Expand timeline" : "Collapse timeline"}
              className="rounded p-1 text-white/55 transition-colors hover:bg-white/10 hover:text-white"
            >
              <svg viewBox="0 0 20 20" className={cn("size-4 transition-transform", collapsed && "rotate-180")} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path d="M5.5 12 10 7.5l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {collapsed ? null : (
      <>

      {/* --- axis: years, then months. Stretched to the full width, each
              year taking room in proportion to the months it holds. ------- */}
      <div className="flex items-stretch gap-3 px-3">
        {years.map((year) => (
            <div
              key={year.year}
              className="min-w-0"
              // A year takes room in proportion to the months it holds, so a
              // long year is wider than a short one.
              style={{ flex: `${year.months.length} 0 auto` }}
            >
              <div className="flex items-baseline gap-1.5 border-b border-white/10 pb-0.5">
                <span className="text-[0.6875rem] font-semibold tabular-nums text-white">
                  {year.year}
                </span>
                <span className="truncate text-[0.5625rem] text-white/40">
                  {year.count} doc{year.count === 1 ? "" : "s"}
                </span>
              </div>

              <div className="mt-1 flex items-end gap-px">
                {year.months.map((month) => {
                  const active = focusedMonth === month.key;
                  const empty = month.events.length === 0;
                  const related =
                    selectedTopic !== null &&
                    month.events.some((e) => e.topics.includes(selectedTopic));
                  return (
                    <button
                      key={month.key}
                      type="button"
                      disabled={empty}
                      onClick={() => setFocusedMonth(active ? null : month.key)}
                      aria-pressed={active}
                      // The visible text is a bare number and a short month,
                      // which says nothing on its own to a screen reader.
                      aria-label={`${month.label}, ${month.events.length} document${
                        month.events.length === 1 ? "" : "s"
                      }`}
                      title={`${month.label} — ${month.events.length} document${
                        month.events.length === 1 ? "" : "s"
                      }`}
                      className={cn(
                        // Capped so a year with one month does not become a
                        // single bar the width of the screen.
                        "flex min-w-0 max-w-10 flex-1 flex-col items-center gap-0.5 rounded-sm py-0.5 transition-colors",
                        active ? "bg-white/15" : !empty && "hover:bg-white/8",
                        empty && "cursor-default",
                      )}
                    >
                      {/* Height carries the month's volume; the number states
                          it outright, because a bar alone is a guess. An empty
                          month keeps its place as a flat tick. */}
                      <span
                        className="w-full rounded-[1px]"
                        style={{
                          height: empty ? 2 : 4 + (month.events.length / year.peak) * 18,
                          background: empty
                            ? "rgba(255,255,255,0.12)"
                            : colorFor(month.events[0].category),
                          opacity: empty || related || active ? 1 : 0.6,
                        }}
                      />
                      <span className="text-[0.5rem] tabular-nums text-white/55">
                        {empty ? "" : month.events.length}
                      </span>
                      <span className="truncate text-[0.5rem] text-white/35">
                        {month.short.slice(0, 1)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
      </div>

      {/* --- cards: a preview of each document --------------------------- */}
      <ul className="mt-1.5 flex min-h-0 flex-1 gap-2 overflow-x-auto px-3 pb-2">
        {shown.map((event) => {
          const active =
            event.artifact_id === selectedArtifactId ||
            (selectedTopic !== null && event.topics.includes(selectedTopic));
          return (
            <li key={`card-${event.id}`} className="shrink-0">
              <button
                type="button"
                onClick={() => onSelect(event)}
                className={cn(
                  "flex h-full w-44 flex-col gap-1.5 rounded-md border p-1.5 text-left transition-colors",
                  active
                    ? "border-white/35 bg-white/10"
                    : "border-white/10 hover:border-white/20 hover:bg-white/5",
                )}
              >
                <DocumentPreview event={event} />
                <span className="min-w-0">
                  <span className="block text-[0.625rem] tabular-nums text-white/50">
                    {event.date}
                    {event.basis === "registered_at" && " · registered"}
                  </span>
                  <span className="block truncate text-[0.8125rem] font-medium text-white">
                    {event.title}
                  </span>
                  <span className="block truncate text-[0.6875rem] text-white/50">
                    {event.category}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      </>
      )}
    </section>
  );
}

/**
 * A miniature of the document.
 *
 * The text is the document's own opening, set small on a page-like surface —
 * a real preview rather than a generated thumbnail. Documents with no
 * extracted text yet get the page without the words.
 */
function DocumentPreview({ event }: { event: CerebroTimelineEvent }) {
  const tint = colorFor(event.category);
  return (
    <span
      aria-hidden="true"
      className="relative block min-h-0 flex-1 overflow-hidden rounded-sm border border-white/10 bg-white/95 p-1.5"
    >
      <span
        className="absolute inset-x-0 top-0 h-1"
        style={{ background: tint }}
      />
      {event.preview ? (
        <span className="mt-0.5 block text-[0.4rem] leading-[1.4] text-slate-700">
          {event.preview}
        </span>
      ) : (
        <span className="mt-2 block space-y-1">
          {[90, 75, 85, 60].map((width) => (
            <span key={width} className="block h-1 rounded-full bg-slate-200" style={{ width: `${width}%` }} />
          ))}
        </span>
      )}
      <span
        className="absolute bottom-1 right-1 rounded px-1 py-0.5 text-[0.5rem] font-semibold text-white"
        style={{ background: tint }}
      >
        {extensionOf(event.filename)}
      </span>
    </span>
  );
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(dot + 1).toUpperCase() : "FILE";
}

interface Month {
  key: string;
  label: string;
  short: string;
  events: CerebroTimelineEvent[];
}

interface Year {
  year: string;
  count: number;
  peak: number;
  months: Month[];
}

/**
 * Groups events by month, and months by year.
 *
 * Every month between the first and the last appears, including empty ones:
 * a gap in the record is itself information, and skipping quiet months makes
 * a sparse year look as busy as a dense one.
 */
function monthsBetween(first: string, last: string): string[] {
  const out: string[] = [];
  const cursor = new Date(`${first}-01T00:00:00`);
  const end = new Date(`${last}-01T00:00:00`);
  while (cursor <= end) {
    out.push(`${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`);
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return out;
}

function groupByMonth(events: CerebroTimelineEvent[]): {
  months: Month[];
  years: Year[];
  total: number;
} {
  const buckets = new Map<string, CerebroTimelineEvent[]>();
  for (const event of events) {
    const key = event.date.slice(0, 7);
    buckets.set(key, [...(buckets.get(key) ?? []), event]);
  }

  const keys = [...buckets.keys()].sort();
  const months: Month[] = monthsBetween(keys[0], keys[keys.length - 1]).map((key) => {
    const date = new Date(`${key}-01T00:00:00`);
    return {
      key,
      label: date.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
      short: date.toLocaleDateString(undefined, { month: "short" }),
      events: buckets.get(key) ?? [],
    };
  });

  const byYear = new Map<string, Month[]>();
  for (const month of months) {
    const year = month.key.slice(0, 4);
    byYear.set(year, [...(byYear.get(year) ?? []), month]);
  }

  const years: Year[] = [...byYear.entries()].map(([year, list]) => ({
    year,
    count: list.reduce((n, m) => n + m.events.length, 0),
    peak: Math.max(1, ...list.map((m) => m.events.length)),
    months: list,
  }));

  return { months, years, total: events.length };
}
