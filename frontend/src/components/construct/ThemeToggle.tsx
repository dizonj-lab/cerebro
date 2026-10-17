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
      <span className="block size-5">
        <Contrast dark={appearance === "dark"} />
      </span>
    </button>
  );
}

/**
 * One mark for both states: a circle, half filled.
 *
 * The rayed sun read as a settings gear at this size, and the pair of them
 * sat next to each other in the header. A contrast disc says "appearance"
 * without competing, and which half is filled says which way the switch
 * will go. The label carries the meaning for anyone who cannot see it.
 */
function Contrast({ dark }: { dark: boolean }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="10" cy="10" r="6.75" />
      <path
        d={dark ? "M10 3.25a6.75 6.75 0 0 0 0 13.5z" : "M10 3.25a6.75 6.75 0 0 1 0 13.5z"}
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}
