import type { CerebroTimelineEventDetail } from "@/lib/api";

/**
 * The six lanes of the approved design, plus Other.
 *
 * Colours are literals rather than design tokens on purpose: the timeline is
 * a dark canvas like the Galaxy, where the themed surface tokens do not
 * apply, and these six hues are the specification. They match the Galaxy's
 * palette so a concept keeps its colour across both views.
 */
export const LANES = [
  { name: "Strategy", color: "#a855f7" },
  { name: "Architecture", color: "#3b82f6" },
  { name: "Governance", color: "#22c55e" },
  { name: "Technology", color: "#f97316" },
  { name: "Projects", color: "#ef4444" },
  { name: "People", color: "#eab308" },
  { name: "Other", color: "#64748b" },
] as const;

export const LANE_COLOR: Record<string, string> = Object.fromEntries(
  LANES.map((lane) => [lane.name, lane.color]),
);

/**
 * A lane's colour.
 *
 * Lanes are the library's own confirmed topics, so most names will not be
 * one of the six the design names. A named lane keeps its colour; anything
 * else takes the next hue in the same palette, by position, so the colours
 * stay stable while the lanes do.
 */
export function colorForLane(name: string, index: number): string {
  return LANE_COLOR[name] ?? LANES[index % (LANES.length - 1)].color;
}

/**
 * A calendar date as a UTC timestamp.
 *
 * Dates are calendar days, not instants, so they are read as UTC and shown as
 * UTC. Reading "1982-01-01" as local midnight and printing it in UTC put every
 * year east of Greenwich one step early: in Singapore, a 1982 citation showed
 * as 1981.
 */
export function dateMs(iso: string): number {
  return Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
}

/** How a date reads, at the precision the document actually gave. */
export function formatEventDate(event: CerebroTimelineEventDetail): string {
  const date = new Date(dateMs(event.date));
  if (event.precision === "year") return String(date.getUTCFullYear());
  if (event.precision === "quarter") {
    return `Q${Math.floor(date.getUTCMonth() / 3) + 1} ${date.getUTCFullYear()}`;
  }
  if (event.precision === "month") {
    return date.toLocaleDateString(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
  }
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Where a date sits on the axis, as a fraction of the visible span. */
export function fractionOf(date: string, from: number, to: number): number {
  if (to <= from) return 0;
  return (dateMs(date) - from) / (to - from);
}

const YEAR_MS = 365.25 * 24 * 60 * 60 * 1000;

/** A span in words: "8 months", "3.5 years", "50 years". */
export function describeSpan(ms: number): string {
  const years = ms / YEAR_MS;
  if (years < 1) {
    const months = Math.max(1, Math.round(years * 12));
    return `${months} month${months === 1 ? "" : "s"}`;
  }
  const rounded = years < 10 ? Math.round(years * 2) / 2 : Math.round(years);
  return `${rounded} year${rounded === 1 ? "" : "s"}`;
}

/** The visible window as a reader would say it: "Mar 2021 – Sep 2024". */
export function describeWindow(from: number, to: number): string {
  const wide = to - from > YEAR_MS * 6;
  const fmt = (ms: number) =>
    new Date(ms).toLocaleDateString(undefined, {
      ...(wide ? {} : { month: "short" }),
      year: "numeric",
      timeZone: "UTC",
    });
  return `${fmt(from)} – ${fmt(to)}`;
}

export function describeLocation(location: Record<string, number | string>): string {
  const parts = Object.entries(location)
    .filter(([key, value]) => value !== null && value !== "" && key !== "char_start" && key !== "char_end")
    .map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`);
  // Only what extraction established. A modality without pages has none.
  return parts.join(", ");
}
