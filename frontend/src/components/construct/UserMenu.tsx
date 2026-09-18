"use client";

import { useEffect, useRef, useState } from "react";

import Link from "next/link";

import { IconLogout, IconProfile, IconSettings } from "@/components/construct/icons";
import type { CerebroUser } from "@/lib/api";

interface UserMenuProps {
  user: CerebroUser;
  onLogout: () => void;
  loggingOut?: boolean;
}

export function UserMenu({ user, onLogout, loggingOut = false }: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const initials = user.display_name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded-md px-1.5 py-1 text-sm text-ink-muted transition-colors hover:bg-surface-subtle"
      >
        <span
          aria-hidden="true"
          className="grid size-7 place-items-center rounded-full bg-accent-subtle text-xs font-semibold text-accent"
        >
          {initials || "?"}
        </span>
        <span className="hidden max-w-[10rem] truncate sm:inline">{user.display_name}</span>
        <span className="sr-only">Account menu</span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-1.5 w-56 rounded-lg border border-line bg-surface py-1 shadow-card"
        >
          <div className="border-b border-line px-3 py-2.5">
            <p className="truncate text-sm font-medium text-ink">{user.display_name}</p>
            <p className="truncate text-xs text-ink-subtle">{user.email}</p>
          </div>

          <Link
            href="/construct/profile"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-ink-muted hover:bg-surface-subtle hover:text-ink"
          >
            <IconProfile />
            Profile
          </Link>

          <Link
            href="/construct/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-ink-muted hover:bg-surface-subtle hover:text-ink"
          >
            <IconSettings />
            Settings
          </Link>

          <button
            type="button"
            role="menuitem"
            onClick={onLogout}
            disabled={loggingOut}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-ink-muted hover:bg-surface-subtle hover:text-ink disabled:opacity-55"
          >
            <IconLogout />
            {loggingOut ? "Signing out" : "Logout"}
          </button>
        </div>
      )}
    </div>
  );
}
