"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { ArtifactStatus, formatBytes } from "@/components/construct/ArtifactStatus";
import { PageHeader } from "@/components/construct/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { FormField } from "@/components/ui/FormField";
import { Input } from "@/components/ui/Input";
import { LoadingState } from "@/components/ui/LoadingState";
import { TagInput } from "@/components/ui/TagInput";
import { Textarea } from "@/components/ui/Textarea";
import { BulkIngest } from "@/app/construct/ingest/BulkIngest";
import { ApiError, api } from "@/lib/api";
import type {
  CerebroArtifact,
  CerebroArtifactExtraction,
  CerebroArtifactMetadata,
  CerebroEnrichmentSuggestion,
} from "@/lib/api";
import { cn } from "@/lib/cn";

const EMPTY: CerebroArtifactMetadata = {
  title: "", description: "", language: "", author: "", created_date: "",
  topics: [], people: [], organizations: [], projects: [], tags: [],
};

function toDraft(m: CerebroArtifactMetadata): CerebroArtifactMetadata {
  return {
    ...EMPTY, ...m,
    title: m.title ?? "", description: m.description ?? "",
    language: m.language ?? "", author: m.author ?? "", created_date: m.created_date ?? "",
  };
}

// Names what the extractor actually found. Nothing is inferred: an artifact
// ingested before extraction was wired in reports no structure at all rather
// than a fabricated page count.
function describeStructure(extraction: CerebroArtifactExtraction): string {
  const structure = extraction.structure ?? {};
  const counts = (["pages", "slides", "paragraphs"] as const)
    .filter((k) => typeof structure[k] === "number")
    .map((k) => `${structure[k]} ${structure[k] === 1 ? k.slice(0, -1) : k}`);
  return counts.length > 0 ? `from ${counts.join(", ")}` : "";
}

// How a value was arrived at, in the user's words. Shown per field so a
// model's guess is never mistaken for something the document asserts.
const METHOD_HINTS: Record<string, string> = {
  filename_stem: "Drafted from the filename, not read from the content.",
  document_metadata: "From the document's own metadata.",
  keyphrase_extraction: "From words the document repeats. Statistics, not meaning.",
  "document_metadata+keyphrase_extraction":
    "The document's own keywords, plus words it repeats.",
  language_detection: "Detected from the text, and left blank when unclear.",
  extracted_opening: "A quote of the opening, not a summary.",
  ai_suggested: "Suggested by the local model. Check it before confirming.",
  human_confirmed: "You confirmed this.",
  not_established: "",
};

