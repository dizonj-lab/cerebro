"use client";

import { useSyncExternalStore } from "react";

import {
  godModeServerSnapshot,
  godModeSnapshot,
  setGodMode,
  subscribeGodMode,
} from "@/lib/godModeState";

/**
 * Opens GOD MODE, and closes it again.
 *
 * It restores whatever geometry was stored rather than resetting the window,
 * so reopening it puts it back where the user left it.
 */
export function GodModeLauncher() {
  const geometry = useSyncExternalStore(
    subscribeGodMode,
    godModeSnapshot,
    godModeServerSnapshot,
  );

  return (
    <button
      type="button"
      data-testid="god-mode-launcher"
      aria-pressed={geometry.open}
      aria-label={geometry.open ? "Close GOD MODE" : "Open GOD MODE"}
      title={geometry.open ? "Close GOD MODE" : "Open GOD MODE"}
      onClick={() =>
        setGodMode(
          geometry.open ? { open: false } : { open: true, mode: geometry.mode === "minimized" ? "normal" : geometry.mode },
        )
      }
      className="hidden rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-subtle hover:text-ink aria-pressed:bg-accent-subtle aria-pressed:text-accent sm:block"
    >
      <svg viewBox="0 0 20 20" className="block size-5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="10" cy="10" r="2.25" />
        <path d="M10 1.5v3M10 15.5v3M1.5 10h3M15.5 10h3M4 4l2.1 2.1M13.9 13.9 16 16M16 4l-2.1 2.1M6.1 13.9 4 16" />
      </svg>
    </button>
  );
}
