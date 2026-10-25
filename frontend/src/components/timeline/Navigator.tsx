"use client";

import { useRef } from "react";

/**
 * The temporal overview: how much knowledge sits where, and the window into it.
 *
 * A bar's height is **volume** — pages of document, not a count of dates. A
 * month holding one eighty-page thesis and a month holding one two-page memo
 * are not the same amount of knowledge, and a bar that counts events claims
 * they are. Each document counts once per month however many dates it names,
 * so a date-dense document cannot inflate its own size. Where a format
 * reports no page count the floor is one page: presence, not a guess at
 * length.
 *
 * A bar is stacked by category, in the lanes' own colours, so the shape of
 * the library reads by subject at a glance. It replaced a single flat blue,
 * which said only "something happened here".
 *
 * The histogram comes from the whole library rather than the filtered slice,
 * so narrowing a filter does not make the navigator forget the shape of the
 * knowledge.
 *
 * The selector is draggable by its body and by each edge, and a click
 * anywhere jumps the window there, keeping its span.
 */
export function Navigator({
  histogram,
  window: window_,
  range,
  laneColor,
  onChange,
}: {
  histogram: {
    month: string;
    count: number;
    pages: number;
    documents: number;
    by_category: Record<string, number>;
  }[];
  window: { from: number; to: number };
  range: { earliest: string | null; latest: string | null };
  /** The lanes' own colours, so a bar segment matches its lane. */
  laneColor: (category: string) => string;
  onChange: (next: { from: number; to: number }) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const fullest = Math.max(1, ...histogram.map((bucket) => bucket.pages));

  const first = histogram[0]?.month;
  const last = histogram[histogram.length - 1]?.month;
  const from = first ? new Date(`${first}-01T00:00:00`).getTime() : window_.from;
  const to = last ? new Date(`${last}-01T00:00:00`).getTime() : window_.to;
  const span = Math.max(to - from, 1);

  const left = ((window_.from - from) / span) * 100;
  const width = ((window_.to - window_.from) / span) * 100;

  function at(clientX: number): number {
    const box = track.current?.getBoundingClientRect();
    if (!box) return window_.from;
    return from + ((clientX - box.left) / box.width) * span;
  }

  function begin(event: React.PointerEvent, mode: "move" | "start" | "end") {
    event.preventDefault();
    event.stopPropagation();
    const origin = at(event.clientX);
    const starting = { ...window_ };

    const move = (e: PointerEvent) => {
      const shift = at(e.clientX) - origin;
      if (mode === "move") {
        onChange({ from: starting.from + shift, to: starting.to + shift });
      } else if (mode === "start") {
        // An edge may not cross the other one, or the window inverts.
        const next = Math.min(starting.from + shift, starting.to - span / 50);
        onChange({ from: next, to: starting.to });
      } else {
        const next = Math.max(starting.to + shift, starting.from + span / 50);
        onChange({ from: starting.from, to: next });
      }
    };
    const stop = () => {
      globalThis.removeEventListener("pointermove", move);
      globalThis.removeEventListener("pointerup", stop);
    };
    globalThis.addEventListener("pointermove", move);
    globalThis.addEventListener("pointerup", stop);
  }

  return (
    <div className="shrink-0 border-t border-scene-ink/10 px-3 py-2" data-testid="timeline-navigator">
      <div
        ref={track}
        onPointerDown={(event) => {
          // A click on the track centres the window there, keeping its span.
          const middle = at(event.clientX);
          const half = (window_.to - window_.from) / 2;
          onChange({ from: middle - half, to: middle + half });
        }}
        className="relative flex h-14 items-end gap-px overflow-hidden rounded-md bg-scene-ink/[0.03]"
      >
        {histogram.map((bucket) => {
          // Largest category at the base, so the stack does not reshuffle
          // between neighbouring months and the eye can follow one band.
          const segments = Object.entries(bucket.by_category).sort((a, b) => b[1] - a[1]);
          return (
            <span
              key={bucket.month}
              title={
                `${bucket.month}: ${bucket.pages} page${bucket.pages === 1 ? "" : "s"} · ` +
                `${bucket.documents} document${bucket.documents === 1 ? "" : "s"}` +
                (segments.length
                  ? ` · ${segments.map(([name, pages]) => `${name} ${pages}`).join(", ")}`
                  : "")
              }
              data-testid={`volume-${bucket.month}`}
              data-pages={bucket.pages}
              style={{ height: `${Math.max(8, (bucket.pages / fullest) * 100)}%` }}
              className="flex min-w-[3px] flex-1 flex-col-reverse overflow-hidden rounded-sm"
            >
              {segments.length ? (
                segments.map(([category, pages]) => (
                  <span
                    key={category}
                    style={{
                      flexGrow: pages,
                      background: laneColor(category),
                      opacity: 0.75,
                    }}
                    className="w-full first:rounded-t-sm"
                  />
                ))
              ) : (
                // A month with events but no category still has presence.
                <span className="size-full rounded-sm bg-scene-ink/15" />
              )}
            </span>
          );
        })}

        <div
          onPointerDown={(event) => begin(event, "move")}
          data-testid="navigator-window"
          style={{ left: `${left}%`, width: `${Math.max(width, 2)}%` }}
          className="absolute inset-y-0 cursor-grab rounded-md border border-scene-ink/60 bg-scene-ink/10 active:cursor-grabbing"
        >
          <span
            onPointerDown={(event) => begin(event, "start")}
            role="slider"
            tabIndex={0}
            aria-label="Window start"
            aria-valuenow={Math.round(left)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="absolute -left-1 bottom-0 top-0 w-2 cursor-ew-resize rounded-full bg-scene-ink/80"
          />
          <span
            onPointerDown={(event) => begin(event, "end")}
            role="slider"
            tabIndex={0}
            aria-label="Window end"
            aria-valuenow={Math.round(left + width)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="absolute -right-1 bottom-0 top-0 w-2 cursor-ew-resize rounded-full bg-scene-ink/80"
          />
        </div>
      </div>

      <div className="mt-1 flex items-baseline justify-between text-[0.65rem] text-scene-ink/40">
        <span>{range.earliest ?? "—"}</span>
        {/* Said once, because a bar's height is not the obvious quantity. */}
        <span className="text-scene-ink/30">Height is pages of document</span>
        <span>{range.latest ?? "—"}</span>
      </div>
    </div>
  );
}
