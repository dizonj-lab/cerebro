"use client";

import { useId, useRef, useState } from "react";

import { dateMs } from "@/components/timeline/lanes";

const YEAR = 365.25 * 24 * 60 * 60 * 1000;

/**
 * The overview: where the events are, and which part of that is on screen.
 *
 * A line through the number of events per year — per month when the whole
 * library spans less than eight years — with the area under it shaded. The
 * shading is one gradient across the strip's full height rather than per
 * hump, so colour tracks size: a tall peak reaches the strong end of the
 * accent and a small bump stays faint. It used to be pages of
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
  const gradient = useId().replace(/:/g, "");
  const [pointed, setPointed] = useState<number | null>(null);

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
        className="relative h-12 cursor-pointer overflow-hidden rounded-md bg-scene-ink/[0.03]"
      >
        <svg
          viewBox="0 0 1000 100"
          preserveAspectRatio="none"
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 size-full"
        >
          <defs>
            <linearGradient id={gradient} gradientUnits="userSpaceOnUse" x1="0" y1="8" x2="0" y2="100">
              <stop offset="0%" style={{ stopColor: "var(--color-accent)" }} stopOpacity="0.75" />
              <stop offset="55%" style={{ stopColor: "var(--color-accent)" }} stopOpacity="0.28" />
              <stop offset="100%" style={{ stopColor: "var(--color-accent)" }} stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <path d={area(buckets, fullest)} style={{ fill: `url(#${gradient})` }} />
          <path
            d={line(buckets, fullest)}
            fill="none"
            style={{ stroke: "var(--color-accent)" }}
            strokeWidth="1.5"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
          {pointed !== null && buckets[pointed] && (
            <line
              x1={xAt(pointed, buckets.length)}
              x2={xAt(pointed, buckets.length)}
              y1="0"
              y2="100"
              style={{ stroke: "var(--color-accent)" }}
              strokeWidth="1"
              strokeDasharray="2 2"
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>

        {/* One invisible column per period: the hover target, its tooltip,
            and the figures, so every value is reachable without the line. */}
        <div className="absolute inset-0 flex">
          {buckets.map((bucket, index) => (
            <span
              key={bucket.key}
              title={`${bucket.label}: ${bucket.count} event${bucket.count === 1 ? "" : "s"}`}
              data-testid={`period-${bucket.key}`}
              data-count={bucket.count}
              onPointerEnter={() => setPointed(index)}
              onPointerLeave={() => setPointed(null)}
              className="h-full min-w-0 flex-1"
            />
          ))}
        </div>
        {pointed !== null && buckets[pointed] && (
          <span
            className="pointer-events-none absolute top-0.5 z-10 -translate-x-1/2 whitespace-nowrap rounded bg-scene-raised/95 px-1.5 py-0.5 text-[0.625rem] text-scene-ink shadow"
            style={{ left: `${Math.min(92, Math.max(8, (xAt(pointed, buckets.length) / 1000) * 100))}%` }}
          >
            {buckets[pointed].label} · {buckets[pointed].count} event{buckets[pointed].count === 1 ? "" : "s"}
          </span>
        )}

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

/** A period's centre across the strip, in the 0–1000 drawing space. */
function xAt(index: number, total: number): number {
  return ((index + 0.5) / Math.max(total, 1)) * 1000;
}

/** Height on the 0–100 drawing space; the tallest period nearly fills it. */
function yAt(count: number, fullest: number): number {
  return 100 - (count / fullest) * 88;
}

/**
 * A smooth curve through every period.
 *
 * Monotone in y between neighbours (each control point is clamped between its
 * two ends), so the curve never dips below zero or overshoots a peak — a
 * smoothing that invents a value the data does not have would be lying.
 */
function line(buckets: { count: number }[], fullest: number): string {
  const points = buckets.map((b, i) => [xAt(i, buckets.length), yAt(b.count, fullest)] as const);
  if (!points.length) return "";
  if (points.length === 1) return `M0,${points[0][1]} L1000,${points[0][1]}`;
  let d = `M0,${points[0][1]} L${points[0][0]},${points[0][1]}`;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const mid = (x0 + x1) / 2;
    d += ` C${mid},${y0} ${mid},${y1} ${x1},${y1}`;
  }
  return `${d} L1000,${points[points.length - 1][1]}`;
}

function area(buckets: { count: number }[], fullest: number): string {
  const d = line(buckets, fullest);
  return d ? `${d} L1000,100 L0,100 Z` : "";
}
