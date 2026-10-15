"use client";

import { usePathname } from "next/navigation";

import { NavigationItem } from "@/components/construct/NavigationItem";
import {
  IconAgents,
  IconCollections,
  IconDashboard,
  IconGalaxy,
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

  return (
    <nav
      aria-label="Workspace"
      className={cn(
        "flex shrink-0 flex-col border-r border-line bg-surface-subtle transition-[width] duration-200",
        // The rail only applies on desktop: the off-canvas panel is always
        // full width, because a 56px drawer is not a navigation.
        collapsed ? "w-60 lg:w-[4.25rem]" : "w-60",
        // Off-canvas below lg, static above.
        "fixed inset-y-0 left-0 z-40 pt-16 transition-transform duration-200 lg:static lg:z-auto lg:translate-x-0 lg:pt-0",
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
  { label: "Search", icon: <IconSearch /> },
  { label: "Galaxy", icon: <IconGalaxy /> },
  { label: "Timeline", icon: <IconTimeline /> },
  { label: "Assisted Recollection", icon: <IconRecall /> },
  { label: "Collections", icon: <IconCollections /> },
  { label: "Tags", icon: <IconTags /> },
  { label: "Agents", icon: <IconAgents /> },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/construct" ? pathname === href : pathname.startsWith(href);
}
