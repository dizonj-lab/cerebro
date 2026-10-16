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
}: {
  events: CerebroTimelineEvent[];
  selectedTopic: string | null;
  selectedArtifactId: string | null;
  onSelect: (event: CerebroTimelineEvent) => void;
}) {
  const [focusedMonth, setFocusedMonth] = useState<string | null>(null);

  const { months, years, total } = useMemo(() => groupByMonth(events), [events]);

  if (!events.length) {
    return (
      <section className="rounded-xl border border-white/10 bg-[#101725] p-6 text-center">
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
    <section className="rounded-xl border border-white/10 bg-[#101725] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-white">Knowledge Timeline</h2>
          <p className="text-[0.6875rem] text-white/50">
            {total} document{total === 1 ? "" : "s"} over {years.length} year
            {years.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {focusedMonth && (
            <button
              type="button"
              onClick={() => setFocusedMonth(null)}
              className="rounded-md border border-white/15 px-2 py-1 text-[0.625rem] font-medium text-white/70 transition-colors hover:text-white"
            >
              Show all
            </button>
          )}
          <p className="text-[0.625rem] text-white/40">
            Dates are stated by the document, or the date it was registered.
          </p>
        </div>
      </div>

      {/* --- axis: years, then months ----------------------------------- */}
      <div className="mt-4 overflow-x-auto pb-1">
        <div className="flex min-w-fit gap-6">
          {years.map((year) => (
            <div key={year.year} className="min-w-fit">
              <div className="flex items-baseline gap-2 border-b border-white/10 pb-1">
                <span className="text-sm font-semibold tabular-nums text-white">{year.year}</span>
                <span className="text-[0.625rem] text-white/40">
                  {year.count} document{year.count === 1 ? "" : "s"}
                </span>
              </div>

              <div className="mt-2 flex items-end gap-1.5">
                {year.months.map((month) => {
                  const active = focusedMonth === month.key;
                  const related =
                    selectedTopic !== null &&
                    month.events.some((e) => e.topics.includes(selectedTopic));
                  return (
                    <button
                      key={month.key}
                      type="button"
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
                        "flex w-9 flex-col items-center gap-1 rounded-md px-0.5 py-1 transition-colors",
                        active ? "bg-white/15" : "hover:bg-white/8",
                      )}
                    >
                      {/* Height carries the month's volume; the number states
                          it outright, because a bar alone is a guess. */}
                      <span
                        className="w-full rounded-sm"
                        style={{
                          height: `${8 + (month.events.length / year.peak) * 26}px`,
                          background: colorFor(month.events[0].category),
                          opacity: related || active ? 1 : 0.55,
                        }}
                      />
                      <span className="text-[0.5625rem] tabular-nums text-white/70">
                        {month.events.length}
                      </span>
                      <span className="text-[0.5625rem] text-white/40">{month.short}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* --- cards: a preview of each document --------------------------- */}
      <ul className="mt-4 flex gap-3 overflow-x-auto pb-1">
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
                  "flex w-60 flex-col gap-2 rounded-lg border p-2.5 text-left transition-colors",
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
      className="relative block h-20 overflow-hidden rounded-md border border-white/10 bg-white/95 p-2"
    >
      <span
        className="absolute inset-x-0 top-0 h-1"
        style={{ background: tint }}
      />
      {event.preview ? (
        <span className="mt-1 block text-[0.4375rem] leading-[1.45] text-slate-700">
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

/** Groups events by month, and months by year. Only months with events appear. */
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

  const months: Month[] = [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, list]) => {
      const date = new Date(`${key}-01T00:00:00`);
      return {
        key,
        label: date.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
        short: date.toLocaleDateString(undefined, { month: "short" }),
        events: list,
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
