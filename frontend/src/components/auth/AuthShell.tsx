import Link from "next/link";
import type { ReactNode } from "react";

import { LogoLockup } from "@/components/brand/Logo";

interface AuthShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}

/**
 * Shared frame for sign-in and sign-up: a single focused column.
 *
 * The lockup is the only branding and doubles as the link home — a separate
 * header bar would repeat the wordmark twice on one short page.
 */
export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <main className="flex min-h-dvh items-center justify-center px-6 py-14">
      <div className="w-full max-w-sm">
        <Link href="/" aria-label="CEREBRO home" className="block">
          <LogoLockup compact priority />
        </Link>

        <div className="mt-10">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">{subtitle}</p>
        </div>

        <div className="mt-8">{children}</div>

        <div className="mt-7 border-t border-line pt-5 text-sm text-ink-muted">{footer}</div>
      </div>
    </main>
  );
}
