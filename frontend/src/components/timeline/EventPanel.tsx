"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { LANE_COLOR, describeLocation, formatEventDate } from "@/components/timeline/lanes";
import { api } from "@/lib/api";
import type { CerebroTimelineEventDetail } from "@/lib/api";
import { cn } from "@/lib/cn";

type Tab = "Overview" | "Related" | "Sources";

/**
 * What a selected event is, where it came from, and what it connects to.
 *
 * Every field here resolves to something real: the date is the one the
 * document states, the evidence is the sentence it was read from, and the
 * related entries say what they share rather than asserting a relationship.
 */
export function EventPanel({
  event,
  onClose,
  onClear,
  onSelect,
}: {
  event: CerebroTimelineEventDetail | null;
  onClose: () => void;
  onClear: () => void;
  onSelect: (event: CerebroTimelineEventDetail) => void;
}) {
  const [tab, setTab] = useState<Tab>("Overview");
  const [related, setRelated] = useState<CerebroTimelineEventDetail[]>([]);

  useEffect(() => {
    if (!event) return;
    let live = true;
    void api
      .timelineRelated(event.id)
      .then((body) => live && setRelated(body.related))
      .catch(() => live && setRelated([]));
    return () => {
      live = false;
    };
  }, [event]);

  if (!event) {
    return (
      <aside className="hidden w-[19rem] shrink-0 flex-col rounded-xl border border-white/10 bg-[#0b111c] p-4 text-xs text-white/50 xl:flex">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-white/80">Event details</span>
          <button type="button" onClick={onClose} aria-label="Hide event details" className="text-white/40">
            ✕
          </button>
        </div>
        <p className="mt-3">Select an event to see its evidence, its source and what it relates to.</p>
      </aside>
    );
  }

  const color = LANE_COLOR[event.category] ?? LANE_COLOR.Other;
  const location = describeLocation(event.source_location);

  return (
    <aside
      data-testid="event-panel"
      className="flex w-[19rem] shrink-0 flex-col overflow-hidden rounded-xl border border-white/10 bg-[#0b111c]"
    >
      <header className="flex items-start gap-2 border-b border-white/10 p-3">
        <span className="mt-1.5 size-2.5 shrink-0 rounded-full" style={{ background: color }} />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-white">{event.title}</h2>
          <p className="text-[0.7rem] text-white/50">
            {event.event_type} · {formatEventDate(event)}
          </p>
        </div>
        <button type="button" onClick={onClear} aria-label="Clear selection" className="text-white/40">
          ✕
        </button>
      </header>

      <div className="flex shrink-0 border-b border-white/10 text-[0.7rem]">
        {(["Overview", "Related", "Sources"] as const).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            aria-pressed={tab === name}
            className={cn(
              "flex-1 px-2 py-2 transition-colors",
              tab === name ? "border-b-2 border-sky-400 text-white" : "text-white/45 hover:text-white/70",
            )}
          >
            {name}
            {name === "Related" && related.length > 0 ? ` (${related.length})` : ""}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3 text-xs">
        {tab === "Overview" && (
          <dl className="flex flex-col gap-2">
            <Field label="Category">
              <span style={{ color }}>{event.category}</span>
              {event.category_basis && (
                <span className="text-white/35"> · matched “{event.category_basis}”</span>
              )}
            </Field>
            <Field label="Type">{event.event_type}</Field>
            <Field label="Date">
              {formatEventDate(event)}
              <span className="text-white/35"> · {event.precision} precision</span>
            </Field>
            <Field label="Stated as">“{event.expression}”</Field>
            <Field label="Source">{event.filename}</Field>
            {event.author && <Field label="Author">{event.author}</Field>}
            <Field label="Status">{event.approval_status}</Field>
            <Field label="Method">{event.extraction_method}</Field>
            {Object.entries(event.entities).map(([field, values]) => (
              <Field key={field} label={field}>{values.join(", ")}</Field>
            ))}
          </dl>
        )}

        {tab === "Related" && (
          <ul className="flex flex-col gap-2">
            {related.length === 0 && <li className="text-white/45">Nothing shares an entity or a source with this event.</li>}
            {related.map((other) => (
              <li key={other.id}>
                <button
                  type="button"
                  onClick={() => onSelect(other)}
                  className="w-full rounded-md border border-white/10 p-2 text-left transition-colors hover:border-white/25"
                >
                  <span className="block truncate font-medium text-white">{other.title}</span>
                  <span className="block text-[0.65rem] text-white/45">
                    {formatEventDate(other)} · {other.category}
                  </span>
                  {/* Why, not an assertion that they are connected. */}
                  <span className="mt-0.5 block text-[0.65rem] text-sky-300/80">{other.relationship}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {tab === "Sources" && (
          <div className="flex flex-col gap-3">
            <div>
              <p className="text-white/45">Supporting evidence</p>
              <p className="mt-1 rounded-md border border-white/10 bg-white/[0.04] p-2 leading-relaxed text-white/80">
                “{event.evidence}”
              </p>
            </div>
            <Field label="Document">{event.filename}</Field>
            {location && <Field label="Location">{location}</Field>}
            <div className="flex flex-wrap gap-2 pt-1">
              <a
                href={api.artifactContentUrl(event.artifact_id)}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-white/15 px-2 py-1 text-sky-300"
              >
                Open original
              </a>
              <Link
                href={`/construct/ingest?artifact=${event.artifact_id}`}
                className="rounded-md border border-white/15 px-2 py-1 text-white/70"
              >
                Open in Library
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* The contextual Galaxy: this event and what it shares something with,
          drawn from the same related set rather than the whole graph. */}
      {related.length > 0 && (
        <div className="shrink-0 border-t border-white/10 p-3">
          <div className="flex items-center justify-between text-[0.7rem]">
            <span className="text-white/45">Galaxy view</span>
            <Link href="/construct/galaxy" className="text-sky-300">Open in Galaxy</Link>
          </div>
          <svg viewBox="0 0 200 110" className="mt-1 w-full" role="img" aria-label="Related knowledge">
            {related.slice(0, 5).map((other, index) => {
              const angle = (index / Math.min(5, related.length)) * Math.PI * 2;
              const x = 100 + Math.cos(angle) * 62;
              const y = 55 + Math.sin(angle) * 36;
              return (
                <g key={other.id}>
                  <line x1="100" y1="55" x2={x} y2={y} stroke="rgba(255,255,255,0.18)" />
                  <circle cx={x} cy={y} r="5" fill={LANE_COLOR[other.category] ?? LANE_COLOR.Other}>
                    <title>{other.title}</title>
                  </circle>
                </g>
              );
            })}
            <circle cx="100" cy="55" r="9" fill={color} />
            <text x="100" y="78" textAnchor="middle" className="fill-white/60" fontSize="7">
              {event.title.slice(0, 26)}
            </text>
          </svg>
        </div>
      )}
    </aside>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <dt className="w-20 shrink-0 capitalize text-white/40">{label}</dt>
      <dd className="min-w-0 flex-1 text-white/80">{children}</dd>
    </div>
  );
}
