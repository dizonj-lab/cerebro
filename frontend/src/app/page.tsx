import Link from "next/link";

import { BRAND, Logo, LogoLockup } from "@/components/brand/Logo";
import { Button } from "@/components/ui/Button";

const PILLARS = [
  { name: "Learn", detail: "CEREBRO takes in what you read, write, record and do." },
  { name: "Connect", detail: "Relationships form between everything you keep." },
  { name: "Reason", detail: "Ask questions that span your whole history." },
  { name: "Recall", detail: "Find the thing you half-remember, precisely." },
] as const;

export default function LandingPage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only-focusable absolute left-4 top-4 z-50 rounded-md bg-accent px-3 py-2 text-sm text-white"
      >
        Skip to content
      </a>

      <header className="border-b border-line">
        <nav
          aria-label="Primary"
          className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6"
        >
          <Logo priority />
          <div className="flex items-center gap-2">
            <Link href="/login">
              <Button variant="ghost">Sign In</Button>
            </Link>
            <Link href="/signup">
              <Button variant="primary">Create Account</Button>
            </Link>
          </div>
        </nav>
      </header>

      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-6">
        <section className="pt-20 pb-20 sm:pt-24 sm:pb-24">
          <LogoLockup className="mx-auto" showWordmark={false} priority />

          <h1 className="mx-auto mt-12 max-w-2xl text-center text-4xl font-semibold leading-[1.1] tracking-tight text-ink sm:text-5xl">
            Your knowledge, connected.
          </h1>

          <p className="mx-auto mt-5 max-w-xl text-center text-base leading-relaxed text-ink-muted">
            CEREBRO transforms your personal knowledge and experiences into a connected
            digital twin — private, searchable and entirely your own.
          </p>

          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link href="/signup">
              <Button variant="primary" size="lg">
                Create Account
              </Button>
            </Link>
            <Link href="/login">
              <Button variant="secondary" size="lg">
                Sign In
              </Button>
            </Link>
          </div>
        </section>

        <section aria-labelledby="pillars" className="border-t border-line py-14">
          <h2 id="pillars" className="sr-only">
            How CEREBRO works
          </h2>
          <ol className="grid gap-x-8 gap-y-9 sm:grid-cols-2 lg:grid-cols-4">
            {PILLARS.map((pillar, index) => (
              <li key={pillar.name}>
                <span className="font-mono text-xs text-ink-subtle">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-2 text-sm font-semibold text-ink">{pillar.name}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{pillar.detail}</p>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-6">
          <Logo markOnly className="opacity-60" size={22} />
          <p className="text-xs text-ink-subtle">{BRAND.tagline}</p>
          <p className="text-xs text-ink-subtle">Private by design.</p>
        </div>
      </footer>
    </div>
  );
}
