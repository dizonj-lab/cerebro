"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

import { NavigationItem } from "@/components/construct/NavigationItem";
import {
  IconAgents,
  IconCollections,
  IconDashboard,
  IconGalaxy,
  IconGodMode,
  IconHelp,
  IconIngest,
  IconLibrary,
  IconLogout,
  IconProfile,
  IconRecall,
  IconSearch,
  IconSettings,
  IconTags,
  IconTimeline,
} from "@/components/construct/icons";
import {
  godModeServerSnapshot,
  godModeSnapshot,
  setGodMode,
  subscribeGodMode,
} from "@/lib/godModeState";
import { cn } from "@/lib/cn";

interface SidebarProps {
  onLogout: () => void;
  loggingOut?: boolean;
  /** Controls the slide-in panel on small screens. */
  open?: boolean;
  onNavigate?: () => void;
  /** Rail mode on desktop: icons only, labels as tooltips. */
  collapsed?: boolean;
}

export function Sidebar({
  onLogout,
  loggingOut = false,
  open = false,
  onNavigate,
  collapsed = false,
}: SidebarProps) {
  const pathname = usePathname();
  const godMode = useSyncExternalStore(
    subscribeGodMode,
    godModeSnapshot,
    godModeServerSnapshot,
  );

  return (
    <nav
      aria-label="Workspace"
      className={cn(
        "flex shrink-0 flex-col border-r border-line bg-surface-subtle transition-[width] duration-200",
        // 240px expanded, 64px as a rail. The rail applies from tablet up:
        // below that the panel is off-canvas and always full width, because a
        // 64px drawer is not a navigation.
        collapsed ? "w-60 md:w-16" : "w-60 md:max-lg:w-16",
        // Off-canvas below md, static above: a tablet gets the rail rather
        // than a drawer, so navigation never covers the Galaxy.
        "fixed inset-y-0 left-0 z-40 pt-16 transition-transform duration-200 md:static md:z-auto md:translate-x-0 md:pt-0",
        open ? "translate-x-0" : "-translate-x-full",
      )}
    >
      <div className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-3">
        {PRIMARY.map((item) => (
          <NavigationItem
            key={item.label}
            label={item.label}
            icon={item.icon}
            href={item.href}
            placeholder={!item.href}
            active={item.href ? isActive(pathname, item.href) : false}
            onClick={item.href ? onNavigate : undefined}
            collapsed={collapsed}
          />
        ))}
        {/*
          GOD MODE is a tool rather than a destination: it opens a floating
          window over whatever the user is looking at, so it toggles here
          instead of navigating. The item reports that state, which is why it
          is not a placeholder and not a link.
        */}
        <NavigationItem
          label="GOD MODE"
          icon={<IconGodMode />}
          active={godMode.open}
          pressed={godMode.open}
          collapsed={collapsed}
          onClick={() =>
            setGodMode(
              godMode.open
                ? { open: false }
                : { open: true, mode: godMode.mode === "minimized" ? "normal" : godMode.mode },
            )
          }
        />
      </div>

      <div className="flex flex-col gap-0.5 border-t border-line p-3">
        <NavigationItem label="Profile" icon={<IconProfile />} href="/construct/profile"
          active={pathname === "/construct/profile"} onClick={onNavigate} collapsed={collapsed} />
        <NavigationItem label="Settings" icon={<IconSettings />} href="/construct/settings"
          active={pathname === "/construct/settings"} onClick={onNavigate} collapsed={collapsed} />
        <NavigationItem label="Help" icon={<IconHelp />} placeholder collapsed={collapsed} />
        <NavigationItem label={loggingOut ? "Signing out" : "Logout"} icon={<IconLogout />}
          onClick={onLogout} collapsed={collapsed} />
      </div>
    </nav>
  );
}

/**
 * The menu from the approved dashboard design.
 *
 * Items without an `href` are placeholders: the route does not exist yet, and
 * they announce themselves as unavailable rather than navigating nowhere. They
 * are not wired up here — that needs its own work package per CLAUDE.md.
 */
const PRIMARY = [
  { label: "Dashboard", icon: <IconDashboard />, href: "/construct" },
  { label: "Ingest", icon: <IconIngest />, href: "/construct/ingest" },
  { label: "Library", icon: <IconLibrary />, href: "/construct/library" },
  { label: "Search", icon: <IconSearch />, href: "/construct/search" },
  { label: "Galaxy", icon: <IconGalaxy />, href: "/construct/galaxy" },
  { label: "Timeline", icon: <IconTimeline />, href: "/construct/timeline" },
  { label: "Assisted Recollection", icon: <IconRecall /> },
  { label: "Collections", icon: <IconCollections /> },
  { label: "Tags", icon: <IconTags /> },
  { label: "Agents", icon: <IconAgents /> },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/construct" ? pathname === href : pathname.startsWith(href);
}
