import { cn } from "@/lib/cn";
import type { ReactNode } from "react";

interface FormFieldProps {
  /** Must match the id of the control it wraps, so the label is programmatic. */
  htmlFor: string;
  label: string;
  error?: string;
  hint?: string;
  /**
   * A short word for where this value came from, shown beside the label.
   *
   * The hint underneath already says it, but a reviewer scanning a form of
   * twelve fields reads labels, not hints — and the one thing they need at
   * a glance is which boxes a model filled, because those are the ones to
   * check. Carried as a separate prop rather than parsed out of `hint` so
   * the mark is a deliberate claim about provenance.
   */
  origin?: { label: string; tone: "ai" | "document" | "confirmed" };
  children: ReactNode;
  className?: string;
}

export function FormField({
  htmlFor,
  label,
  error,
  hint,
  origin,
  children,
  className,
}: FormFieldProps) {
  const errorId = `${htmlFor}-error`;
  const hintId = `${htmlFor}-hint`;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
          {label}
        </label>
        {origin && (
          <span
            data-testid={`origin-${htmlFor}`}
            data-origin={origin.tone}
            className={cn(
              "rounded-full px-1.5 py-0.5 text-[0.625rem] font-medium",
              origin.tone === "ai"
                ? "bg-accent/15 text-accent"
                : "bg-surface-sunken text-ink-subtle",
            )}
          >
            {origin.label}
          </span>
        )}
      </div>
      {children}
      {hint && !error && (
        <p id={hintId} className="text-xs text-ink-subtle">
          {hint}
        </p>
      )}
      {error && (
        // role="alert" so the message is announced the moment it appears.
        <p id={errorId} role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
