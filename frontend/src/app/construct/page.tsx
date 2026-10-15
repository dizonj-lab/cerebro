import Link from "next/link";

import { CompletionMeter } from "@/components/construct/CompletionMeter";
import { Button } from "@/components/ui/Button";
import { getCurrentProfile, getCurrentUser } from "@/lib/session";

/** Time-of-day greeting, computed on the server from its own clock. */
function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default async function ConstructPage() {
  const [user, profile] = await Promise.all([getCurrentUser(), getCurrentProfile()]);

  const name = profile?.full_name?.split(" ")[0] || user?.display_name || "there";
  // "Current focus" reuses what the profile already holds — nothing inferred.
  const focus = [...(profile?.current_topics ?? []), ...(profile?.expertise ?? [])].slice(0, 3);
  const percent = profile?.completion_percent ?? 0;

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">
        {greeting()}, {name}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">
        Your knowledge twin begins here.
      </p>

      {percent < 100 && (
        <div className="mt-8 rounded-lg border border-line bg-surface-subtle p-5">
          <p className="text-sm font-medium text-ink">
            {percent === 0
              ? "Complete your profile to help CEREBRO understand your context."
              : "A little more context will help CEREBRO understand you."}
          </p>
          {profile && (
            <CompletionMeter
              className="mt-4 max-w-xs"
              percent={percent}
              completed={profile.completed_fields}
              total={profile.total_fields}
            />
          )}
          <Link href="/construct/profile" className="mt-4 inline-block">
            <Button variant="secondary">
              {percent === 0 ? "Complete profile" : "Edit profile"}
            </Button>
          </Link>
        </div>
      )}

      {focus.length > 0 && (
        <section className="mt-10 border-t border-line pt-6">
          <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
            Current focus
          </h2>
          <p className="mt-2 text-sm text-ink">{focus.join(" · ")}</p>
        </section>
      )}

      {percent === 100 && profile && (
        <section className="mt-8 flex flex-wrap items-center gap-4 border-t border-line pt-6">
          <CompletionMeter
            className="max-w-xs"
            percent={percent}
            completed={profile.completed_fields}
            total={profile.total_fields}
          />
          <Link href="/construct/profile">
            <Button variant="ghost">Edit profile</Button>
          </Link>
        </section>
      )}
    </div>
  );
}
