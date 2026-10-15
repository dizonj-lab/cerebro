/**
 * Dashboard charts, drawn as inline SVG.
 *
 * No charting library: the project has none, and a donut and a bar strip do
 * not justify adding a dependency that would then have to be themed, bundled
 * and kept current. Colour comes from the same tokens as everything else, so
 * both charts follow the theme with no per-theme code.
 */
import { cn } from "@/lib/cn";

// Hues for categorical slices, as CSS variables so the legend and the arc
// cannot drift apart. Chosen to stay distinguishable on both themes.
const SLICE_COLORS = [
  "var(--color-accent)",
  "#8b5cf6",
  "#ec4899",
  "#f59e0b",
  "#14b8a6",
  "var(--color-ink-subtle)",
];

export function sliceColor(index: number): string {
  return SLICE_COLORS[index % SLICE_COLORS.length];
}

/**
 * A donut, drawn with one stroked circle per slice.
 *
 * `stroke-dasharray` plus an offset is far less code than generating arc
 * paths, and it renders identically.
 */
export function Donut({
  slices,
  total,
  label,
}: {
  slices: { label: string; count: number }[];
  total: number;
  label: string;
}) {
  const sum = slices.reduce((n, s) => n + s.count, 0) || 1;
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  // Offsets are computed up front rather than accumulated during render: a
  // variable mutated inside map() gives a different result on a re-render.
  const arcs = slices.reduce<{ label: string; length: number; offset: number }[]>(
    (acc, slice) => {
      const length = (slice.count / sum) * circumference;
      const previous = acc[acc.length - 1];
      const offset = previous ? previous.offset + previous.length : 0;
      return [...acc, { label: slice.label, length, offset }];
    },
    [],
  );

  return (
    <div className="relative size-[118px] shrink-0">
      <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden="true">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="var(--color-surface-sunken)" strokeWidth="13" />
        {arcs.map((arc, i) => (
          <circle
            key={arc.label}
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={sliceColor(i)}
            strokeWidth="13"
            strokeDasharray={`${arc.length} ${circumference - arc.length}`}
            strokeDashoffset={-arc.offset}
          />
        ))}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-semibold tabular-nums text-ink">{total}</span>
        <span className="text-[0.6875rem] text-ink-subtle">{label}</span>
      </div>
    </div>
  );
}

/** Daily counts as a bar strip. Heights are relative to the busiest day. */
export function Bars({
  data,
  className,
}: {
  data: { date: string; count: number }[];
  className?: string;
}) {
  const peak = Math.max(1, ...data.map((d) => d.count));
  // A rounded axis top, so the labels read as whole numbers.
  const top = peak <= 3 ? peak : Math.ceil(peak / 10) * 10;
  const ticks = [top, Math.round(top / 2), 0];

  return (
    <div className={cn("flex gap-2", className)}>
      <div className="flex h-20 flex-col justify-between py-0.5 text-[0.625rem] tabular-nums text-ink-subtle">
        {ticks.map((t) => (
          <span key={t}>{t}</span>
        ))}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex h-20 items-end gap-[3px]">
          {data.map((day) => (
            <div
              key={day.date}
              title={`${day.date}: ${day.count}`}
              style={{ height: `${Math.max(2, (day.count / top) * 100)}%` }}
              className={cn(
                "flex-1 rounded-sm transition-colors",
                day.count > 0 ? "bg-accent" : "bg-surface-sunken",
              )}
            />
          ))}
        </div>
        <div className="mt-1.5 flex justify-between text-[0.625rem] tabular-nums text-ink-subtle">
          {everyThird(data).map((d) => (
            <span key={d.date}>{shortDate(d.date)}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function everyThird<T>(items: T[]): T[] {
  return items.filter((_, i) => i % 3 === 0);
}

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
