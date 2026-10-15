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
}

export function NavigationItem({
  label,
  icon,
  active = false,
  placeholder = false,
  onClick,
  nested = false,
  href,
}: NavigationItemProps) {
  const classes = cn(
    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm",
    "transition-colors duration-150",
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
        className={classes}
      >
        {!nested && icon}
        <span className="truncate">{label}</span>
      </Link>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      aria-disabled={placeholder || undefined}
      title={placeholder ? `${label} — coming soon` : undefined}
      className={classes}
    >
      {!nested && icon}
      <span className="truncate">{label}</span>
    </button>
  );
}