function IngestInner() {
  const existingId = useSearchParams().get("artifact");

  const [artifact, setArtifact] = useState<CerebroArtifact | null>(null);
  const [draft, setDraft] = useState<CerebroArtifactMetadata>(EMPTY);
  const [loading, setLoading] = useState(Boolean(existingId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [dragging, setDragging] = useState(false);
  // Single is the default: one document reviewed carefully is the normal
  // case, and bulk is for when a pile of them arrives at once.
  const [mode, setMode] = useState<"single" | "bulk">("single");
  const [suggesting, setSuggesting] = useState(false);
  const [suggestion, setSuggestion] = useState<CerebroEnrichmentSuggestion | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!existingId) return;
    api
      .artifact(existingId)
      .then((a) => {
        setArtifact(a);
        setDraft(toDraft(a.metadata));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load that artifact."))
      .finally(() => setLoading(false));
  }, [existingId]);

  const onFile = useCallback(async (file: File) => {
    setError(null);
    setSaved(false);
    setBusy(true);
    try {
      const a = await api.uploadArtifact(file);
      setArtifact(a);
      setDraft(toDraft(a.metadata));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add that file.");
    } finally {
      setBusy(false);
    }
  }, []);

  async function askTheModel() {
    if (!artifact) return;
    setError(null);
    setSuggesting(true);
    try {
      const result = await api.suggestArtifact(artifact.id);
      setSuggestion(result);
      // Suggestions land in the form, where they can be edited or removed.
      // They are not saved until the form is submitted, and they stay
      // unconfirmed until it is approved.
      setDraft((d) => ({ ...d, ...toDraft({ ...d, ...result.suggestions }) }));
      setSaved(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not ask the local model.");
    } finally {
      setSuggesting(false);
    }
  }

  // Live methods: a field the model has just proposed reports as such before
  // anything is saved, so the hint matches what is in the box.
  function methodOf(field: string): string | undefined {
    const method = suggestion?.field_methods?.[field] ?? artifact?.field_methods?.[field];
    return method ? METHOD_HINTS[method] || undefined : undefined;
  }

  function set<K extends keyof CerebroArtifactMetadata>(k: K, v: CerebroArtifactMetadata[K]) {
    setDraft((d) => ({ ...d, [k]: v }));
    setSaved(false);
  }

  async function submit(approve: boolean) {
    if (!artifact) return;
    setError(null);
    setBusy(true);
    try {
      const a = await api.reviewArtifact(artifact.id, { metadata: draft, approve });
      setArtifact(a);
      setDraft(toDraft(a.metadata));
      setSaved(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save that review.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingState label="Loading artifact" className="mt-2" />;

  const registered = artifact?.status === "registered";

  return (
    <div className="mx-auto max-w-3xl pb-4">
      <PageHeader
        title={artifact ? "Review artifact" : "Add an artifact"}
        description={
          artifact
            ? "CEREBRO inspected the file and drafted what it could establish. Confirm it before registering."
            : "Add a document. Nothing is registered until you confirm what CEREBRO got right."
        }
        action={
          <Link href="/construct/library">
            <Button variant="ghost">Library</Button>
          </Link>
        }
      />

      <ErrorMessage className="mt-5">{error}</ErrorMessage>

      {!artifact && (
        <div role="group" aria-label="Upload mode" className="mt-5 flex w-fit rounded-lg border border-line bg-surface-subtle p-0.5">
          {(["single", "bulk"] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMode(option)}
              aria-pressed={mode === option}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                mode === option ? "bg-accent text-accent-ink" : "text-ink-muted hover:text-ink",
              )}
            >
              {option === "single" ? "One document" : "Several documents"}
            </button>
          ))}
        </div>
      )}

      {!artifact && mode === "bulk" && <BulkIngest />}

      {!artifact && mode === "single" && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) void onFile(f);
          }}
          className={cn(
            "mt-7 rounded-lg border border-dashed p-10 text-center transition-colors",
            dragging ? "border-accent bg-accent-subtle" : "border-line-strong bg-surface-subtle",
          )}
        >
          <p className="text-sm font-medium text-ink">Drop a document here</p>
          <p className="mx-auto mt-1.5 max-w-sm text-xs text-ink-muted">
            PDF, Word, PowerPoint, plain text and Markdown, up to 25MB. Text is extracted
            deterministically — no AI reads your document. Scanned pages and audio need OCR and
            transcription, which arrive in a later phase.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.pptx,.txt,.md,.markdown,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onFile(f);
            }}
          />
          <Button
            variant="secondary"
            className="mt-5"
            loading={busy}
            onClick={() => fileRef.current?.click()}
          >
            {busy ? "Inspecting" : "Choose a file"}
          </Button>
        </div>
      )}

      {artifact && (
        <>
          {/* --- deterministic evidence, before any human edit --- */}
          <section className="mt-7 rounded-lg border border-line bg-surface-subtle p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{artifact.filename}</p>
                <p className="mt-0.5 font-mono text-xs text-ink-subtle">
                  {formatBytes(artifact.size_bytes)} · {artifact.modality} ·{" "}
                  {artifact.sha256.slice(0, 12)}…
                </p>
              </div>
              <ArtifactStatus status={artifact.status} />
            </div>

            {artifact.preview && (
              <p className="mt-4 text-xs font-medium text-ink-muted">
                Extracted text {describeStructure(artifact.extraction)}
              </p>
            )}

            {artifact.preview && (
              <pre className="mt-4 max-h-36 overflow-auto rounded-md border border-line bg-surface p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">
                {artifact.preview}
              </pre>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
              <a
                href={api.artifactContentUrl(artifact.id)}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-md text-sm font-medium text-accent underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
              >
                Open original document
                <span className="sr-only"> {artifact.filename} in a new tab</span>
              </a>
              {!registered && (
                <Button
                  type="button"
                  variant="secondary"
                  loading={suggesting}
                  onClick={() => void askTheModel()}
                >
                  {suggesting ? "Asking the local model" : "Suggest with local AI"}
                </Button>
              )}
            </div>

            <p className="mt-3 text-xs text-ink-subtle">
              {suggestion?.ai_used
                ? `Suggested by ${suggestion.model ?? suggestion.engine}, running in your CEREBRO environment. Check each field before confirming.`
                : "Inspected and extracted deterministically — no AI has read this artifact."}
            </p>

            {suggestion?.notes?.length ? (
              <ul className="mt-2 space-y-1">
                {suggestion.notes.map((note) => (
                  <li key={note} className="text-xs text-ink-subtle">
                    {note}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <form
            onSubmit={(e) => { e.preventDefault(); void submit(false); }}
            noValidate
            className="mt-8 flex flex-col gap-5"
          >
            <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
              Metadata
            </h2>

            <div className="grid gap-5 sm:grid-cols-2">
              <FormField
                htmlFor="title" label="Title" className="sm:col-span-2"
                hint={methodOf("title")}
              >
                <Input id="title" value={draft.title ?? ""} disabled={registered || busy}
                  onChange={(e) => set("title", e.target.value)} />
              </FormField>

              <FormField hint={methodOf("description")} htmlFor="description" label="Description" className="sm:col-span-2">
                <Textarea id="description" rows={3} value={draft.description ?? ""}
                  disabled={registered || busy}
                  onChange={(e) => set("description", e.target.value)} />
              </FormField>

              <FormField hint={methodOf("author")} htmlFor="author" label="Author">
                <Input id="author" value={draft.author ?? ""} disabled={registered || busy}
                  onChange={(e) => set("author", e.target.value)} />
              </FormField>

              <FormField hint={methodOf("language")} htmlFor="language" label="Language">
                <Input id="language" value={draft.language ?? ""} disabled={registered || busy}
                  onChange={(e) => set("language", e.target.value)} />
              </FormField>

              <FormField
                hint={methodOf("created_date")}
                htmlFor="created_date"
                label="Created date"
                className="sm:col-span-2"
              >
                <Input id="created_date" value={draft.created_date ?? ""}
                  placeholder="YYYY-MM-DD" disabled={registered || busy}
                  onChange={(e) => set("created_date", e.target.value)} />
              </FormField>

              <FormField hint={methodOf("topics")} htmlFor="topics" label="Topics" className="sm:col-span-2">
                <TagInput id="topics" value={draft.topics} disabled={registered || busy}
                  onChange={(v) => set("topics", v)} placeholder="Add a topic and press Enter" />
              </FormField>

              <FormField hint={methodOf("tags")} htmlFor="tags" label="Tags" className="sm:col-span-2">
                <TagInput id="tags" value={draft.tags} disabled={registered || busy}
                  onChange={(v) => set("tags", v)} placeholder="Add a tag and press Enter" />
              </FormField>

              <FormField htmlFor="people" label="People" className="sm:col-span-2">
                <TagInput id="people" value={draft.people} disabled={registered || busy}
                  onChange={(v) => set("people", v)} placeholder="Add a person and press Enter" />
              </FormField>

              <FormField htmlFor="organizations" label="Organizations" className="sm:col-span-2">
                <TagInput id="organizations" value={draft.organizations}
                  disabled={registered || busy}
                  onChange={(v) => set("organizations", v)}
                  placeholder="Add an organization and press Enter" />
              </FormField>

              <FormField htmlFor="projects" label="Projects" className="sm:col-span-2">
                <TagInput id="projects" value={draft.projects} disabled={registered || busy}
                  onChange={(v) => set("projects", v)} placeholder="Add a project and press Enter" />
              </FormField>
            </div>

            {registered ? (
              <div className="flex flex-wrap items-center gap-4 border-t border-line pt-5">
                <p className="text-sm text-ink-muted">
                  Registered and checksum-verified. This artifact is now trusted evidence.
                </p>
                <Link href="/construct/library" className="ml-auto">
                  <Button variant="secondary">Back to library</Button>
                </Link>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3 border-t border-line pt-5">
                <Button type="submit" variant="secondary" loading={busy}>
                  Save draft
                </Button>
                <Button type="button" loading={busy} onClick={() => void submit(true)}>
                  Confirm and register
                </Button>
                {saved && (
                  <span role="status" className="text-sm text-ink-muted">
                    Saved
                  </span>
                )}
                <p className="w-full text-xs text-ink-subtle">
                  Registering records your approval and re-verifies the stored file against its
                  original checksum.
                </p>
              </div>
            )}
          </form>
        </>
      )}
    </div>
  );
}

export function IngestView() {
  return (
    <Suspense fallback={null}>
      <IngestInner />
    </Suspense>
  );
}
