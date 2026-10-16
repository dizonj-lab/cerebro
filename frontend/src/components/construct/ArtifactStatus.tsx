import { cn } from "@/lib/cn";

const LABELS: Record<string, { label: string; tone: string }> = {
  // Stored, not yet read. Distinct from "Awaiting review" on purpose: there
  // is nothing to review yet, and defaulting to that label would invite a
  // user to approve metadata that has not been proposed.
  processing: { label: "Reading", tone: "border-line-strong bg-surface-subtle text-ink-subtle" },
  inspected: { label: "Awaiting review", tone: "border-line-strong bg-surface-subtle text-ink-muted" },
  registered: { label: "Registered", tone: "border-accent/25 bg-accent-subtle text-accent" },
  approved: { label: "Approved", tone: "border-accent/25 bg-accent-subtle text-accent" },
  rejected: { label: "Rejected", tone: "border-danger/25 bg-danger-subtle text-danger" },
};

/** Lifecycle badge. Registered is the only state that means trusted. */
export function ArtifactStatus({ status, className }: { status: string; className?: string }) {
  const { label, tone } = LABELS[status] ?? LABELS.inspected;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5",
        "text-[0.65rem] font-medium uppercase tracking-[0.08em]",
        tone,
        className,
      )}
    >
      {label}
    </span>
  );
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
