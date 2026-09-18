"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/construct/PageHeader";
import { AiPrivacySection } from "@/components/construct/AiPrivacySection";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { FormField } from "@/components/ui/FormField";
import { Input } from "@/components/ui/Input";
import { LoadingState } from "@/components/ui/LoadingState";
import { Select } from "@/components/ui/Select";
import { Toggle } from "@/components/ui/Toggle";
import { ApiError, api } from "@/lib/api";
import type { CerebroAccount, CerebroPreferences } from "@/lib/api";
import { cn } from "@/lib/cn";

const TABS = ["Preferences", "AI & Privacy", "Account"] as const;
type Tab = (typeof TABS)[number];

export function SettingsView() {
  const [tab, setTab] = useState<Tab>("Preferences");
  const [prefs, setPrefs] = useState<CerebroPreferences | null>(null);
  const [account, setAccount] = useState<CerebroAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.preferences(), api.account()])
      .then(([p, a]) => {
        setPrefs(p);
        setAccount(a);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load your settings."),
      )
      .finally(() => setLoading(false));
  }, []);

  async function patch(input: Partial<CerebroPreferences>) {
    setError(null);
    try {
      setPrefs(await api.savePreferences(input));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save that change.");
    }
  }

  if (loading) return <LoadingState label="Loading settings" className="mt-2" />;

  return (
    <div className="mx-auto max-w-3xl pb-4">
      <PageHeader
        title="Settings"
        description="How CEREBRO behaves, and what it may do with your knowledge."
      />

      <div role="tablist" aria-label="Settings sections" className="mt-5 flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              tab === t
                ? "bg-accent-subtle font-medium text-accent"
                : "text-ink-muted hover:bg-surface-subtle hover:text-ink",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-7">
        <ErrorMessage className="mb-5">{error}</ErrorMessage>

        {tab === "Preferences" && prefs && (
          <section className="flex flex-col gap-1">
            <FormField htmlFor="response_style" label="Preferred response style"
              className="max-w-xs pb-3"
              hint="Stored for future AI features; nothing uses it yet.">
              <Select id="response_style" value={prefs.response_style}
                onChange={(e) => patch({ response_style: e.target.value })}>
                <option value="concise">Concise</option>
                <option value="balanced">Balanced</option>
                <option value="detailed">Detailed</option>
              </Select>
            </FormField>

            <div className="divide-y divide-line border-t border-line">
              <Toggle label="AI suggestions" checked={prefs.ai_suggestions}
                description="Let CEREBRO offer suggestions as you work."
                onChange={(v) => patch({ ai_suggestions: v })} />
              <Toggle label="Recall suggestions" checked={prefs.recall_suggestions}
                description="Surface things you may want to remember."
                onChange={(v) => patch({ recall_suggestions: v })} />
              <Toggle label="Keep knowledge private" description="Private by default."
                checked={prefs.knowledge_visibility === "private"}
                onChange={(v) =>
                  patch({ knowledge_visibility: v ? "private" : "shared" })
                } />
            </div>
          </section>
        )}

        {tab === "AI & Privacy" && prefs && (
          <AiPrivacySection preferences={prefs} onChange={patch} />
        )}

        {tab === "Account" && account && (
          <AccountSection account={account} />
        )}
      </div>
    </div>
  );
}

function AccountSection({ account }: { account: CerebroAccount }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setDone(false);
    if (next !== confirm) {
      setError("New passwords do not match");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      setDone(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not change your password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-9">
      <section>
        <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
          Account
        </h2>
        <dl className="mt-4 divide-y divide-line border-y border-line text-sm">
          <Row label="Display name" value={account.display_name} />
          <Row label="Email" value={account.email} />
          <Row label="Account created" value={formatDate(account.created_at)} />
          <Row
            label="Last sign-in"
            value={account.last_login_at ? formatDate(account.last_login_at) : "This session"}
          />
        </dl>
        <p className="mt-3 text-xs text-ink-subtle">
          Your display name is editable from your{" "}
          <Link href="/construct/profile" className="text-accent hover:underline">
            profile
          </Link>
          .
        </p>
      </section>

      <section>
        <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
          Change password
        </h2>
        <form onSubmit={submit} noValidate className="mt-4 flex max-w-sm flex-col gap-4">
          <ErrorMessage>{error}</ErrorMessage>
          <FormField htmlFor="current_password" label="Current password">
            <Input id="current_password" type="password" autoComplete="current-password"
              value={current} onChange={(e) => setCurrent(e.target.value)} disabled={busy} />
          </FormField>
          <FormField htmlFor="new_password" label="New password"
            hint="At least 10 characters, including a letter and a number.">
            <Input id="new_password" type="password" autoComplete="new-password"
              value={next} onChange={(e) => setNext(e.target.value)} disabled={busy} />
          </FormField>
          <FormField htmlFor="confirm_password" label="Confirm new password">
            <Input id="confirm_password" type="password" autoComplete="new-password"
              value={confirm} onChange={(e) => setConfirm(e.target.value)} disabled={busy} />
          </FormField>
          <div className="flex items-center gap-3">
            <Button type="submit" loading={busy}>Update password</Button>
            {done && <span role="status" className="text-sm text-ink-muted">Password updated</span>}
          </div>
        </form>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-3 py-3">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric", month: "long", day: "numeric",
  });
}
