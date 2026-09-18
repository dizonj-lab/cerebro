"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormField } from "@/components/ui/FormField";
import { Select } from "@/components/ui/Select";
import type { CerebroPreferences } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * AI processing mode and the consent that gates it.
 *
 * Configuration only — no model is called anywhere in this phase. Local is the
 * default, and moving to Cloud requires an explicit, cancellable consent step.
 * Provider and model are free-form selects so further options can be added
 * without reworking this UI.
 */

const LOCAL_PROVIDERS = [
  { value: "", label: "Not configured" },
  { value: "ollama", label: "Ollama" },
  { value: "llamacpp", label: "llama.cpp" },
];

const CLOUD_PROVIDERS = [
  { value: "", label: "Not configured" },
  { value: "anthropic", label: "Anthropic" },
  { value: "openai", label: "OpenAI" },
];

interface Props {
  preferences: CerebroPreferences;
  onChange: (input: Partial<CerebroPreferences>) => void | Promise<void>;
}

export function AiPrivacySection({ preferences, onChange }: Props) {
  const [consentOpen, setConsentOpen] = useState(false);
  const isCloud = preferences.ai_processing_mode === "cloud";

  function selectMode(mode: "local" | "cloud") {
    if (mode === "local") {
      onChange({ ai_processing_mode: "local" });
      return;
    }
    // Consent already on record — no need to ask again.
    if (preferences.cloud_ai_consent) {
      onChange({ ai_processing_mode: "cloud" });
      return;
    }
    setConsentOpen(true);
  }

  return (
    <div className="flex flex-col gap-9">
      <section>
        <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
          AI processing
        </h2>

        <div className="mt-4 flex flex-col gap-2" role="radiogroup" aria-label="AI processing mode">
          <ModeOption
            selected={!isCloud}
            onSelect={() => selectMode("local")}
            title="Local AI"
            badge="Recommended"
            description="Processing stays within the CEREBRO environment. No external AI provider is contacted, and there is no per-request API cost."
          />
          <ModeOption
            selected={isCloud}
            onSelect={() => selectMode("cloud")}
            title="Cloud AI"
            description="Uses an external AI service. Content needed for a request may be transmitted outside the CEREBRO environment, and may incur API usage cost."
          />
        </div>
      </section>

      {/* Progressive disclosure: only the selected mode's configuration shows. */}
      <section>
        <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
          {isCloud ? "Cloud model" : "Local model"}
        </h2>
        <div className="mt-4 grid max-w-lg gap-4 sm:grid-cols-2">
          {isCloud ? (
            <>
              <FormField htmlFor="cloud_provider" label="Provider">
                <Select id="cloud_provider" value={preferences.cloud_provider ?? ""}
                  onChange={(e) => onChange({ cloud_provider: e.target.value || null })}>
                  {CLOUD_PROVIDERS.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </Select>
              </FormField>
              <FormField htmlFor="cloud_model" label="Model"
                hint="Credentials are never stored here.">
                <Select id="cloud_model" value={preferences.cloud_model ?? ""}
                  onChange={(e) => onChange({ cloud_model: e.target.value || null })}>
                  <option value="">Not configured</option>
                  <option value="default">Provider default</option>
                </Select>
              </FormField>
            </>
          ) : (
            <>
              <FormField htmlFor="local_provider" label="Runtime">
                <Select id="local_provider" value={preferences.local_provider ?? ""}
                  onChange={(e) => onChange({ local_provider: e.target.value || null })}>
                  {LOCAL_PROVIDERS.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </Select>
              </FormField>
              <FormField htmlFor="local_model" label="Model"
                hint="No external API usage cost.">
                <Select id="local_model" value={preferences.local_model ?? ""}
                  onChange={(e) => onChange({ local_model: e.target.value || null })}>
                  <option value="">Not configured</option>
                  <option value="default">Runtime default</option>
                </Select>
              </FormField>
            </>
          )}
        </div>
      </section>

      <section>
        <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
          Privacy status
        </h2>
        <div className="mt-3">
          <PrivacyStatus mode={preferences.ai_processing_mode} />
        </div>

        <div className="mt-5 rounded-lg border border-line bg-surface-subtle p-4 text-sm leading-relaxed text-ink-muted">
          <p className="font-medium text-ink">Your knowledge belongs to you.</p>
          <p className="mt-2">
            CEREBRO is designed with privacy as a core principle. Local AI processing keeps
            supported AI workloads within your CEREBRO environment.
          </p>
          <p className="mt-2">
            If you enable Cloud AI, information required to process your request may be
            transmitted to the selected external AI provider.
          </p>
          <p className="mt-2">
            CEREBRO will not intentionally switch from Local to Cloud processing without your
            permission. Review your selected AI processing mode before using CEREBRO with
            confidential, sensitive, or regulated information.
          </p>
        </div>
      </section>

      {consentOpen && (
        <ConsentDialog
          onCancel={() => setConsentOpen(false)}
          onEnable={async () => {
            await onChange({ ai_processing_mode: "cloud", cloud_ai_consent: true });
            setConsentOpen(false);
          }}
        />
      )}
    </div>
  );
}

export function PrivacyStatus({ mode }: { mode: string }) {
  const cloud = mode === "cloud";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs",
        cloud
          ? "border-line-strong bg-surface-subtle text-ink-muted"
          : "border-accent/25 bg-accent-subtle text-accent",
      )}
    >
      <span
        aria-hidden="true"
        className={cn("size-1.5 rounded-full", cloud ? "bg-ink-subtle" : "bg-accent")}
      />
      <span className="font-medium uppercase tracking-[0.08em]">
        {cloud ? "Cloud AI" : "Local AI"}
      </span>
      <span>{cloud ? "External processing enabled" : "Processing stays within CEREBRO"}</span>
    </span>
  );
}

