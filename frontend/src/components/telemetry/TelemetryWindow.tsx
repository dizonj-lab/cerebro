"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

import { TelemetryPanel } from "@/components/telemetry/TelemetryPanel";
import {
  clampToViewport,
  telemetryWindowServerSnapshot,
  telemetryWindowSnapshot,
  MIN_HEIGHT,
  MIN_OPACITY,
  MIN_WIDTH,
  setTelemetryWindow,
  subscribeTelemetryWindow,
} from "@/lib/telemetryWindowState";
import type { TelemetryWindowGeometry } from "@/lib/telemetryWindowState";
import { cn } from "@/lib/cn";

/** Which edges a drag on this handle moves. */
const HANDLES = [
  { key: "n", className: "left-2 right-2 top-0 h-1.5 cursor-ns-resize", x: 0, y: -1 },
  { key: "s", className: "left-2 right-2 bottom-0 h-1.5 cursor-ns-resize", x: 0, y: 1 },
  { key: "w", className: "top-2 bottom-2 left-0 w-1.5 cursor-ew-resize", x: -1, y: 0 },
  { key: "e", className: "top-2 bottom-2 right-0 w-1.5 cursor-ew-resize", x: 1, y: 0 },
  { key: "nw", className: "left-0 top-0 size-3 cursor-nwse-resize", x: -1, y: -1 },
  { key: "ne", className: "right-0 top-0 size-3 cursor-nesw-resize", x: 1, y: -1 },
  { key: "sw", className: "left-0 bottom-0 size-3 cursor-nesw-resize", x: -1, y: 1 },
  { key: "se", className: "right-0 bottom-0 size-3 cursor-nwse-resize", x: 1, y: 1 },
] as const;

const STEP = 16;

/**
 * Telemetry — a floating window over whichever module the user is in.
 *
 * Mounted once in the shell, so it survives navigation between Dashboard,
 * Library, Galaxy and Timeline: a client-side route change re-renders the
 * page beneath it and leaves this component, and its telemetry, alone.
 *
 * Dragging and resizing write straight to the element's style and commit to
 * the store once the pointer is released. A React render per pointermove
 * would re-render the telemetry inside the window sixty times a second in
 * order to move a box; the DOM can move the box on its own.
 */
