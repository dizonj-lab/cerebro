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

/** How a date reads, at the precision the document actually gave. */
export function formatEventDate(event: CerebroTimelineEventDetail): string {
  const date = new Date(`${event.date}T00:00:00`);
  if (event.precision === "year") return String(date.getUTCFullYear());
  if (event.precision === "quarter") {
    return `Q${Math.floor(date.getUTCMonth() / 3) + 1} ${date.getUTCFullYear()}`;
  }
  if (event.precision === "month") {
    return date.toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Where a date sits on the axis, as a fraction of the visible span. */
export function fractionOf(date: string, from: number, to: number): number {
  const at = new Date(`${date}T00:00:00`).getTime();
  if (to <= from) return 0;
  return (at - from) / (to - from);
}

export function describeLocation(location: Record<string, number | string>): string {
  const parts = Object.entries(location)
    .filter(([key, value]) => value !== null && value !== "" && key !== "char_start" && key !== "char_end")
    .map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`);
  // Only what extraction established. A modality without pages has none.
  return parts.join(", ");
}
