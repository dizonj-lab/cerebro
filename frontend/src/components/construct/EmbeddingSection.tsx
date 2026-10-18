"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormField } from "@/components/ui/FormField";
import { Input } from "@/components/ui/Input";
import type { CerebroPreferences } from "@/lib/api";

/**
 * The embedding and chunking budget.
 *
 * These five numbers decide whether a document can be embedded at all. They
 * were compiled-in constants until a slide deck chunk overran the embedding
 * model's context and took a whole registration down with it, with nothing on
 * screen to say what the numbers were. They are editable here, and the two
 * groups are separated because they fail differently:
 *
 * - **Model and width** are matched against every stored vector at search
 *   time. Changing either orphans the vectors already written — the documents
 *   stay, and stay findable by keyword, but drop out of semantic search until
 *   re-registered. The warning below says so before anything is saved.
 * - **Context limit, chunk size and overlap** only decide how the *next*
 *   registration is cut. Fragments already written keep the size they had.
 *
 * Unlike the rest of Settings, this section does not save as you type: a
 * half-typed number is a different budget, and the five are checked against
 * each other on the server, so they are sent together behind an explicit
 * Save.
 */

interface Props {
  preferences: CerebroPreferences;
  onChange: (input: Partial<CerebroPreferences>) => void | Promise<void>;
}

type Draft = Record<FieldName, string>;

type FieldName =
  | "embedding_model"
  | "embedding_dimensions"
  | "embedding_context_limit"
  | "chunk_target_tokens"
  | "chunk_overlap_tokens";

const FIELDS: FieldName[] = [
  "embedding_model",
  "embedding_dimensions",
  "embedding_context_limit",
  "chunk_target_tokens",
  "chunk_overlap_tokens",
];

function draftOf(preferences: CerebroPreferences): Draft {
  return FIELDS.reduce((acc, field) => {
    const value = preferences[field];
    acc[field] = value === null || value === undefined ? "" : String(value);
    return acc;
  }, {} as Draft);
}

