import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/brand/Logo";

interface AuthShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}

/** Shared frame for the sign-in and sign-up pages: focused, single column. */
export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center px-6">
          <Link href="/" aria-label="CEREBRO home">
            <Logo />
          </Link>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-6 py-14">
        <div className="w-full max-w-sm">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">{subtitle}</p>

          <div className="mt-8">{children}</div>

          <div className="mt-7 border-t border-line pt-5 text-sm text-ink-muted">{footer}</div>
        </div>
      </main>
    </div>
  );
}
