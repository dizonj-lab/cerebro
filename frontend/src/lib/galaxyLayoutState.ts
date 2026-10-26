/**
 * How the user has arranged the Galaxy workspace.
 *
 * Whether the timeline is open and how tall, whether the details panel is
 * open, where the legend and the what-if window sit and whether they are
 * folded away. Kept in localStorage and read through `useSyncExternalStore`,
 * like the telemetry window, so an arrangement survives navigation and
 * reloads instead of resetting — the timeline in particular used to come
 * back hidden after it had been opened.
 *
 * Only the arrangement is stored. Nothing about the library is.
 */
import { useCallback, useSyncExternalStore } from "react";

const KEY = "cerebro-galaxy-layout";

export interface GalaxyLayout {
  timelineOpen: boolean;
  timelineHeight: number;
  panelOpen: boolean;
  /** Folded by default: the map is what the screen is for. */
  legendOpen: boolean;
  legendX: number;
  legendY: number;
  /** The what-if window: folded to a tab at the left edge, or open where it was left. */
  lensMinimized: boolean;
  lensX: number;
  lensY: number;
  /** Node details: same window as the what-if; x below zero docks it right. */
  nodeMinimized: boolean;
  nodeX: number;
  nodeY: number;
}

const DEFAULTS: GalaxyLayout = {
  timelineOpen: true,
  timelineHeight: 240,
  panelOpen: true,
  legendOpen: false,
  legendX: 12,
  legendY: 12,
  lensMinimized: true,
  lensX: 12,
  lensY: 64,
  nodeMinimized: false,
  nodeX: -1,
  nodeY: 64,
};

const listeners = new Set<() => void>();
let snapshot: GalaxyLayout | undefined;

function sane(value: unknown): GalaxyLayout {
  if (typeof value !== "object" || value === null) return DEFAULTS;
  const raw = value as Partial<Record<keyof GalaxyLayout, unknown>>;
  const out = { ...DEFAULTS };
  for (const key of Object.keys(DEFAULTS) as (keyof GalaxyLayout)[]) {
    const v = raw[key];
    if (typeof v === typeof DEFAULTS[key] && (typeof v !== "number" || Number.isFinite(v))) {
      (out as Record<string, unknown>)[key] = v;
    }
  }
  out.timelineHeight = Math.min(520, Math.max(120, out.timelineHeight));
  return out;
}

function read(): GalaxyLayout {
  if (snapshot) return snapshot;
  try {
    snapshot = sane(JSON.parse(window.localStorage.getItem(KEY) ?? "null"));
  } catch {
    // Storage unavailable (private window, blocked site data): use defaults.
    snapshot = DEFAULTS;
  }
  return snapshot;
}

function write(next: GalaxyLayout) {
  snapshot = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Not persisted, but the session still works.
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useGalaxyLayout(): [GalaxyLayout, (change: Partial<GalaxyLayout>) => void] {
  const layout = useSyncExternalStore(subscribe, read, () => DEFAULTS);
  const update = useCallback((change: Partial<GalaxyLayout>) => write({ ...read(), ...change }), []);
  return [layout, update];
}
