"use client";

import { useSyncExternalStore } from "react";

import { IconGodMode } from "@/components/construct/icons";
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
      <span className="block size-5">
        <IconGodMode />
      </span>
    </button>
  );
}
