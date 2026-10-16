"use client";

import Link from "next/link";

import { Logo } from "@/components/brand/Logo";
import { IconBell, IconPlus, IconSettings } from "@/components/construct/icons";
import { ThemeToggle } from "@/components/construct/ThemeToggle";
import { GodModeLauncher } from "@/components/godmode/GodModeLauncher";
import { UserMenu } from "@/components/construct/UserMenu";
import { GlobalSearch } from "@/components/search/GlobalSearch";
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
        className="-ml-1 rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-subtle md:hidden"
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
          className="hidden rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-subtle md:block"
        >
          <svg viewBox="0 0 20 20" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
            <rect x="2.75" y="3.75" width="14.5" height="12.5" rx="2" />
            <path d="M7.75 3.75v12.5" />
          </svg>
        </button>
      )}

      <Logo />

      <GlobalSearch />

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

        <GodModeLauncher />

        <ThemeToggle />

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
