"use client";

import { useEffect, useState } from "react";

import { CompletionMeter } from "@/components/construct/CompletionMeter";
import { PageHeader } from "@/components/construct/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { FormField } from "@/components/ui/FormField";
import { Input } from "@/components/ui/Input";
import { LoadingState } from "@/components/ui/LoadingState";
import { TagInput } from "@/components/ui/TagInput";
import { Textarea } from "@/components/ui/Textarea";
import { ApiError, api } from "@/lib/api";
import type { CerebroProfile } from "@/lib/api";

type Draft = Omit<CerebroProfile, "completion_percent" | "completed_fields" | "total_fields">;

const EMPTY: Draft = {
  full_name: "", bio: "", location: "", timezone: "", avatar_url: null,
  role_title: "", organization: "", industry: "", years_experience: null,
  expertise: [], interests: [], current_topics: [],
  learning_goals: "", career_goals: "",
};

function toDraft(p: CerebroProfile): Draft {
  return {
    full_name: p.full_name ?? "", bio: p.bio ?? "", location: p.location ?? "",
    timezone: p.timezone ?? "", avatar_url: p.avatar_url,
    role_title: p.role_title ?? "", organization: p.organization ?? "",
    industry: p.industry ?? "", years_experience: p.years_experience,
    expertise: p.expertise, interests: p.interests, current_topics: p.current_topics,
    learning_goals: p.learning_goals ?? "", career_goals: p.career_goals ?? "",
  };
}

export function ProfileForm() {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [profile, setProfile] = useState<CerebroProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api
      .profile()
      .then((p) => {
        setProfile(p);
        setDraft(toDraft(p));
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load your profile."),
      )
      .finally(() => setLoading(false));
  }, []);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
    setSaved(false);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const saved = await api.saveProfile({
        ...draft,
        years_experience:
          draft.years_experience === null || Number.isNaN(draft.years_experience)
            ? null
            : draft.years_experience,
      });
      setProfile(saved);
      setDraft(toDraft(saved));
      setSaved(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save your profile.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingState label="Loading your profile" className="mt-2" />;

  return (
    <div className="mx-auto max-w-3xl pb-4">
      <PageHeader
        title="Profile"
        description="This is how CEREBRO understands your context. Nothing here is shared."
      />

      {profile && (
        <div className="mt-6 max-w-sm">
          <CompletionMeter
            percent={profile.completion_percent}
            completed={profile.completed_fields}
            total={profile.total_fields}
          />
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="mt-8 flex flex-col gap-10">
        <ErrorMessage>{error}</ErrorMessage>

        <Section title="Personal">
          <FormField htmlFor="full_name" label="Full name">
            <Input id="full_name" value={draft.full_name ?? ""}
              onChange={(e) => set("full_name", e.target.value)} disabled={saving} />
          </FormField>
          <FormField htmlFor="location" label="Location">
            <Input id="location" value={draft.location ?? ""} placeholder="City, country"
              onChange={(e) => set("location", e.target.value)} disabled={saving} />
          </FormField>
          <FormField htmlFor="timezone" label="Timezone" className="sm:col-span-1">
            <Input id="timezone" value={draft.timezone ?? ""} placeholder="Europe/London"
              onChange={(e) => set("timezone", e.target.value)} disabled={saving} />
          </FormField>
          <FormField htmlFor="bio" label="Short bio" className="sm:col-span-2"
            hint="A sentence or two. Context, not a CV.">
            <Textarea id="bio" rows={3} value={draft.bio ?? ""}
              onChange={(e) => set("bio", e.target.value)} disabled={saving} />
          </FormField>
        </Section>

        <Section title="Professional">
          <FormField htmlFor="role_title" label="Role or title">
            <Input id="role_title" value={draft.role_title ?? ""}
              onChange={(e) => set("role_title", e.target.value)} disabled={saving} />
          </FormField>
          <FormField htmlFor="organization" label="Organization">
            <Input id="organization" value={draft.organization ?? ""}
              onChange={(e) => set("organization", e.target.value)} disabled={saving} />
          </FormField>
          <FormField htmlFor="industry" label="Industry">
            <Input id="industry" value={draft.industry ?? ""}
              onChange={(e) => set("industry", e.target.value)} disabled={saving} />
          </FormField>
          <FormField htmlFor="years_experience" label="Years of experience">
            <Input id="years_experience" type="number" min={0} max={80}
              value={draft.years_experience ?? ""}
              onChange={(e) =>
                set("years_experience", e.target.value === "" ? null : Number(e.target.value))
              }
              disabled={saving} />
          </FormField>
          <FormField htmlFor="expertise" label="Areas of expertise" className="sm:col-span-2">
            <TagInput id="expertise" value={draft.expertise} disabled={saving}
              onChange={(v) => set("expertise", v)} placeholder="Add an area and press Enter" />
          </FormField>
        </Section>

        <Section title="Interests and goals">
          <FormField htmlFor="interests" label="Interests" className="sm:col-span-2">
            <TagInput id="interests" value={draft.interests} disabled={saving}
              onChange={(v) => set("interests", v)} placeholder="Add an interest and press Enter" />
          </FormField>
          <FormField htmlFor="current_topics" label="Currently exploring" className="sm:col-span-2">
            <TagInput id="current_topics" value={draft.current_topics} disabled={saving}
              onChange={(v) => set("current_topics", v)} placeholder="Add a topic and press Enter" />
          </FormField>
          <FormField htmlFor="learning_goals" label="Learning goals" className="sm:col-span-2">
            <Textarea id="learning_goals" rows={2} value={draft.learning_goals ?? ""}
              onChange={(e) => set("learning_goals", e.target.value)} disabled={saving} />
          </FormField>
          <FormField htmlFor="career_goals" label="Career goals" className="sm:col-span-2">
            <Textarea id="career_goals" rows={2} value={draft.career_goals ?? ""}
              onChange={(e) => set("career_goals", e.target.value)} disabled={saving} />
          </FormField>
        </Section>

        <div className="flex items-center gap-4 border-t border-line pt-5">
          <Button type="submit" loading={saving}>
            {saving ? "Saving" : "Save profile"}
          </Button>
          {saved && (
            <span role="status" className="text-sm text-ink-muted">
              Profile saved
            </span>
          )}
        </div>
      </form>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">{title}</h2>
      <div className="mt-4 grid gap-5 sm:grid-cols-2">{children}</div>
    </section>
  );
}