function ConsentDialog({
  onCancel,
  onEnable,
}: {
  onCancel: () => void;
  onEnable: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div aria-hidden="true" className="absolute inset-0 bg-ink/25" onClick={onCancel} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="consent-title"
        className="relative w-full max-w-lg rounded-lg border border-line bg-surface p-6 shadow-card"
      >
        <h2 id="consent-title" className="text-base font-semibold text-ink">
          Cloud AI Processing
        </h2>
        <div className="mt-3 flex flex-col gap-2.5 text-sm leading-relaxed text-ink-muted">
          <p>
            CEREBRO can use external AI services to provide more capable language and reasoning
            features.
          </p>
          <p>
            When Cloud AI is enabled, relevant portions of your content may be transmitted outside
            the local CEREBRO environment to the selected AI provider for processing.
          </p>
          <p>
            This may include text extracted from documents, prompts, retrieved knowledge, and other
            information required to answer your request.
          </p>
          <p>
            Use Local AI if you prefer to keep AI processing within your CEREBRO environment.
          </p>
          <p>
            By enabling Cloud AI, you acknowledge that relevant data may be processed by the
            selected external provider according to that provider&rsquo;s applicable terms and
            privacy policies.
          </p>
        </div>
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            loading={busy}
            onClick={async () => {
              setBusy(true);
              await onEnable();
              setBusy(false);
            }}
          >
            Enable Cloud AI
          </Button>
        </div>
      </div>
    </div>
  );
}

function ModeOption({
  selected,
  onSelect,
  title,
  description,
  badge,
}: {
  selected: boolean;
  onSelect: () => void;
  title: string;
  description: string;
  badge?: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        "flex gap-3 rounded-lg border p-4 text-left transition-colors",
        selected ? "border-accent bg-accent-subtle" : "border-line hover:bg-surface-subtle",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border",
          selected ? "border-accent" : "border-line-strong",
        )}
      >
        {selected && <span className="size-2 rounded-full bg-accent" />}
      </span>
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-ink">{title}</span>
          {badge && (
            <span className="rounded-full bg-surface px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-[0.08em] text-ink-subtle">
              {badge}
            </span>
          )}
        </span>
        <span className="mt-1 block text-xs leading-relaxed text-ink-muted">{description}</span>
      </span>
    </button>
  );
}