export function EmbeddingSection({ preferences, onChange }: Props) {
  // Derived from props, re-derived when they change. The saved preferences are
  // the authority; the draft only exists between a keystroke and a Save.
  const [source, setSource] = useState(preferences);
  const [draft, setDraft] = useState<Draft>(() => draftOf(preferences));
  const [saving, setSaving] = useState(false);
  if (source !== preferences) {
    setSource(preferences);
    setDraft(draftOf(preferences));
  }

  const effective = preferences.effective ?? null;
  const overridden = new Set(effective?.overridden ?? []);
  const saved = draftOf(preferences);
  const dirty = FIELDS.some((f) => draft[f] !== saved[f]);

  // Whether this save would orphan vectors — true only for the two fields
  // that search filters on, and only when they actually change.
  const changesVectorSpace =
    draft.embedding_model !== saved.embedding_model ||
    draft.embedding_dimensions !== saved.embedding_dimensions;

  function set(field: FieldName, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function save() {
    // An empty field clears the override and returns the setting to the
    // deployment default, so it is sent as an explicit null rather than
    // omitted — omitting it would leave the old value in place.
    const payload: Partial<CerebroPreferences> = {
      embedding_model: draft.embedding_model.trim() || null,
      embedding_dimensions: numberOrNull(draft.embedding_dimensions),
      embedding_context_limit: numberOrNull(draft.embedding_context_limit),
      chunk_target_tokens: numberOrNull(draft.chunk_target_tokens),
      chunk_overlap_tokens: numberOrNull(draft.chunk_overlap_tokens),
    };
    setSaving(true);
    try {
      await onChange(payload);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-9" data-testid="embedding-settings">
      <section>
        <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
          Embedding model
        </h2>
        <p className="mt-2 max-w-prose text-sm text-ink-subtle">
          The model that turns your documents into vectors, and the width of
          the vectors it produces. Leave either blank to use whatever the
          CEREBRO environment is configured with.
        </p>

        <div className="mt-4 flex flex-col gap-1">
          <FormField
            htmlFor="embedding_model"
            label="Model"
            className="max-w-sm pb-3"
            hint="The name as the local daemon lists it, tag included."
            origin={
              overridden.has("embedding_model")
                ? { label: "Chosen by you", tone: "confirmed" }
                : undefined
            }
          >
            <Input
              id="embedding_model"
              value={draft.embedding_model}
              placeholder={effective?.embedding_model ?? "Whatever is installed"}
              onChange={(e) => set("embedding_model", e.target.value)}
            />
          </FormField>

          <FormField
            htmlFor="embedding_dimensions"
            label="Dimensions"
            className="max-w-sm pb-3"
            hint={
              "Left blank, the published width for the model above is used. A" +
              " wrong width is not a smaller vector — the daemon refuses every" +
              " embedding — so a mismatch is rejected rather than stored."
            }
            origin={
              overridden.has("embedding_dimensions")
                ? { label: "Chosen by you", tone: "confirmed" }
                : undefined
            }
          >
            <Input
              id="embedding_dimensions"
              type="number"
              inputMode="numeric"
              value={draft.embedding_dimensions}
              placeholder={
                effective?.embedding_dimensions
                  ? String(effective.embedding_dimensions)
                  : "From the model"
              }
              onChange={(e) => set("embedding_dimensions", e.target.value)}
            />
          </FormField>
        </div>
      </section>

      <section>
        <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
          Chunking
        </h2>
        <p className="mt-2 max-w-prose text-sm text-ink-subtle">
          How a document is cut up before it is embedded. These apply to what
          you register next; fragments already stored keep the size they were
          cut at.
        </p>

        <div className="mt-4 flex flex-col gap-1">
          <FormField
            htmlFor="embedding_context_limit"
            label="Context limit (tokens)"
            className="max-w-sm pb-3"
            hint={
              "The most the model will accept in one go. A lower value than" +
              " the model publishes is allowed; a higher one is refused," +
              " because overrunning it is what fails a registration."
            }
            origin={
              overridden.has("context_limit")
                ? { label: "Chosen by you", tone: "confirmed" }
                : undefined
            }
          >
            <Input
              id="embedding_context_limit"
              type="number"
              inputMode="numeric"
              value={draft.embedding_context_limit}
              placeholder={
                effective ? String(effective.embedding_context_limit) : undefined
              }
              onChange={(e) => set("embedding_context_limit", e.target.value)}
            />
          </FormField>

          <FormField
            htmlFor="chunk_target_tokens"
            label="Chunk size (tokens)"
            className="max-w-sm pb-3"
            hint={
              effective
                ? `About ${effective.chunk_target_chars} characters at present.` +
                  " Keep it well under the context limit: the token count is an" +
                  " estimate, and the headroom is what absorbs it being wrong."
                : "Keep it well under the context limit."
            }
            origin={
              overridden.has("target_tokens")
                ? { label: "Chosen by you", tone: "confirmed" }
                : undefined
            }
          >
            <Input
              id="chunk_target_tokens"
              type="number"
              inputMode="numeric"
              value={draft.chunk_target_tokens}
              placeholder={effective ? String(effective.chunk_target_tokens) : undefined}
              onChange={(e) => set("chunk_target_tokens", e.target.value)}
            />
          </FormField>

          <FormField
            htmlFor="chunk_overlap_tokens"
            label="Overlap (tokens)"
            className="max-w-sm pb-3"
            hint="How much each chunk repeats of the one before, so a sentence split across a boundary is still retrievable from both sides."
            origin={
              overridden.has("overlap_tokens")
                ? { label: "Chosen by you", tone: "confirmed" }
                : undefined
            }
          >
            <Input
              id="chunk_overlap_tokens"
              type="number"
              inputMode="numeric"
              value={draft.chunk_overlap_tokens}
              placeholder={effective ? String(effective.chunk_overlap_tokens) : undefined}
              onChange={(e) => set("chunk_overlap_tokens", e.target.value)}
            />
          </FormField>
        </div>
      </section>

      {changesVectorSpace && (
        <p
          data-testid="orphan-warning"
          className="max-w-prose rounded-md border border-danger/25 bg-danger-subtle px-4 py-3 text-sm text-danger"
        >
          Changing the model or the width leaves your existing vectors behind.
          Provider, model and width travel with every vector and search matches
          on all three, so documents registered under the old model stay in
          your library and stay findable by keyword, but drop out of semantic
          search until they are registered again under the new one.
        </p>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={() => void save()} disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save embedding settings"}
        </Button>
        {dirty && !saving && (
          <button
            type="button"
            className="text-sm text-ink-subtle underline-offset-2 hover:underline"
            onClick={() => setDraft(saved)}
          >
            Discard changes
          </button>
        )}
      </div>
    </div>
  );
}

function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}
