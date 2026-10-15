"use client";

import { usePathname } from "next/navigation";

import { NavigationItem } from "@/components/construct/NavigationItem";
import {
  IconDashboard,
  IconGalaxy,
  IconIngest,
  IconLibrary,
  IconLogout,
  IconProfile,
  IconSettings,
  IconRecall,
  IconSearch,
  IconTimeline,
  IconWhatIf,
} from "@/components/construct/icons";
import { cn } from "@/lib/cn";

interface SidebarProps {
  onLogout: () => void;
  loggingOut?: boolean;
  /** Controls the slide-in panel on small screens. */
  open?: boolean;
  onNavigate?: () => void;
}

export function Sidebar({ onLogout, loggingOut = false, open = false, onNavigate }: SidebarProps) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Workspace"
      className={cn(
        "flex w-60 shrink-0 flex-col border-r border-line bg-surface-subtle",
        // Off-canvas below lg, static above.
        "fixed inset-y-0 left-0 z-40 pt-16 transition-transform duration-200 lg:static lg:z-auto lg:translate-x-0 lg:pt-0",
        open ? "translate-x-0" : "-translate-x-full",
      )}
    >
      <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-3">
        <div className="flex flex-col gap-0.5">
          <NavigationItem
            label="Dashboard"
            icon={<IconDashboard />}
            href="/construct"
            active={pathname === "/construct"}
            onClick={onNavigate}
          />
        </div>

        <Group label="Knowledge">
          <NavigationItem label="Library" icon={<IconLibrary />} placeholder />
          <NavigationItem label="Ingest" icon={<IconIngest />} placeholder />
        </Group>

        <Group label="Retrieve">
          <NavigationItem label="Search" icon={<IconSearch />} placeholder />
          <NavigationItem label="Recall" icon={<IconRecall />} placeholder />
        </Group>

        <Group label="Visualise">
          <NavigationItem label="Timeline" icon={<IconTimeline />} placeholder />
          <NavigationItem label="Galaxy" icon={<IconGalaxy />} placeholder />
        </Group>

        <Group label="Explore">
          <NavigationItem label="What-If" icon={<IconWhatIf />} placeholder />
        </Group>
      </div>

      <div className="flex flex-col gap-0.5 border-t border-line p-3">
        <NavigationItem
          label="Profile"
          icon={<IconProfile />}
          href="/construct/profile"
          active={pathname === "/construct/profile"}
          onClick={onNavigate}
        />
        <NavigationItem
          label="Settings"
          icon={<IconSettings />}
          href="/construct/settings"
          active={pathname === "/construct/settings"}
          onClick={onNavigate}
        />
        <NavigationItem
          label={loggingOut ? "Signing out" : "Logout"}
          icon={<IconLogout />}
          onClick={onLogout}
        />
      </div>
    </nav>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <h2 className="px-2.5 pb-1 text-[0.6875rem] font-medium uppercase tracking-[0.1em] text-ink-subtle">
        {label}
      </h2>
      {children}
    </div>
  );
}
