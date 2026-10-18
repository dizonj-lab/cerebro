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
import { EnrichmentQueue } from "@/components/construct/EnrichmentQueue";
import { ApiError, api } from "@/lib/api";
import { useEnrichmentQueue } from "@/lib/useEnrichmentQueue";
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
  technologies: [], concepts: [],
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
  extracted_byline:
    "Printed on the document's first page, read verbatim. Check it before confirming.",
  ai_suggested: "Suggested by the local model. Check it before confirming.",
  human_confirmed: "You confirmed this.",
  not_established: "",
};

function IngestInner() {
  const existingId = useSearchParams().get("artifact");

  const [artifact, setArtifact] = useState<CerebroArtifact | null>(null);
  const { queue, refresh } = useEnrichmentQueue();
  const [draft, setDraft] = useState<CerebroArtifactMetadata>(EMPTY);
  const [loading, setLoading] = useState(Boolean(existingId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [dragging, setDragging] = useState(false);
  // Several files dropped at once go to the table; one goes to the form.
  // The shape follows what the user did rather than asking them first.
  const [batch, setBatch] = useState<File[] | null>(null);
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

  /** One file fills the form; several fill the table. */
  const onFiles = useCallback(
    (list: FileList | null) => {
      const files = list ? [...list] : [];
      if (files.length === 0) return;
      if (files.length === 1) {
        void onFile(files[0]);
        return;
      }
      setBatch(files);
    },
    [onFile],
  );

  /*
    A large document is stored immediately and read afterwards, so the form
    waits for the text rather than the upload. Polling rather than a socket:
    this is one row changing state once, and the user is free to leave the
    page while it happens — the work is on the server, not in this tab.
  */
  useEffect(() => {
    if (artifact?.status !== "processing") return;
    const id = artifact.id;
    let live = true;
    const timer = window.setInterval(() => {
      void api
        .artifact(id)
        .then((a) => {
          if (!live || a.status === "processing") return;
          setArtifact(a);
          setDraft(toDraft(a.metadata));
        })
        .catch(() => {
          // A failed poll is not a failed upload. The next one tries again.
        });
    }, 2000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [artifact?.status, artifact?.id]);

  async function discard() {
    if (!artifact) return;
    setError(null);
    setBusy(true);
    try {
      await api.deleteArtifact(artifact.id);
      // Back to an empty page: the artifact, its bytes and anything derived
      // from it are gone.
      setArtifact(null);
      setSuggestion(null);
      setSaved(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete that artifact.");
    } finally {
      setBusy(false);
    }
  }

  async function askTheModel() {
    if (!artifact) return;
    setError(null);
    setSuggesting(true);
    try {
      // Queued, not awaited. The work now outlives this page, so leaving it
      // no longer throws away minutes of a local model's time — coming back
      // finds the suggestions already on the artifact.
      await api.suggestArtifact(artifact.id);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not ask the local model.");
      setSuggesting(false);
    }
  }

  // Wait for the artifact's own job to reach a terminal state.
  //
  // Absence from the queue is not the same as finished: a queue snapshot can
  // predate the enqueue, and treating it as completion refetched the
  // artifact while the job was still waiting — which produced an empty
  // result and then stopped looking. The row's own status is the authority.
  // Wait for the artifact's own job to finish, then fill the form from the
  // server.
  //
  // Absence from the queue is not the same as finished: a queue snapshot can
  // predate the enqueue, and treating it as completion refetched the artifact
  // while the job was still waiting — which produced an empty result and then
  // stopped looking. The row's own status is the authority.
  const awaitJob = useCallback(async (id: string) => {
    const fresh = await api.artifact(id);
    setArtifact(fresh);
    const status = fresh.enrichment_job?.status;
    if (status !== "done" && status !== "failed") return false;
    // Only fills what is still empty: a value the user typed while waiting is
    // theirs, and the job must not overwrite it from behind them.
    setDraft((current) => {
      const filled = toDraft(fresh.metadata) as unknown as Record<string, unknown>;
      const merged = { ...current } as unknown as Record<string, unknown>;
      for (const [key, value] of Object.entries(filled)) {
        const held = merged[key];
        const empty =
          held === undefined ||
          held === null ||
          held === "" ||
          (Array.isArray(held) && held.length === 0);
        if (empty && value !== undefined) merged[key] = value;
      }
      return merged as unknown as CerebroArtifactMetadata;
    });
    setSaved(false);
    return true;
  }, []);

  useEffect(() => {
    if (!artifact || !suggesting) return;
    const id = artifact.id;
    let cancelled = false;
    const handle = setInterval(() => {
      void awaitJob(id).then((done) => {
        if (done && !cancelled) setSuggesting(false);
      });
    }, 1200);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [artifact, suggesting, awaitJob]);

  // Live methods: a field the model has just proposed reports as such before
  // anything is saved, so the hint matches what is in the box.
  function rawMethodOf(field: string): string | undefined {
    return suggestion?.field_methods?.[field] ?? artifact?.field_methods?.[field];
  }

  function methodOf(field: string): string | undefined {
    const method = rawMethodOf(field);
    return method ? METHOD_HINTS[method] || undefined : undefined;
  }

  /**
   * A word beside the label for where the value came from.
   *
   * The hint underneath already says it in a sentence, but a reviewer
   * scanning twelve fields reads labels, not hints — and the one thing they
   * need at a glance is which boxes a model filled, because those are the
   * ones to check. An empty field is not marked: provenance describes a
   * value, and there is no value to describe.
   */
  function originOf(field: keyof CerebroArtifactMetadata) {
    const value = draft[field];
    const empty =
      value === undefined || value === null || value === "" ||
      (Array.isArray(value) && value.length === 0);
    if (empty) return undefined;
    const method = rawMethodOf(field);
    if (!method || method === "not_established") return undefined;
    if (method === "ai_suggested") return { label: "AI suggested", tone: "ai" as const };
    if (method === "human_confirmed") return { label: "You confirmed", tone: "confirmed" as const };
    if (method === "extracted_byline") {
      return { label: "From the page", tone: "document" as const };
    }
    if (method.startsWith("document_metadata")) {
      return { label: "From the file", tone: "document" as const };
    }
    if (method === "filename_stem") return { label: "From the filename", tone: "document" as const };
    return { label: "From the text", tone: "document" as const };
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

      {/*
        A large document is read after its upload has been answered for, so
        the form has nothing to show yet. Saying so — and saying that leaving
        is safe — is the whole point of doing it this way.
      */}
      {artifact?.status === "processing" && (
        <p
          role="status"
          data-testid="artifact-processing"
          className="mt-5 rounded-lg border border-line bg-surface-subtle px-4 py-3 text-sm text-ink-muted"
        >
          Reading <span className="font-medium text-ink">{artifact.filename}</span>. This runs in
          CEREBRO, not in this tab — you can go elsewhere and come back to it in the library.
        </p>
      )}

      {/*
        Deliberately no onDone handler: that fires when the batch has finished
        registering, and tearing the table down at that moment would take the
        results away just as the user wants to read them.
      */}
      {!artifact && batch && <BulkIngest initialFiles={batch} />}

      {!artifact && !batch && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            onFiles(e.dataTransfer.files);
          }}
          className={cn(
            "mt-7 rounded-lg border border-dashed p-10 text-center transition-colors",
            dragging ? "border-accent bg-accent-subtle" : "border-line-strong bg-surface-subtle",
          )}
        >
          <p className="text-sm font-medium text-ink">Drop documents here</p>
          <p className="mx-auto mt-1.5 max-w-sm text-xs text-ink-muted">
            One opens a form; several open a table. PDF, Word, PowerPoint, plain text and
            Markdown, up to 25MB each. Text is extracted deterministically — no AI reads your
            document. Scanned pages and audio need OCR and transcription, which arrive in a
            later phase.
          </p>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.docx,.pptx,.txt,.md,.markdown,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
            className="sr-only"
            onChange={(e) => onFiles(e.target.files)}
          />
          <Button
            variant="secondary"
            className="mt-5"
            loading={busy}
            onClick={() => fileRef.current?.click()}
          >
            {busy ? "Inspecting" : "Choose files"}
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

            {/* The queue, not a spinner. It keeps running if this page is
                closed, so what it shows is the server's state rather than
                this tab's. */}
            <EnrichmentQueue queue={queue} className="mt-3" />

            <p className="mt-3 text-xs text-ink-subtle">
              {artifact?.enrichment_job?.ai_used
                ? `Suggested by ${artifact.enrichment_job.model}, running in your CEREBRO environment. Check each field before confirming.`
                : "Inspected and extracted deterministically — no AI has read this artifact."}
            </p>

            {artifact?.enrichment_job?.error && (
              <p className="mt-2 text-xs text-danger">
                Enrichment did not finish: {artifact.enrichment_job.error}
              </p>
            )}

            {artifact?.enrichment_job?.notes?.length ? (
              <ul className="mt-2 space-y-1">
                {artifact.enrichment_job.notes.map((note) => (
                  <li key={note} className="text-xs text-ink-subtle">
                    {note}
                  </li>
                ))}
              </ul>
            ) : null}

            {/*
              The evidence for each suggested name. A model proposing a
              person is the one suggestion a reviewer cannot sanity-check
              from the field alone, so the sentence it came from is shown
              next to it rather than left in the document.
            */}
            {suggestion?.evidence && Object.keys(suggestion.evidence).length > 0 ? (
              <details className="mt-3" data-testid="suggestion-evidence">
                <summary className="cursor-pointer text-xs font-medium text-accent">
                  Where these came from ({Object.keys(suggestion.evidence).length})
                </summary>
                <ul className="mt-2 space-y-1.5">
                  {Object.entries(suggestion.evidence).map(([value, quote]) => (
                    <li key={value} className="text-xs text-ink-muted">
                      <span className="font-medium text-ink">{value}</span>
                      <span className="block text-ink-subtle">“{quote}”</span>
                    </li>
                  ))}
                </ul>
              </details>
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
                hint={methodOf("title")} origin={originOf("title")}
              >
                <Input id="title" value={draft.title ?? ""} disabled={registered || busy}
                  onChange={(e) => set("title", e.target.value)} />
              </FormField>

              <FormField hint={methodOf("description")} origin={originOf("description")} htmlFor="description" label="Description" className="sm:col-span-2">
                <Textarea id="description" rows={3} value={draft.description ?? ""}
                  disabled={registered || busy}
                  onChange={(e) => set("description", e.target.value)} />
              </FormField>

              <FormField hint={methodOf("author")} origin={originOf("author")} htmlFor="author" label="Author">
                <Input id="author" value={draft.author ?? ""} disabled={registered || busy}
                  onChange={(e) => set("author", e.target.value)} />
              </FormField>

              <FormField hint={methodOf("language")} origin={originOf("language")} htmlFor="language" label="Language">
                <Input id="language" value={draft.language ?? ""} disabled={registered || busy}
                  onChange={(e) => set("language", e.target.value)} />
              </FormField>

              <FormField
                hint={methodOf("created_date")} origin={originOf("created_date")}
                htmlFor="created_date"
                label="Created date"
                className="sm:col-span-2"
              >
                <Input id="created_date" value={draft.created_date ?? ""}
                  placeholder="YYYY-MM-DD" disabled={registered || busy}
                  onChange={(e) => set("created_date", e.target.value)} />
              </FormField>

              <FormField hint={methodOf("topics")} origin={originOf("topics")} htmlFor="topics" label="Topics" className="sm:col-span-2">
                <TagInput id="topics" value={draft.topics} disabled={registered || busy}
                  onChange={(v) => set("topics", v)} placeholder="Add a topic and press Enter" />
              </FormField>

              <FormField hint={methodOf("tags")} origin={originOf("tags")} htmlFor="tags" label="Tags" className="sm:col-span-2">
                <TagInput id="tags" value={draft.tags} disabled={registered || busy}
                  onChange={(v) => set("tags", v)} placeholder="Add a tag and press Enter" />
              </FormField>

              <FormField hint={methodOf("people")} origin={originOf("people")} htmlFor="people" label="People" className="sm:col-span-2">
                <TagInput id="people" value={draft.people} disabled={registered || busy}
                  onChange={(v) => set("people", v)} placeholder="Add a person and press Enter" />
              </FormField>

              <FormField hint={methodOf("organizations")} origin={originOf("organizations")} htmlFor="organizations" label="Organizations" className="sm:col-span-2">
                <TagInput id="organizations" value={draft.organizations}
                  disabled={registered || busy}
                  onChange={(v) => set("organizations", v)}
                  placeholder="Add an organization and press Enter" />
              </FormField>

              <FormField hint={methodOf("projects")} origin={originOf("projects")} htmlFor="projects" label="Projects" className="sm:col-span-2">
                <TagInput id="projects" value={draft.projects} disabled={registered || busy}
                  onChange={(v) => set("projects", v)} placeholder="Add a project and press Enter" />
              </FormField>

              <FormField hint={methodOf("technologies")} origin={originOf("technologies")} htmlFor="technologies" label="Technologies">
                <TagInput id="technologies" value={draft.technologies}
                  disabled={registered || busy} onChange={(v) => set("technologies", v)}
                  placeholder="Add a technology and press Enter" />
              </FormField>

              <FormField hint={methodOf("concepts")} origin={originOf("concepts")} htmlFor="concepts" label="Key concepts">
                <TagInput id="concepts" value={draft.concepts} disabled={registered || busy}
                  onChange={(v) => set("concepts", v)} placeholder="Add a concept and press Enter" />
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
                {/* Deletes the artifact, its bytes and anything derived from
                    it. Offered here because the alternative — leaving an
                    unwanted upload in the library — is worse. */}
                <Button
                  type="button"
                  variant="ghost"
                  loading={busy}
                  data-testid="discard-artifact"
                  onClick={() => {
                    if (window.confirm(`Delete ${artifact.filename}? This cannot be undone.`)) {
                      void discard();
                    }
                  }}
                >
                  Delete
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
