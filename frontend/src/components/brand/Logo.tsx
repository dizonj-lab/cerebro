import { cn } from "@/lib/cn";

interface LogoProps {
  /** Hides the wordmark, leaving only the mark. */
  markOnly?: boolean;
  className?: string;
}

/**
 * CEREBRO brand lockup: a small node-and-link mark suggesting connected
 * knowledge, set beside the wordmark.
 */
export function Logo({ markOnly = false, className }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg viewBox="0 0 24 24" className="size-6 text-accent" fill="none" aria-hidden="true">
        <path
          d="M12 4.2 6 7.5v6l6 3.3 6-3.3v-6l-6-3.3Z"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
          opacity="0.45"
        />
        <circle cx="12" cy="4.2" r="1.7" fill="currentColor" />
        <circle cx="6" cy="13.5" r="1.7" fill="currentColor" />
        <circle cx="18" cy="13.5" r="1.7" fill="currentColor" />
        <circle cx="12" cy="19.8" r="1.7" fill="currentColor" opacity="0.55" />
      </svg>
      {!markOnly && (
        <span className="text-[0.9375rem] font-semibold tracking-[0.14em] text-ink">
          CEREBRO
        </span>
      )}
    </span>
  );
}
