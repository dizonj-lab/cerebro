"use client";

import { useRef } from "react";

/**
 * The temporal overview: event density, and the window into it.
 *
 * Bars are counts of real events per month — the histogram comes from the
 * whole library rather than the filtered slice, so narrowing a filter does
 * not make the navigator forget the shape of the knowledge.
 *
 * The selector is draggable by its body and by each edge, and a click
 * anywhere jumps the window there, keeping its span.
 */
export function Navigator({
  histogram,
  window: window_,
  range,
  onChange,
}: {
  histogram: { month: string; count: number }[];
  window: { from: number; to: number };
  range: { earliest: string | null; latest: string | null };
  onChange: (next: { from: number; to: number }) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const busiest = Math.max(1, ...histogram.map((bucket) => bucket.count));

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
    <div className="shrink-0 border-t border-white/10 px-3 py-2" data-testid="timeline-navigator">
      <div
        ref={track}
        onPointerDown={(event) => {
          // A click on the track centres the window there, keeping its span.
          const middle = at(event.clientX);
          const half = (window_.to - window_.from) / 2;
          onChange({ from: middle - half, to: middle + half });
        }}
        className="relative flex h-14 items-end gap-px overflow-hidden rounded-md bg-white/[0.03]"
      >
        {histogram.map((bucket) => (
          <span
            key={bucket.month}
            title={`${bucket.month}: ${bucket.count}`}
            style={{ height: `${Math.max(8, (bucket.count / busiest) * 100)}%` }}
            className="min-w-[3px] flex-1 rounded-sm bg-sky-400/40"
          />
        ))}

        <div
          onPointerDown={(event) => begin(event, "move")}
          data-testid="navigator-window"
          style={{ left: `${left}%`, width: `${Math.max(width, 2)}%` }}
          className="absolute inset-y-0 cursor-grab rounded-md border border-sky-300/70 bg-sky-300/10 active:cursor-grabbing"
        >
          <span
            onPointerDown={(event) => begin(event, "start")}
            role="slider"
            tabIndex={0}
            aria-label="Window start"
            aria-valuenow={Math.round(left)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="absolute -left-1 bottom-0 top-0 w-2 cursor-ew-resize rounded-full bg-sky-200/80"
          />
          <span
            onPointerDown={(event) => begin(event, "end")}
            role="slider"
            tabIndex={0}
            aria-label="Window end"
            aria-valuenow={Math.round(left + width)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="absolute -right-1 bottom-0 top-0 w-2 cursor-ew-resize rounded-full bg-sky-200/80"
          />
        </div>
      </div>

      <div className="mt-1 flex justify-between text-[0.65rem] text-white/40">
        <span>{range.earliest ?? "—"}</span>
        <span>{range.latest ?? "—"}</span>
      </div>
    </div>
  );
}
