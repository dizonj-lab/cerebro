import { cn } from "@/lib/cn";

/**
 * Profile completion. The percentage is computed server-side over a fixed
 * field list, so this only renders what it is given.
 */
export function CompletionMeter({
  percent,
  completed,
  total,
  className,
}: {
  percent: number;
  completed: number;
  total: number;
  className?: string;
}) {
  return (
    <div className={cn("w-full", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium text-ink-muted">Profile completion</span>
        <span className="font-mono text-sm font-medium tabular-nums text-ink">{percent}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Profile completion"
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken"
      >
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-ink-subtle">
        {completed} of {total} fields
      </p>
    </div>
  );
}
