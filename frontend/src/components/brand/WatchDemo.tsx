"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { DEMO_VIDEO } from "@/lib/demo";

/**
 * "Watch demo": the five-minute narrated tour, played in a dialog over the page.
 *
 * The video loads only when opened, starts playing, and stops when closed
 * (the element is removed). Escape, the close button or a click outside closes it.
 */
export function WatchDemo({ size = "lg" }: { size?: "md" | "lg" }) {
  const [open, setOpen] = useState(false);
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <Button variant="secondary" size={size} onClick={() => setOpen(true)}>
        <svg aria-hidden="true" viewBox="0 0 16 16" className="size-3.5 fill-current">
          <path d="M4 2.8v10.4a.6.6 0 0 0 .9.5l8.3-5.2a.6.6 0 0 0 0-1L4.9 2.3a.6.6 0 0 0-.9.5z" />
        </svg>
        Watch demo
      </Button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8">
          <div aria-hidden="true" className="absolute inset-0 bg-ink/70" onClick={() => setOpen(false)} />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={DEMO_VIDEO.title}
            className="relative w-full max-w-5xl overflow-hidden rounded-lg border border-line bg-surface shadow-card"
          >
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="text-sm font-medium text-ink">{DEMO_VIDEO.title}</span>
              <button
                ref={close}
                type="button"
                aria-label="Close the demo"
                onClick={() => setOpen(false)}
                className="rounded-md px-2 py-1 text-ink-muted hover:bg-surface-subtle hover:text-ink"
              >
                ✕
              </button>
            </div>
            <video
              data-testid="demo-video"
              src={DEMO_VIDEO.src}
              controls
              autoPlay
              playsInline
              preload="metadata"
              crossOrigin="anonymous"
              className="aspect-video w-full bg-ink"
            >
              <track kind="captions" src={DEMO_VIDEO.captions} srcLang="en" label="English" />
            </video>
          </div>
        </div>
      )}
    </>
  );
}
