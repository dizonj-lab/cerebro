"use client";

import { useRef } from "react";

import { dateMs } from "@/components/timeline/lanes";

const YEAR = 365.25 * 24 * 60 * 60 * 1000;

/**
 * The overview: where the events are, and which part of that is on screen.
 *
 * One bar per year — per month when the whole library spans less than eight
 * years — whose height is the number of events in it. It used to be pages of
 * document, stacked in lane colours, which needed a caption to explain and
 * repeated the lanes' legend. Counting events answers the one question the
 * strip is for: where is there something to look at.
 *
 * The histogram comes from the whole library rather than the filtered slice,
 * so narrowing a filter does not make the overview forget the shape of the
 * knowledge.
 *
 * The box is the visible window. Drag it, or either edge; a click anywhere
 * else moves it there, keeping its span.
 */
export function Navigator({
  histogram,
  window: window_,
  onChange,
}: {
  histogram: { month: string; count: number }[];
  window: { from: number; to: number };
  onChange: (next: { from: number; to: number }) => void;
}) {
  const track = useRef<HTMLDivElement>(null);

  const first = histogram[0]?.month;
  const last = histogram[histogram.length - 1]?.month;
  const startYear = first ? Number(first.slice(0, 4)) : 0;
  const endYear = last ? Number(last.slice(0, 4)) : 0;
  // Yearly bars only once there are enough years to make a shape; below
  // that, a handful of wide blocks says less than monthly bars do.
  const yearly = endYear - startYear >= 8;

  // Buckets cover whole periods, so the strip starts at the first period's
  // start and ends at the last one's end.
  const buckets: { key: string; label: string; from: number; to: number; count: number }[] = [];
  if (first && last) {
    const counts = new Map<string, number>();
    for (const bucket of histogram) {
      const key = yearly ? bucket.month.slice(0, 4) : bucket.month;
      counts.set(key, (counts.get(key) ?? 0) + bucket.count);
    }
    if (yearly) {
      for (let year = startYear; year <= endYear; year++) {
        buckets.push({
          key: String(year),
          label: String(year),
          from: Date.UTC(year, 0, 1),
          to: Date.UTC(year + 1, 0, 1),
          count: counts.get(String(year)) ?? 0,
        });
      }
    } else {
      const cursor = new Date(dateMs(`${first}-01`));
      const end = dateMs(`${last}-01`);
      while (cursor.getTime() <= end) {
        const key = cursor.toISOString().slice(0, 7);
        const next = Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 1);
        buckets.push({
          key,
          label: cursor.toLocaleDateString(undefined, { month: "short", year: "numeric", timeZone: "UTC" }),
          from: cursor.getTime(),
          to: next,
          count: counts.get(key) ?? 0,
        });
        cursor.setTime(next);
      }
    }
  }

  const from = buckets[0]?.from ?? window_.from;
  const to = buckets[buckets.length - 1]?.to ?? window_.to;
  const span = Math.max(to - from, 1);
  const fullest = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const unit = yearly ? "year" : "month";

  const left = ((window_.from - from) / span) * 100;
  const width = ((window_.to - window_.from) / span) * 100;
  // The box is drawn within the strip even when the window runs past the
  // library's ends, so it is always there to grab.
  const boxLeft = Math.min(Math.max(left, 0), 98);
  const boxWidth = Math.max(2, Math.min(left + width, 100) - boxLeft);

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
    const narrowest = YEAR / 12;

    const move = (e: PointerEvent) => {
      const shift = at(e.clientX) - origin;
      if (mode === "move") {
        onChange({ from: starting.from + shift, to: starting.to + shift });
      } else if (mode === "start") {
        // An edge may not cross the other one, or the window inverts.
        onChange({ from: Math.min(starting.from + shift, starting.to - narrowest), to: starting.to });
      } else {
        onChange({ from: starting.from, to: Math.max(starting.to + shift, starting.from + narrowest) });
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
          const middle = at(event.clientX);
          const half = (window_.to - window_.from) / 2;
          onChange({ from: middle - half, to: middle + half });
        }}
        className="relative flex h-10 cursor-pointer items-end gap-px overflow-hidden rounded-md bg-scene-ink/[0.03]"
      >
        {buckets.map((bucket) => {
          const inView = bucket.to > window_.from && bucket.from < window_.to;
          return (
            <span
              key={bucket.key}
              title={`${bucket.label}: ${bucket.count} event${bucket.count === 1 ? "" : "s"}`}
              data-testid={`period-${bucket.key}`}
              data-count={bucket.count}
              style={{ height: bucket.count ? `${Math.max(10, (bucket.count / fullest) * 100)}%` : "2px" }}
              className={
                "min-w-[2px] flex-1 rounded-sm " +
                (inView ? "bg-scene-ink/45" : "bg-scene-ink/20")
              }
            />
          );
        })}

        <div
          onPointerDown={(event) => begin(event, "move")}
          data-testid="navigator-window"
          style={{ left: `${boxLeft}%`, width: `${boxWidth}%` }}
          className="absolute inset-y-0 cursor-grab rounded-md border border-scene-ink/50 bg-scene-ink/[0.06] active:cursor-grabbing"
        >
          <span
            onPointerDown={(event) => begin(event, "start")}
            role="slider"
            tabIndex={0}
            aria-label="Window start"
            aria-valuenow={Math.round(left)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="absolute -left-1 bottom-1 top-1 w-1.5 cursor-ew-resize rounded-full bg-scene-ink/60"
          />
          <span
            onPointerDown={(event) => begin(event, "end")}
            role="slider"
            tabIndex={0}
            aria-label="Window end"
            aria-valuenow={Math.round(left + width)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="absolute -right-1 bottom-1 top-1 w-1.5 cursor-ew-resize rounded-full bg-scene-ink/60"
          />
        </div>
      </div>

      <div className="mt-1 flex items-baseline justify-between gap-3 text-[0.65rem] text-scene-ink/45">
        <span>{buckets[0]?.label ?? "—"}</span>
        <span className="text-scene-ink/35">
          Events per {unit} · the box is what you see — drag it to move
        </span>
        <span>{buckets[buckets.length - 1]?.label ?? "—"}</span>
      </div>
    </div>
  );
}
