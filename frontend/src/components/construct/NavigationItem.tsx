"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface NavigationItemProps {
  label: string;
  icon: ReactNode;
  active?: boolean;
  /**
   * Placeholder items are visible but not yet wired to a destination. They stay
   * in the tab order and announce their state rather than silently doing nothing.
   */
  placeholder?: boolean;
  onClick?: () => void;
  nested?: boolean;
  /** When set the item navigates; otherwise it is a button. */
  href?: string;
  /**
   * Rail mode: the label is hidden visually but kept for screen readers, and
   * the native tooltip carries it for sighted users.
   */
  collapsed?: boolean;
}

export function NavigationItem({
  label,
  icon,
  active = false,
  placeholder = false,
  onClick,
  nested = false,
  href,
  collapsed = false,
}: NavigationItemProps) {
  const classes = cn(
    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm",
    "transition-colors duration-150",
    // The off-canvas panel below tablet keeps its labels; from tablet up the
    // item centres its icon whenever it is a rail.
    collapsed ? "md:justify-center md:px-0" : "md:max-lg:justify-center md:max-lg:px-0",
    nested && "pl-9",
    active
      ? "bg-accent-subtle font-medium text-accent"
      : placeholder
        ? "text-ink-subtle hover:bg-surface-subtle"
        : "text-ink-muted hover:bg-surface-subtle hover:text-ink",
  );

  if (href) {
    return (
      <Link
        href={href}
        onClick={onClick}
        aria-current={active ? "page" : undefined}
        // The tooltip is what names a rail icon for a sighted user; the
        // label itself stays in the accessible name either way.
        title={label}
        className={classes}
      >
        {!nested && icon}
        <span className={cn("truncate", collapsed ? "md:sr-only" : "md:max-lg:sr-only")}>
          {label}
        </span>
      </Link>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      aria-disabled={placeholder || undefined}
      title={placeholder ? `${label} — coming soon` : label}
      className={classes}
    >
      {!nested && icon}
      <span className={cn("truncate", collapsed ? "md:sr-only" : "md:max-lg:sr-only")}>
        {label}
      </span>
    </button>
  );
}
