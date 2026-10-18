"use client";

import type { CerebroEnrichmentQueue } from "@/lib/api";
import { describeJob } from "@/lib/useEnrichmentQueue";
import { cn } from "@/lib/cn";

/**
 * What the local model is working on, and what is waiting behind it.
 *
 * Shown wherever the user might be: the queue belongs to the server, not to
 * the page that started it, so the Library and Ingest both render this and
 * agree. A waiting document says how many are ahead of it, because "waiting"
 * without a number is indistinguishable from stuck.
 */
export function EnrichmentQueue({
  queue,
  className,
}: {
  queue: CerebroEnrichmentQueue | null;
  className?: string;
}) {
  if (!queue || queue.jobs.length === 0) return null;

  return (
    <section
      data-testid="enrichment-queue"
      className={cn("rounded-xl border border-border bg-surface-subtle p-3", className)}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-medium text-ink">
          Local AI is reading {queue.running} document{queue.running === 1 ? "" : "s"}
          {queue.waiting > 0 && `, ${queue.waiting} waiting`}
        </p>
        {/* Says why the rest are waiting, so a queue does not read as a
            stall. One model on one machine is the reason. */}
        <p className="text-[0.6875rem] text-ink-subtle">
          Up to {queue.max_concurrent} at a time
        </p>
      </div>

      <ul className="mt-2 space-y-1.5">
        {queue.jobs.map((job) => {
          const fraction =
            job.status === "running" && job.total
              ? Math.min(1, job.progress / job.total)
              : 0;
          return (
            <li key={job.artifact_id} data-testid="enrichment-job">
              <div className="flex items-baseline justify-between gap-3 text-[0.6875rem]">
                <span className="truncate text-ink">{job.filename}</span>
                <span className="shrink-0 text-ink-subtle">{describeJob(job)}</span>
              </div>
              <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-surface-sunken">
                <div
                  className={cn(
                    "h-full rounded-full transition-[width] duration-500",
                    job.status === "running" ? "bg-accent" : "bg-ink-subtle/30",
                  )}
                  // A queued job shows an empty track rather than a guess at
                  // how far along it is not yet.
                  style={{ width: `${Math.round(fraction * 100)}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
