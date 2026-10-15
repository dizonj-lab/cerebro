/**
 * Dashboard primitives.
 *
 * Cards, headers and skeletons shared by every panel, so the panels differ in
 * content rather than in chrome. All colour comes from tokens, which is what
 * makes the dark theme work without a second set of components.
 */
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section
      className={cn(
        "rounded-xl border border-line bg-surface p-4 shadow-subtle",
        "transition-colors duration-150",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  action,
  href,
}: {
  title: string;
  action?: string;
  href?: string;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="truncate text-sm font-semibold whitespace-nowrap text-ink">{title}</h2>
      {action &&
        (href ? (
          <Link
            href={href}
            className="inline-flex shrink-0 items-center gap-1 rounded text-xs font-medium whitespace-nowrap text-accent underline-offset-2 hover:underline"
          >
            {action}
            <Arrow />
          </Link>
        ) : (
          <span
            title={`${action} — coming soon`}
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium whitespace-nowrap text-ink-subtle"
          >
            {action}
            <Arrow />
          </span>
        ))}
    </div>
  );
}

function Arrow() {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M3 8h10M9 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A neutral placeholder while the one dashboard request is in flight. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-sunken", className)} />;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="py-6 text-center text-xs leading-relaxed text-ink-subtle">{children}</p>
  );
}
