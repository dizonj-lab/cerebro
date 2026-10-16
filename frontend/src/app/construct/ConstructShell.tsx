"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";

import { ConstructHeader } from "@/components/construct/ConstructHeader";
import { Sidebar } from "@/components/construct/Sidebar";
import { api } from "@/lib/api";
import {
  railServerSnapshot,
  railSnapshot,
  setRailCollapsed,
  subscribeRail,
} from "@/lib/railState";
import type { CerebroUser } from "@/lib/api";

interface ConstructShellProps {
  user: CerebroUser;
  children: React.ReactNode;
}

/** The authenticated application shell: header, sidebar, workspace. */
export function ConstructShell({ user, children }: ConstructShellProps) {
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const pathname = usePathname();
  const preference = useSyncExternalStore(subscribeRail, railSnapshot, railServerSnapshot);

  /*
    The Galaxy and its timeline want the whole screen, so they open railed —
    but only until the user has expressed a width of their own, which is
    stored and then wins on every route.

    Derived during render rather than set from an effect: an effect would
    collapse the sidebar a frame after the page appeared, and the
    visualisation would resize twice on every visit.
  */
  const visualisation = pathname.startsWith("/construct/galaxy");
  const railCollapsed = preference === null ? visualisation : preference === "collapsed";

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await api.logout();
    } catch {
      // Even if the call fails, send the user back to the public experience;
      // the cookie is cleared server-side on any successful response and the
      // next protected request will be rejected regardless.
    }
    router.replace("/");
    router.refresh();
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <ConstructHeader
        user={user}
        onLogout={handleLogout}
        loggingOut={loggingOut}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        railCollapsed={railCollapsed}
        onToggleRail={() => setRailCollapsed(!railCollapsed)}
      />

      <div className="flex flex-1">
        <Sidebar
          onLogout={handleLogout}
          loggingOut={loggingOut}
          open={sidebarOpen}
          onNavigate={() => setSidebarOpen(false)}
          collapsed={railCollapsed}
        />

        {/*
          Scrim for the off-canvas sidebar. Decorative and hidden from the
          accessibility tree: the header toggle is the labelled control, so the
          scrim must not duplicate its accessible name or add a tab stop.
        */}
        {sidebarOpen && (
          <div
            aria-hidden="true"
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-30 bg-ink/20 md:hidden"
          />
        )}

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
