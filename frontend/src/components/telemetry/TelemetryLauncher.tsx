"use client";

import { useSyncExternalStore } from "react";

import { IconTelemetry } from "@/components/construct/icons";
import {
  telemetryWindowServerSnapshot,
  telemetryWindowSnapshot,
  setTelemetryWindow,
  subscribeTelemetryWindow,
} from "@/lib/telemetryWindowState";

/**
 * Opens Telemetry, and closes it again.
 *
 * It restores whatever geometry was stored rather than resetting the window,
 * so reopening it puts it back where the user left it.
 */
export function TelemetryLauncher() {
  const geometry = useSyncExternalStore(
    subscribeTelemetryWindow,
    telemetryWindowSnapshot,
    telemetryWindowServerSnapshot,
  );

  return (
    <button
      type="button"
      data-testid="telemetry-launcher"
      aria-pressed={geometry.open}
      aria-label={geometry.open ? "Close Telemetry" : "Open Telemetry"}
      title={geometry.open ? "Close Telemetry" : "Open Telemetry"}
      onClick={() =>
        setTelemetryWindow(
          geometry.open ? { open: false } : { open: true, mode: geometry.mode === "minimized" ? "normal" : geometry.mode },
        )
      }
      className="hidden rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-subtle hover:text-ink aria-pressed:bg-accent-subtle aria-pressed:text-accent sm:block"
    >
      <span className="block size-5">
        <IconTelemetry />
      </span>
    </button>
  );
}
