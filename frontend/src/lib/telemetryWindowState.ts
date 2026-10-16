/**
 * The Telemetry window's geometry.
 *
 * Position, size, opacity and display mode live in one external store read
 * through `useSyncExternalStore`, for the same reason the sidebar rail does:
 * the value is in localStorage, outside React, and the window must survive
 * navigation between modules without resetting.
 *
 * Geometry is stored, not the telemetry. Numbers the user is looking at are
 * fetched fresh; only where they chose to put the window is remembered.
 */
const KEY = "cerebro-telemetry-window";
// What the key was called before the window was renamed. Read once, so the
// rename does not throw away a position someone had arranged.
const LEGACY_KEY = "cerebro-godmode";

export type TelemetryWindowMode = "normal" | "minimized" | "maximized";

export interface TelemetryWindowGeometry {
  open: boolean;
  mode: TelemetryWindowMode;
  x: number;
  y: number;
  width: number;
  height: number;
  /** 0.5 to 1. Below half, text stops being readable over a busy canvas. */
  opacity: number;
}

export const MIN_WIDTH = 320;
export const MIN_HEIGHT = 240;
export const MIN_OPACITY = 0.5;

const DEFAULTS: TelemetryWindowGeometry = {
  open: false,
  mode: "normal",
  x: 24,
  y: 88,
  width: 420,
  height: 360,
  opacity: 0.85,
};

const listeners = new Set<() => void>();
let snapshot: TelemetryWindowGeometry | undefined;

function sane(value: unknown): TelemetryWindowGeometry {
  if (typeof value !== "object" || value === null) return DEFAULTS;
  const raw = value as Partial<TelemetryWindowGeometry>;
  const number = (v: unknown, fallback: number) =>
    typeof v === "number" && Number.isFinite(v) ? v : fallback;
  return {
    open: raw.open === true,
    mode:
      raw.mode === "minimized" || raw.mode === "maximized" || raw.mode === "normal"
        ? raw.mode
        : "normal",
    x: number(raw.x, DEFAULTS.x),
    y: number(raw.y, DEFAULTS.y),
    width: Math.max(MIN_WIDTH, number(raw.width, DEFAULTS.width)),
    height: Math.max(MIN_HEIGHT, number(raw.height, DEFAULTS.height)),
    opacity: Math.min(1, Math.max(MIN_OPACITY, number(raw.opacity, DEFAULTS.opacity))),
  };
}

function read(): TelemetryWindowGeometry {
  try {
    const raw = window.localStorage.getItem(KEY) ?? window.localStorage.getItem(LEGACY_KEY);
    // Anything stored by an older version, or edited by hand, is normalised
    // rather than trusted: a NaN width would render an invisible window.
    return raw ? sane(JSON.parse(raw)) : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export function subscribeTelemetryWindow(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function telemetryWindowSnapshot(): TelemetryWindowGeometry {
  if (snapshot === undefined) snapshot = read();
  return snapshot;
}

/** The server has no storage, and must agree with the first client render. */
export function telemetryWindowServerSnapshot(): TelemetryWindowGeometry {
  return DEFAULTS;
}

export function setTelemetryWindow(next: Partial<TelemetryWindowGeometry>): void {
  const merged = sane({ ...telemetryWindowSnapshot(), ...next });
  snapshot = merged;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(merged));
  } catch {
    // The window still behaves for this page; only persistence is lost.
  }
  for (const listener of listeners) listener();
}

/**
 * Keep the window inside the viewport.
 *
 * Called when it is dragged, resized, and when the viewport itself changes —
 * a window dragged to the right of a wide screen must not be unreachable
 * after the browser is made narrow. A margin is left on every side so the
 * title bar is always grabbable.
 */
export function clampToViewport(
  geometry: TelemetryWindowGeometry,
  viewport: { width: number; height: number },
): TelemetryWindowGeometry {
  const margin = 8;
  const width = Math.min(Math.max(MIN_WIDTH, geometry.width), Math.max(MIN_WIDTH, viewport.width - margin * 2));
  const height = Math.min(
    Math.max(MIN_HEIGHT, geometry.height),
    Math.max(MIN_HEIGHT, viewport.height - margin * 2),
  );
  return {
    ...geometry,
    width,
    height,
    x: Math.min(Math.max(margin, geometry.x), Math.max(margin, viewport.width - width - margin)),
    y: Math.min(Math.max(margin, geometry.y), Math.max(margin, viewport.height - height - margin)),
  };
}
