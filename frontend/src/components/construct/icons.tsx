/**
 * Simple line icons for Construct navigation. Uniform 20px grid, 1.5 stroke,
 * inheriting currentColor so they take the nav item's state colour.
 */
import type { SVGProps } from "react";

function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="size-[18px] shrink-0"
      {...props}
    >
      {children}
    </svg>
  );
}

export const IconDashboard = () => (
  <Icon>
    <rect x="2.75" y="2.75" width="6" height="6" rx="1.25" />
    <rect x="11.25" y="2.75" width="6" height="6" rx="1.25" />
    <rect x="2.75" y="11.25" width="6" height="6" rx="1.25" />
    <rect x="11.25" y="11.25" width="6" height="6" rx="1.25" />
  </Icon>
);

export const IconLibrary = () => (
  <Icon>
    <path d="M3.5 4.5v11M7 3.75v12.5M10.5 4.25l4.75 11.25" />
    <path d="M3.5 15.5h13" />
  </Icon>
);

export const IconIngest = () => (
  <Icon>
    <path d="M10 13V3.5M10 3.5 6.75 6.75M10 3.5l3.25 3.25" />
    <path d="M3.5 12.5v2.75a1.25 1.25 0 0 0 1.25 1.25h10.5a1.25 1.25 0 0 0 1.25-1.25V12.5" />
  </Icon>
);

export const IconSearch = () => (
  <Icon>
    <circle cx="8.75" cy="8.75" r="5" />
    <path d="m12.5 12.5 4 4" />
  </Icon>
);

export const IconRecall = () => (
  <Icon>
    <circle cx="10" cy="10" r="7" />
    <path d="M10 5.75V10l2.75 1.75" />
  </Icon>
);

export const IconTimeline = () => (
  <Icon>
    <path d="M3 10h14" />
    <circle cx="6" cy="10" r="1.75" />
    <circle cx="13" cy="10" r="1.75" />
  </Icon>
);

export const IconGalaxy = () => (
  <Icon>
    <circle cx="10" cy="10" r="2" />
    <circle cx="4.5" cy="5.5" r="1.5" />
    <circle cx="15.5" cy="6" r="1.5" />
    <circle cx="6" cy="15" r="1.5" />
    <path d="m8.6 8.6-2.7-2.1M11.7 9.2l2.5-2M9.3 11.8 6.8 13.7" />
  </Icon>
);

export const IconWhatIf = () => (
  <Icon>
    <path d="M10 3.5v3.25M10 16.5v-3.25" />
    <circle cx="10" cy="10" r="3.25" />
    <path d="M4.5 6.75 7.3 8.4M15.5 13.25 12.7 11.6" />
  </Icon>
);

export const IconProfile = () => (
  <Icon>
    <circle cx="10" cy="7" r="3" />
    <path d="M4 16.25a6 6 0 0 1 12 0" />
  </Icon>
);

export const IconLogout = () => (
  <Icon>
    <path d="M12 6.5V4.75A1.25 1.25 0 0 0 10.75 3.5h-6A1.25 1.25 0 0 0 3.5 4.75v10.5a1.25 1.25 0 0 0 1.25 1.25h6A1.25 1.25 0 0 0 12 15.25V13.5" />
    <path d="M8 10h8.5M16.5 10l-2.25-2.25M16.5 10l-2.25 2.25" />
  </Icon>
);

export const IconSettings = () => (
  <Icon>
    <circle cx="10" cy="10" r="2.5" />
    <path d="M10 2.75v1.6M10 15.65v1.6M17.25 10h-1.6M4.35 10h-1.6M15.13 4.87l-1.13 1.13M6 14l-1.13 1.13M15.13 15.13 14 14M6 6 4.87 4.87" />
  </Icon>
);

/** Added for the dashboard shell. Same 20x20 stroke grid as the rest. */
export const IconCollections = () => (
  <Icon>
    <path d="M3.5 6.5h13v9a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1z" />
    <path d="M5.5 4.5h9M6.5 2.5h7" />
  </Icon>
);

export const IconTags = () => (
  <Icon>
    <path d="M10.5 3.5H16a.5.5 0 0 1 .5.5v5.5L9 17 3 11z" />
    <circle cx="13" cy="7" r="1" />
  </Icon>
);

export const IconAgents = () => (
  <Icon>
    <rect x="4.5" y="7" width="11" height="8" rx="2" />
    <path d="M10 4.5V7M7.5 11h.01M12.5 11h.01" />
  </Icon>
);

// A signal trace: what the window shows is activity over time. It replaced
// a sun, which was a joke about the old name and meant nothing about the
// contents.
export const IconTelemetry = () => (
  <Icon>
    <path d="M2.5 10h3l2-5 3 10 2.5-6 1.5 3h3" />
  </Icon>
);

export const IconHelp = () => (
  <Icon>
    <circle cx="10" cy="10" r="7" />
    <path d="M8.2 8a1.9 1.9 0 1 1 2.6 1.8c-.5.2-.8.6-.8 1.1v.4M10 14h.01" />
  </Icon>
);

export const IconBell = () => (
  <Icon>
    <path d="M6 8.5a4 4 0 1 1 8 0c0 2.5.6 3.6 1.2 4.3.3.3.1.7-.3.7H5.1c-.4 0-.6-.4-.3-.7C5.4 12.1 6 11 6 8.5Z" />
    <path d="M8.5 16a1.7 1.7 0 0 0 3 0" />
  </Icon>
);

export const IconPlus = () => (
  <Icon>
    <path d="M10 4.5v11M4.5 10h11" />
  </Icon>
);
