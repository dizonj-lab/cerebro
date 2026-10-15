import { cn } from "@/lib/cn";

interface ErrorMessageProps {
  children?: string | null;
  className?: string;
}

/** Form-level error banner. Renders nothing when there is no message. */
export function ErrorMessage({ children, className }: ErrorMessageProps) {
  if (!children) return null;

  return (
    <div
      role="alert"
      data-testid="form-error"
      className={cn(
        "flex items-start gap-2 rounded-md border border-danger/25 bg-danger-subtle",
        "px-3 py-2.5 text-sm text-danger",
        className,
      )}
    >
      <svg viewBox="0 0 16 16" className="mt-0.5 size-4 shrink-0" fill="none" aria-hidden="true">
        <circle cx="8" cy="8" r="6.75" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 4.75v3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11" r="0.85" fill="currentColor" />
      </svg>
      <span>{children}</span>
    </div>
  );
}
