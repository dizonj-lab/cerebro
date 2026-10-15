"use client";

import { useMemo } from "react";

import { colorFor } from "@/components/galaxy/palette";
import type { CerebroTimelineEvent } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * The Knowledge Timeline.
 *
 * Events are registered artifacts placed at the date the document states, or
 * the date it was registered when it states none. Which of the two is always
 * shown — an inferred date would be a fabricated fact.
 */
export function KnowledgeTimeline({
  events,
  selectedTopic,
  selectedArtifactId,
  onSelect,
}: {
  events: CerebroTimelineEvent[];
  /** Highlights events carrying the topic selected in the Galaxy. */
  selectedTopic: string | null;
  selectedArtifactId: string | null;
  onSelect: (event: CerebroTimelineEvent) => void;
}) {
  const { placed, years } = useMemo(() => {
    if (!events.length) return { placed: [], years: [] as string[] };
    const times = events.map((e) => new Date(e.date).getTime());
    const min = Math.min(...times);
    const max = Math.max(...times);
    const span = Math.max(1, max - min);
    return {
      placed: events.map((event, i) => ({
        event,
        // A single-date collection would otherwise stack on one point.
        percent: max === min ? ((i + 1) / (events.length + 1)) * 100 : ((times[i] - min) / span) * 100,
      })),
      years: [...new Set(events.map((e) => e.date.slice(0, 4)))].sort(),
    };
  }, [events]);

  if (!events.length) {
    return (
      <div className="rounded-xl border border-white/10 bg-[#101725] p-6 text-center">
        <p className="text-sm text-white/60">
          Your timeline fills as you register documents. Dates come from the document
          itself where it states one.
        </p>
      </div>
    );
  }

  return (
    <section className="rounded-xl border border-white/10 bg-[#101725] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-white">Knowledge Timeline</h2>
          <p className="text-[0.6875rem] text-white/50">Your knowledge journey over time</p>
        </div>
        <p className="text-[0.625rem] text-white/40">
          Dates are stated by the document, or the date it was registered.
        </p>
      </div>

      <div className="relative mt-5 h-16">
        {/* The gradient band is the time axis itself, coloured by the
            categories actually present. */}
        <div
          className="absolute inset-x-0 bottom-5 h-1 rounded-full opacity-80"
          style={{ background: gradientOf(events) }}
        />
        <div className="absolute inset-x-0 bottom-0 flex justify-between text-[0.625rem] tabular-nums text-white/40">
          {years.map((year) => (
            <span key={year}>{year}</span>
          ))}
        </div>
        {placed.map(({ event, percent }) => {
          const active =
            event.artifact_id === selectedArtifactId ||
            (selectedTopic !== null && event.topics.includes(selectedTopic));
          const color = colorFor(event.category);
          return (
            <button
              key={event.id}
              type="button"
              onClick={() => onSelect(event)}
              title={`${event.title} — ${event.date}`}
              aria-label={`${event.title}, ${event.date}`}
              className="absolute bottom-[1.1rem] -translate-x-1/2 rounded-full transition-transform hover:scale-150 focus-visible:scale-150 focus-visible:outline-none"
              style={{
                left: `${percent}%`,
                width: active ? 14 : 9,
                height: active ? 14 : 9,
                background: color,
                boxShadow: active ? `0 0 14px ${color}` : `0 0 6px ${color}80`,
              }}
            />
          );
        })}
      </div>

      <ul className="mt-4 flex gap-3 overflow-x-auto pb-1">
        {events.map((event) => {
          const active =
            event.artifact_id === selectedArtifactId ||
            (selectedTopic !== null && event.topics.includes(selectedTopic));
          return (
            <li key={`card-${event.id}`} className="shrink-0">
              <button
                type="button"
                onClick={() => onSelect(event)}
                className={cn(
                  "flex w-52 items-start gap-2.5 rounded-lg border p-2.5 text-left transition-colors",
                  active
                    ? "border-white/35 bg-white/10"
                    : "border-white/10 hover:border-white/20 hover:bg-white/5",
                )}
              >
                <span
                  className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md text-[0.5625rem] font-semibold text-black/80"
                  style={{ background: colorFor(event.category) }}
                >
                  {event.modality.slice(0, 3).toUpperCase()}
                </span>
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

function gradientOf(events: CerebroTimelineEvent[]): string {
  const categories = [...new Set(events.map((e) => e.category))].slice(0, 6);
  if (categories.length === 1) return colorFor(categories[0]);
  const stops = categories.map(
    (category, i) => `${colorFor(category)} ${(i / (categories.length - 1)) * 100}%`,
  );
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}
