import Image from "next/image";

import { cn } from "@/lib/cn";

/**
 * CEREBRO brand lockup.
 *
 * The artwork is the supplied head-and-network mark at
 * `public/brand/cerebro-mark.png`, cropped from the master lockup with its
 * white matte removed so it sits on any surface. The wordmark is set in type
 * rather than baked into the image, so it stays crisp at every size, inherits
 * the ink token, and remains selectable and searchable.
 *
 * Two compositions:
 *   <Logo />        mark + wordmark            — app chrome, tight vertical space
 *   <LogoLockup />  mark + wordmark + tagline  — landing and auth pages
 */

export const BRAND = {
  name: "CEREBRO",
  tagline: "Adaptive Knowledge and Reasoning Digital Twin",
  pillars: ["Learn", "Connect", "Reason", "Recall"] as const,
} as const;

const MARK_SRC = "/brand/cerebro-mark.png";

interface LogoMarkProps {
  size?: number;
  className?: string;
  priority?: boolean;
}

export function LogoMark({ size = 24, className, priority = false }: LogoMarkProps) {
  return (
    <Image
      src={MARK_SRC}
      alt=""
      width={size}
      height={size}
      priority={priority}
      aria-hidden="true"
      className={cn("shrink-0 select-none", className)}
    />
  );
}

interface LogoProps {
  /** Renders the mark alone, without the wordmark. */
  markOnly?: boolean;
  size?: number;
  className?: string;
  priority?: boolean;
}

export function Logo({ markOnly = false, size = 30, className, priority }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark size={size} priority={priority} />
      {!markOnly && (
        <span className="text-[0.9375rem] font-semibold tracking-[0.14em] text-ink">
          {BRAND.name}
        </span>
      )}
      {markOnly && <span className="sr-only">{BRAND.name}</span>}
    </span>
  );
}

interface LogoLockupProps {
  className?: string;
  /** Hides the pillar strip; the tagline is always shown. */
  compact?: boolean;
  /**
   * Set false where the wordmark already appears nearby — the landing header
   * carries it, so repeating it in the hero reads as duplication.
   */
  showWordmark?: boolean;
  priority?: boolean;
}

/** Full lockup: mark, wordmark, tagline and (optionally) the pillar strip. */
export function LogoLockup({
  className,
  compact = false,
  showWordmark = true,
  priority,
}: LogoLockupProps) {
  return (
    <div className={cn("flex flex-col items-center text-center", className)}>
      {/* The supplied mark carries fine detail — the network nodes and the
          strands through the head — so it needs more room than a simple glyph
          would to stay legible. */}
      <LogoMark size={compact ? 76 : 112} priority={priority} />

      {showWordmark && (
        <p className="mt-4 text-2xl font-semibold tracking-[0.18em] text-ink sm:text-[1.75rem]">
          {BRAND.name}
        </p>
      )}

      <p className={cn("text-sm text-ink-muted", showWordmark ? "mt-1.5" : "mt-4")}>
        {BRAND.tagline}
      </p>

      {!compact && (
        <ul className="mt-3 flex flex-wrap items-center justify-center gap-x-2.5 gap-y-1 text-[0.6875rem] font-medium uppercase tracking-[0.16em] text-ink-subtle">
          {BRAND.pillars.map((pillar, index) => (
            <li key={pillar} className="flex items-center gap-2.5">
              {index > 0 && (
                <span aria-hidden="true" className="size-1 rounded-full bg-accent/50" />
              )}
              {pillar}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