export function TelemetryWindow() {
  const geometry = useSyncExternalStore(
    subscribeTelemetryWindow,
    telemetryWindowSnapshot,
    telemetryWindowServerSnapshot,
  );
  const frame = useRef<HTMLDivElement>(null);
  // Where a gesture started, and the values it is currently writing.
  const gesture = useRef<{ geometry: TelemetryWindowGeometry; x: number; y: number } | null>(null);
  // Only the in-flight value of a gesture; the store stays the source of
  // truth, so nothing is mirrored into a ref during render.
  const live = useRef<TelemetryWindowGeometry | null>(null);

  const paint = useCallback((next: TelemetryWindowGeometry) => {
    const element = frame.current;
    if (!element) return;
    // transform rather than top/left: the compositor can move it without a
    // layout pass, which is what keeps a drag smooth over the Galaxy.
    element.style.transform = `translate3d(${next.x}px, ${next.y}px, 0)`;
    element.style.width = `${next.width}px`;
    element.style.height = `${next.height}px`;
  }, []);

  /* Keep the window reachable when the viewport changes. */
  useEffect(() => {
    function onResize() {
      const current = telemetryWindowSnapshot();
      if (!current.open || current.mode !== "normal") return;
      const clamped = clampToViewport(current, {
        width: window.innerWidth,
        height: window.innerHeight,
      });
      if (
        clamped.x !== current.x ||
        clamped.y !== current.y ||
        clamped.width !== current.width ||
        clamped.height !== current.height
      ) {
        setTelemetryWindow(clamped);
      }
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  function begin(event: React.PointerEvent, handle: (typeof HANDLES)[number] | null) {
    if (event.button !== 0) return;
    event.preventDefault();
    const from = telemetryWindowSnapshot();
    live.current = from;
    gesture.current = { geometry: from, x: event.clientX, y: event.clientY };
    const element = frame.current;

    const move = (e: PointerEvent) => {
      const start = gesture.current;
      if (!start) return;
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      const next = handle
        ? resize(start.geometry, handle, dx, dy)
        : { ...start.geometry, x: start.geometry.x + dx, y: start.geometry.y + dy };
      live.current = clampToViewport(next, {
        width: window.innerWidth,
        height: window.innerHeight,
      });
      paint(live.current);
    };
    const end = () => {
      gesture.current = null;
      if (element) element.style.transition = "";
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      // One store write per gesture: the window is remembered without
      // persisting every intermediate pixel.
      if (live.current) setTelemetryWindow(live.current);
    };
    // Listeners on the window, not the handle: a fast drag outruns a 6px
    // strip, and the gesture must continue anyway.
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  }

  function onTitleKeyDown(event: React.KeyboardEvent) {
    const arrows = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"];
    if (!arrows.includes(event.key)) return;
    event.preventDefault();
    const dx = (event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0) * STEP;
    const dy = (event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0) * STEP;
    // Shift resizes, so the window is as usable from the keyboard as from a
    // pointer; without it a keyboard user could never make it bigger.
    const next = event.shiftKey
      ? { ...geometry, width: geometry.width + dx, height: geometry.height + dy }
      : { ...geometry, x: geometry.x + dx, y: geometry.y + dy };
    setTelemetryWindow(clampToViewport(next, { width: window.innerWidth, height: window.innerHeight }));
  }

  if (!geometry.open) return null;

  if (geometry.mode === "minimized") {
    return (
      <button
        type="button"
        data-testid="telemetry-widget"
        onClick={() => setTelemetryWindow({ mode: "normal" })}
        className="fixed bottom-4 right-4 z-[60] inline-flex items-center gap-2 rounded-full border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink shadow-subtle"
      >
        <span className="size-2 rounded-full bg-accent" aria-hidden="true" />
        Telemetry
      </button>
    );
  }

  const maximized = geometry.mode === "maximized";

  return (
    <div
      ref={frame}
      role="dialog"
      aria-label="Telemetry"
      data-testid="telemetry-window"
      data-mode={geometry.mode}
      style={
        maximized
          ? { opacity: geometry.opacity }
          : {
              transform: `translate3d(${geometry.x}px, ${geometry.y}px, 0)`,
              width: geometry.width,
              height: geometry.height,
              opacity: geometry.opacity,
            }
      }
      className={cn(
        // Fixed and above the modules, but only as large as itself: the page
        // underneath keeps every pointer event this window does not cover,
        // so the Galaxy still pans and its nodes still drag.
        "fixed z-[60] flex flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-subtle backdrop-blur",
        maximized ? "inset-2" : "left-0 top-0",
      )}
    >
      <div
        onPointerDown={(event) => {
          // A press on a control belongs to that control, not to a drag.
          if (event.target !== event.currentTarget) return;
          begin(event, null);
        }}
        onDoubleClick={(event) => {
          if (event.target !== event.currentTarget) return;
          setTelemetryWindow({ mode: maximized ? "normal" : "maximized" });
        }}
        onKeyDown={onTitleKeyDown}
        tabIndex={0}
        role="toolbar"
        aria-label="Telemetry window — arrow keys move, shift and arrow keys resize"
        data-testid="telemetry-title"
        className={cn(
          "flex shrink-0 select-none items-center gap-2 border-b border-line bg-surface-subtle px-3 py-2",
          "text-xs font-semibold uppercase tracking-wide text-ink",
          maximized ? "cursor-default" : "cursor-grab active:cursor-grabbing",
        )}
      >
        Telemetry
        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[10px] font-normal normal-case text-ink-muted">
            <span className="sr-only">Opacity</span>
            <input
              type="range"
              min={MIN_OPACITY * 100}
              max={100}
              step={5}
              value={Math.round(geometry.opacity * 100)}
              aria-label="Window opacity"
              onChange={(e) => setTelemetryWindow({ opacity: Number(e.target.value) / 100 })}
              className="w-16 accent-accent"
            />
          </label>
          <Control label="Minimize" onClick={() => setTelemetryWindow({ mode: "minimized" })}>
            <path d="M5 14h10" />
          </Control>
          <Control
            label={maximized ? "Restore" : "Maximize"}
            onClick={() => setTelemetryWindow({ mode: maximized ? "normal" : "maximized" })}
          >
            {maximized ? <path d="M7 7h8v8H7zM4 13V4h9" /> : <rect x="5" y="5" width="10" height="10" rx="1.5" />}
          </Control>
          <Control label="Close Telemetry" onClick={() => setTelemetryWindow({ open: false })}>
            <path d="m6 6 8 8M14 6l-8 8" />
          </Control>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <TelemetryPanel />
      </div>

      {/* Resize handles. Absent when maximized, where there is nothing to resize. */}
      {!maximized &&
        HANDLES.map((handle) => (
          <div
            key={handle.key}
            onPointerDown={(event) => begin(event, handle)}
            data-testid={`telemetry-resize-${handle.key}`}
            aria-hidden="true"
            className={cn("absolute touch-none", handle.className)}
          />
        ))}
    </div>
  );
}

function resize(
  start: TelemetryWindowGeometry,
  handle: (typeof HANDLES)[number],
  dx: number,
  dy: number,
): TelemetryWindowGeometry {
  let { x, y, width, height } = start;
  if (handle.x === 1) width = Math.max(MIN_WIDTH, start.width + dx);
  if (handle.x === -1) {
    // A left or top edge moves the origin as well as the size, and must stop
    // at the minimum rather than pushing the window sideways.
    width = Math.max(MIN_WIDTH, start.width - dx);
    x = start.x + (start.width - width);
  }
  if (handle.y === 1) height = Math.max(MIN_HEIGHT, start.height + dy);
  if (handle.y === -1) {
    height = Math.max(MIN_HEIGHT, start.height - dy);
    y = start.y + (start.height - height);
  }
  return { ...start, x, y, width, height };
}

function Control({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="rounded p-1 text-ink-muted transition-colors hover:bg-surface hover:text-ink"
    >
      <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
        {children}
      </svg>
    </button>
  );
}
