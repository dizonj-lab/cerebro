"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { DEMO_VIDEO } from "@/lib/demo";

/**
 * "Watch demo": the five-minute narrated tour, played in a dialog over the page.
 *
 * The video loads only when opened, starts playing, and stops when closed
 * (the element is removed). Escape, the close button or a click outside closes it.
 *
 * The video carries no `crossOrigin`: as plain cross-origin media it plays
 * whatever headers the host or its CDN send. The subtitles are fetched
 * separately and handed to the track as a same-origin blob; if that fails
 * the video plays without them. If the video itself cannot load, folio's
 * player is offered instead.
 */
export function WatchDemo({ size = "lg" }: { size?: "md" | "lg" }) {
  const [open, setOpen] = useState(false);
  const close = useRef<HTMLButtonElement>(null);
  const [captions, setCaptions] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let url: string | null = null;
    let cancelled = false;
    fetch(DEMO_VIDEO.captions)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((text) => {
        if (cancelled) return;
        url = URL.createObjectURL(new Blob([text], { type: "text/vtt" }));
        setCaptions(url);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
      setCaptions(null);
      setFailed(false);
    };
  }, [open]);

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
            {failed ? (
              <div className="flex aspect-video w-full flex-col items-center justify-center gap-3 bg-surface-subtle p-6 text-center">
                <p className="text-sm text-ink-muted">The video could not load here.</p>
                <a
                  href={DEMO_VIDEO.page}
                  target="_blank"
                  rel="noopener"
                  className="text-sm font-medium text-accent underline underline-offset-4"
                >
                  Watch it on folio.xtangent.ai
                </a>
              </div>
            ) : (
              <video
                data-testid="demo-video"
                src={DEMO_VIDEO.src}
                controls
                autoPlay
                playsInline
                preload="metadata"
                onError={() => setFailed(true)}
                className="aspect-video w-full bg-ink"
              >
                {captions && <track kind="captions" src={captions} srcLang="en" label="English" default />}
              </video>
            )}
          </div>
        </div>
      )}
    </>
  );
}
