"use client";

import Link from "next/link";

import { Logo } from "@/components/brand/Logo";
import { IconBell, IconPlus, IconSettings } from "@/components/construct/icons";
import { UserMenu } from "@/components/construct/UserMenu";
import type { CerebroUser } from "@/lib/api";

interface ConstructHeaderProps {
  user: CerebroUser;
  onLogout: () => void;
  loggingOut?: boolean;
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
  /** Desktop rail toggle. Separate from the mobile off-canvas state. */
  onToggleRail?: () => void;
  railCollapsed?: boolean;
}

export function ConstructHeader({
  user,
  onLogout,
  loggingOut,
  onToggleSidebar,
  sidebarOpen,
  onToggleRail,
  railCollapsed = false,
}: ConstructHeaderProps) {
  return (
    <header className="sticky top-0 z-50 flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface px-4 sm:px-6">
      <button
        type="button"
        onClick={onToggleSidebar}
        data-testid="sidebar-toggle"
        aria-expanded={sidebarOpen}
        aria-label={sidebarOpen ? "Close navigation" : "Open navigation"}
        className="-ml-1 rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-subtle lg:hidden"
      >
        <svg viewBox="0 0 20 20" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
          <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
        </svg>
      </button>

      {onToggleRail && (
        <button
          type="button"
          onClick={onToggleRail}
          aria-expanded={!railCollapsed}
          aria-label={railCollapsed ? "Expand navigation" : "Collapse navigation"}
          className="hidden rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-subtle lg:block"
        >
          <svg viewBox="0 0 20 20" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
            <rect x="2.75" y="3.75" width="14.5" height="12.5" rx="2" />
            <path d="M7.75 3.75v12.5" />
          </svg>
        </button>
      )}

      <Logo />

      {/*
        Global search. A form rather than a decorative box: it submits to the
        search page, which is where the existing retrieval service lives.
      */}
      <form
        action="/construct/search"
        role="search"
        className="mx-auto hidden w-full max-w-md items-center gap-2 rounded-lg border border-line bg-surface-subtle px-3 py-2 text-sm focus-within:border-accent md:flex"
      >
        <svg viewBox="0 0 20 20" className="size-4 shrink-0 text-ink-subtle" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <circle cx="8.75" cy="8.75" r="5" />
          <path d="m12.5 12.5 4 4" strokeLinecap="round" />
        </svg>
        <input
          type="search"
          name="q"
          aria-label="Search your knowledge"
          placeholder="Search your knowledge..."
          className="w-full bg-transparent text-ink outline-none placeholder:text-ink-subtle"
        />
      </form>

      <div className="ml-auto flex items-center gap-1.5">
        {/* The existing ingestion route. No second pipeline. */}
        <Link
          href="/construct/ingest"
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-ink shadow-subtle transition-colors hover:bg-accent-hover"
        >
          <span className="size-4"><IconPlus /></span>
          <span className="hidden sm:inline">Ingest</span>
        </Link>

        {/*
          Notifications has no backend. It is rendered as unavailable rather
          than as an empty bell that looks like "nothing new" — and it never
          shows a badge, which would be a fabricated count.
        */}
        <button
          type="button"
          aria-disabled="true"
          title="Notifications — coming soon"
          className="hidden rounded-md p-2 text-ink-subtle transition-colors hover:bg-surface-subtle sm:block"
        >
          <span className="sr-only">Notifications (coming soon)</span>
          <span className="block size-5"><IconBell /></span>
        </button>

        <Link
          href="/construct/settings"
          className="hidden rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-subtle hover:text-ink sm:block"
        >
          <span className="sr-only">Settings</span>
          <span className="block size-5"><IconSettings /></span>
        </Link>

        <UserMenu user={user} onLogout={onLogout} loggingOut={loggingOut} />
      </div>
    </header>
  );
}
