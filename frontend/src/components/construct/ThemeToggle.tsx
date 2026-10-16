"use client";

import { useSyncExternalStore } from "react";

import { api } from "@/lib/api";
import {
  appearanceServerSnapshot,
  appearanceSnapshot,
  chooseTheme,
  subscribeAppearance,
} from "@/lib/theme";

/**
 * Light and dark, switched where the user is.
 *
 * Appearance used to be reachable only from Settings, so changing it meant
 * leaving the page you were looking at — and on the Galaxy, losing the view
 * you had arranged. This switches in place.
 *
 * It writes an explicit choice, which is what the user asked for by pressing
 * it. "Match my system" remains in Settings: that is a different intent, and
 * a two-state button cannot express three states honestly.
 *
 * The account preference is updated in the background, so the choice follows
 * the user to another machine. The theme itself applies immediately and does
 * not wait for that request — an appearance control that lags a round trip
 * feels broken.
 */
export function ThemeToggle() {
  const appearance = useSyncExternalStore(
    subscribeAppearance,
    appearanceSnapshot,
    appearanceServerSnapshot,
  );
  const next = appearance === "dark" ? "light" : "dark";

  function toggle() {
    chooseTheme(next);
    void api.savePreferences({ theme: next }).catch(() => {
      // The page is already in the chosen theme and localStorage holds it.
      // Only the cross-machine copy failed, so say nothing here.
    });
  }

  return (
    <button
      type="button"
      onClick={toggle}
      data-testid="theme-toggle"
      aria-label={`Switch to ${next} appearance`}
      title={`Switch to ${next} appearance`}
      className="hidden rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-subtle hover:text-ink sm:block"
    >
      <span className="block size-5">{appearance === "dark" ? <Sun /> : <Moon />}</span>
    </button>
  );
}

function Sun() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
      <circle cx="10" cy="10" r="3.75" />
      <path d="M10 2.5v1.75M10 15.75v1.75M2.5 10h1.75M15.75 10h1.75M4.7 4.7l1.25 1.25M14.05 14.05l1.25 1.25M15.3 4.7l-1.25 1.25M5.95 14.05L4.7 15.3" />
    </svg>
  );
}

function Moon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M16.25 12.4A6.75 6.75 0 0 1 7.6 3.75a6.75 6.75 0 1 0 8.65 8.65Z" />
    </svg>
  );
}
