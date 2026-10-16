/**
 * Whether the sidebar is collapsed to its icon rail.
 *
 * A tiny external store rather than state seeded in an effect: the value
 * lives in localStorage, which is outside React, and `useSyncExternalStore`
 * is what reads such a value without a second render on mount.
 *
 * The server always reports "open" so the markup it sends matches the first
 * client render; the stored value is applied immediately afterwards.
 */
const KEY = "cerebro-rail";

const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "collapsed";
  } catch {
    // Private browsing or storage disabled. The default stands.
    return false;
  }
}

let snapshot: boolean | null = null;

export function subscribeRail(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function railSnapshot(): boolean {
  if (snapshot === null) snapshot = read();
  return snapshot;
}

/** The server has no storage, and must agree with the first client render. */
export function railServerSnapshot(): boolean {
  return false;
}

export function setRailCollapsed(collapsed: boolean): void {
  snapshot = collapsed;
  try {
    window.localStorage.setItem(KEY, collapsed ? "collapsed" : "open");
  } catch {
    // The choice still applies for this page.
  }
  for (const listener of listeners) listener();
}
