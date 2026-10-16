/**
 * The sidebar's width preference.
 *
 * A tiny external store rather than state seeded in an effect: the value
 * lives in localStorage, which is outside React, and `useSyncExternalStore`
 * is what reads such a value without a second render on mount.
 *
 * Three states, not two. `null` means the user has never chosen, which is
 * what lets a route default apply — the Galaxy wants the screen, so it opens
 * railed. The moment the user picks a width themselves it is stored, and from
 * then on their choice holds everywhere, including on the Galaxy. A route
 * default must never win back a decision the user has made.
 */
const KEY = "cerebro-rail";

export type RailPreference = "collapsed" | "open" | null;

const listeners = new Set<() => void>();

function read(): RailPreference {
  try {
    const stored = window.localStorage.getItem(KEY);
    return stored === "collapsed" || stored === "open" ? stored : null;
  } catch {
    // Private browsing or storage disabled. No preference, so defaults stand.
    return null;
  }
}

// `undefined` marks "not read yet"; the snapshot must then stay identical
// between renders, which is why it is cached rather than read each time.
let snapshot: RailPreference | undefined;

export function subscribeRail(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function railSnapshot(): RailPreference {
  if (snapshot === undefined) snapshot = read();
  return snapshot;
}

/** The server has no storage, and must agree with the first client render. */
export function railServerSnapshot(): RailPreference {
  return null;
}

export function setRailCollapsed(collapsed: boolean): void {
  snapshot = collapsed ? "collapsed" : "open";
  try {
    window.localStorage.setItem(KEY, snapshot);
  } catch {
    // The choice still applies for this page.
  }
  for (const listener of listeners) listener();
}
