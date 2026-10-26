/**
 * A small per-browser settings store: localStorage behind
 * `useSyncExternalStore`, so a remembered value is there from the first
 * client render and every component reading it stays in step.
 *
 * Only view preferences belong here — how something is arranged or shown,
 * never anything about the library. A value of the wrong type (an older
 * shape, a hand-edited entry) falls back to its default rather than breaking
 * the page, and blocked storage simply means nothing is remembered.
 */
import { useCallback, useSyncExternalStore } from "react";

export function createPersistedStore<T extends Record<string, unknown>>(key: string, defaults: T) {
  const listeners = new Set<() => void>();
  let snapshot: T | undefined;

  function sane(value: unknown): T {
    if (typeof value !== "object" || value === null) return defaults;
    const raw = value as Record<string, unknown>;
    const out: Record<string, unknown> = { ...defaults };
    for (const name of Object.keys(defaults)) {
      const v = raw[name];
      const expected = defaults[name];
      const sameType =
        expected === null ? v === null || typeof v === "number" || typeof v === "string" : typeof v === typeof expected;
      if (sameType && (typeof v !== "number" || Number.isFinite(v)) && (!Array.isArray(expected) || Array.isArray(v))) {
        out[name] = v;
      }
    }
    return out as T;
  }

  function read(): T {
    if (snapshot) return snapshot;
    try {
      snapshot = sane(JSON.parse(window.localStorage.getItem(key) ?? "null"));
    } catch {
      snapshot = defaults;
    }
    return snapshot;
  }

  function write(next: T) {
    snapshot = next;
    try {
      window.localStorage.setItem(key, JSON.stringify(next));
    } catch {
      // Not remembered, but the page still works.
    }
    for (const listener of listeners) listener();
  }

  function subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return function usePersisted(): [T, (change: Partial<T>) => void] {
    const value = useSyncExternalStore(subscribe, read, () => defaults);
    const update = useCallback((change: Partial<T>) => write({ ...read(), ...change }), []);
    return [value, update];
  };
}
