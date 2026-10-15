"use client";

import { Logo } from "@/components/brand/Logo";
import { UserMenu } from "@/components/construct/UserMenu";
import type { CerebroUser } from "@/lib/api";

interface ConstructHeaderProps {
  user: CerebroUser;
  onLogout: () => void;
  loggingOut?: boolean;
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
}

export function ConstructHeader({
  user,
  onLogout,
  loggingOut,
  onToggleSidebar,
  sidebarOpen,
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

      <Logo />

      <div className="ml-auto flex items-center gap-2">
        {/* Search is part of the shell's shape but not wired up in this milestone. */}
        <div className="hidden items-center gap-2 rounded-md border border-line bg-surface-subtle px-2.5 py-1.5 text-sm text-ink-subtle sm:flex">
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <circle cx="8.75" cy="8.75" r="5" />
            <path d="m12.5 12.5 4 4" strokeLinecap="round" />
          </svg>
          <span>Search</span>
        </div>

        <UserMenu user={user} onLogout={onLogout} loggingOut={loggingOut} />
      </div>
    </header>
  );
}
