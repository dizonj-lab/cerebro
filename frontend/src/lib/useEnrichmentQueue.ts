"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { CerebroEnrichmentQueue } from "@/lib/api";

/**
 * The enrichment queue, polled.
 *
 * Enrichment runs server-side now, so progress is something to read rather
 * than something a page owns. That is the whole point: this hook can be
 * mounted on the Library, on Ingest, or on both at once, and every one of
 * them sees the same jobs — including jobs started before the page was
 * opened, which is what leaving the page used to destroy.
 *
 * Polling stops when nothing is running, so an idle library makes no
 * requests, and restarts as soon as something is queued.
 */
const ACTIVE_MS = 1500;
const IDLE_MS = 6000;

export function useEnrichmentQueue(enabled = true) {
  const [queue, setQueue] = useState<CerebroEnrichmentQueue | null>(null);
  // Bumped to force an immediate re-poll after queueing something, rather
  // than waiting out the current tick.
  const [nonce, setNonce] = useState(0);
  const active = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    // An interval rather than a self-rescheduling callback: the latter is a
    // function that has to reference itself, which React's rules of hooks
    // rightly refuse. The rate follows whether anything is running, so an
    // idle library is nearly silent instead of polling every 1.5s forever.
    async function tick() {
      try {
        const next = await api.enrichmentQueue();
        if (cancelled) return;
        setQueue(next);
        active.current = next.jobs.length > 0;
      } catch {
        // A failed poll is not worth an error banner: the next one may
        // work, and the job is server-side and unaffected either way.
      }
    }

    void tick();
    // Fast while anything is running, and fast right after the user queued
    // something — a job can finish between the enqueue and the first poll,
    // and at the idle rate the page would sit on a spinner for seconds
    // after the work was already done.
    const rate = active.current || nonce > 0 ? ACTIVE_MS : IDLE_MS;
    const handle = setInterval(() => {
      void tick();
    }, rate);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [enabled, nonce, queue?.jobs.length]);

  /** Call after queueing something, so the next tick is immediate. */
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return { queue, refresh, busy: (queue?.jobs.length ?? 0) > 0 };
}

/** One job's progress as a sentence, or null when there is nothing to say. */
export function describeJob(job: {
  status: string;
  progress: number;
  total: number | null;
  position: number;
}): string {
  if (job.status === "queued") {
    return job.position > 0 ? `Waiting — ${job.position} ahead` : "Waiting to start";
  }
  if (!job.total) return "Reading the document…";
  return `Reading section ${Math.min(job.progress + 1, job.total)} of ${job.total}`;
}
