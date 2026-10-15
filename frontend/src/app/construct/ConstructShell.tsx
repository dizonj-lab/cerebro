"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConstructHeader } from "@/components/construct/ConstructHeader";
import { Sidebar } from "@/components/construct/Sidebar";
import { api } from "@/lib/api";
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
      />

      <div className="flex flex-1">
        <Sidebar
          onLogout={handleLogout}
          loggingOut={loggingOut}
          open={sidebarOpen}
          onNavigate={() => setSidebarOpen(false)}
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
            className="fixed inset-0 z-30 bg-ink/20 lg:hidden"
          />
        )}

        <main className="flex-1 px-6 py-10 sm:px-10">{children}</main>
      </div>
    </div>
  );
}
