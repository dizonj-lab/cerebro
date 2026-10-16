"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { formatBytes } from "@/components/construct/ArtifactStatus";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { Input } from "@/components/ui/Input";
import { TagInput } from "@/components/ui/TagInput";
import { ApiError, api } from "@/lib/api";
import type { CerebroArtifact, CerebroArtifactMetadata } from "@/lib/api";
import { cn } from "@/lib/cn";

type RowState = "awaiting" | "enriching" | "registering" | "registered" | "failed";

interface Row {
  artifact: CerebroArtifact;
  title: string;
  topics: string[];
  tags: string[];
  state: RowState;
  error?: string;
  /** Set once a model has proposed for this row, so the label can say so. */
  enrichedBy?: string | null;
  note?: string;
}

/** Files the server refused, kept visible so nothing disappears silently. */
interface Refused {
  filename: string;
  error: string;
}

/**
 * Bulk ingestion.
 *
 * The same pipeline as a single upload, shown as a table: each file is
 * inspected, extracted and enriched on upload, and registering a row runs
 * the identical approval path — checksum re-verification, then chunking and
 * embedding. There is no second pipeline and no bulk shortcut past review:
 * every row's metadata is still confirmed by a human before it counts as
 * knowledge.
 */
export function BulkIngest({
  initialFiles,
  onDone,
}: {
  /** Files already chosen on the ingest page, uploaded as soon as this mounts. */
  initialFiles?: File[];
  onDone?: () => void;
}) {
  const [rows, setRows] = useState<Row[]>([]);
  const [refused, setRefused] = useState<Refused[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback(async (list: FileList | File[] | null) => {
    if (!list || list.length === 0) return;
    setError(null);
    setBusy(true);
    try {
      const result = await api.uploadArtifacts([...list]);
      setRows((current) => [
        ...current,
        ...result.items
          .filter((item) => item.accepted && item.artifact)
          .map((item) => toRow(item.artifact!)),
      ]);
      setRefused((current) => [
        ...current,
        ...result.items
          .filter((item) => !item.accepted)
          .map((item) => ({ filename: item.filename, error: item.error ?? "Refused." })),
      ]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add those files.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, []);

  /*
    Uploads what the ingest page already collected. The page decides between
    the form and this table by counting the files, so they arrive here rather
    than being chosen again.
  */
  const started = useRef(false);
  useEffect(() => {
    if (!initialFiles?.length || started.current) return;
    started.current = true;
    void addFiles(initialFiles);
  }, [initialFiles, addFiles]);

  async function remove(id: string) {
    setError(null);
    try {
      await api.deleteArtifact(id);
      setRows((current) => current.filter((row) => row.artifact.id !== id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete that artifact.");
    }
  }

  function update(id: string, patch: Partial<Row>) {
    setRows((current) => current.map((row) => (row.artifact.id === id ? { ...row, ...patch } : row)));
  }

  /**
   * Ask the local model to propose metadata for these rows.
   *
   * One row at a time: a model on a laptop takes tens of seconds each, and a
   * burst of parallel requests would simply queue inside Ollama while making
   * the progress impossible to follow. Each row updates as it returns.
   */
  async function enrich(ids: string[]) {
    const pending = rows.filter(
      (row) => ids.includes(row.artifact.id) && row.state === "awaiting",
    );
    if (!pending.length || busy) return;

    setError(null);
    setBusy(true);
    setRows((current) =>
      current.map((row) =>
        ids.includes(row.artifact.id) && row.state === "awaiting"
          ? { ...row, state: "enriching", error: undefined }
          : row,
      ),
    );

    for (const row of pending) {
      try {
        const result = await api.suggestArtifact(row.artifact.id);
        setRows((current) =>
          current.map((item) =>
            item.artifact.id === row.artifact.id
              ? {
                  ...item,
                  state: "awaiting",
                  // Suggestions land in the row, where they can still be
                  // edited. Nothing is saved until the row is registered.
                  title: (result.suggestions.title as string) ?? item.title,
                  topics: (result.suggestions.topics as string[]) ?? item.topics,
                  tags: (result.suggestions.tags as string[]) ?? item.tags,
                  enrichedBy: result.ai_used ? result.model ?? result.engine : null,
                  note: result.ai_used ? undefined : result.notes[0],
                }
              : item,
          ),
        );
      } catch (e) {
        const message = e instanceof ApiError ? e.message : "Could not ask the local model.";
        setRows((current) =>
          current.map((item) =>
            item.artifact.id === row.artifact.id
              ? { ...item, state: "awaiting", error: message }
              : item,
          ),
        );
      }
    }
    setBusy(false);
  }

  async function register(ids: string[]) {
    const pending = rows.filter((row) => ids.includes(row.artifact.id) && row.state !== "registered");
    if (!pending.length) return;

    setError(null);
    setBusy(true);
    setRows((current) =>
      current.map((row) =>
        ids.includes(row.artifact.id) && row.state !== "registered"
          ? { ...row, state: "registering", error: undefined }
          : row,
      ),
    );

    try {
      const result = await api.reviewArtifacts(
        pending.map((row) => ({
          id: row.artifact.id,
          metadata: metadataOf(row),
        })),
        true,
      );
      setRows((current) =>
        current.map((row) => {
          const outcome = result.items.find((item) => item.id === row.artifact.id);
          if (!outcome) return row;
          return {
            ...row,
            state: outcome.registered ? "registered" : "failed",
            error: outcome.error ?? undefined,
          };
        }),
      );
      if (result.registered > 0) onDone?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not register those artifacts.");
      setRows((current) =>
        current.map((row) => (ids.includes(row.artifact.id) ? { ...row, state: "awaiting" } : row)),
      );
    } finally {
      setBusy(false);
    }
  }

  const awaiting = rows.filter((row) => row.state === "awaiting" || row.state === "failed");


  return (
    <div className="mt-6">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void addFiles(e.dataTransfer.files);
        }}
        className={cn(
          "rounded-lg border border-dashed p-6 text-center transition-colors",
          dragging ? "border-accent bg-accent-subtle" : "border-line-strong bg-surface-subtle",
        )}
      >
        <p className="text-sm font-medium text-ink">Drop more documents here</p>
        <p className="mx-auto mt-1 max-w-md text-xs text-ink-muted">
          Up to 25 at a time. Each is inspected and extracted on arrival; nothing is
          registered until you confirm it below.
        </p>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.docx,.pptx,.txt,.md,.markdown,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
          className="sr-only"
          onChange={(e) => void addFiles(e.target.files)}
        />
        <Button
          variant="secondary"
          className="mt-4"
          loading={busy}
          onClick={() => fileRef.current?.click()}
        >
          {busy ? "Working" : "Choose files"}
        </Button>
      </div>

      <ErrorMessage className="mt-4">{error}</ErrorMessage>

      {refused.length > 0 && (
        <ul className="mt-4 space-y-1.5" data-testid="refused-files">
          {refused.map((item) => (
            <li
              key={item.filename}
              className="rounded-md border border-danger/30 bg-danger-subtle px-3 py-2 text-xs text-danger"
            >
              <span className="font-medium">{item.filename}</span> — {item.error}
            </li>
          ))}
        </ul>
      )}

      {rows.length > 0 && (
        <>
          <div className="mt-6 overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[52rem] text-left text-sm">
              <thead className="border-b border-line bg-surface-subtle text-xs text-ink-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">File</th>
                  <th scope="col" className="px-3 py-2 font-medium">Title</th>
                  <th scope="col" className="px-3 py-2 font-medium">Topics</th>
                  <th scope="col" className="px-3 py-2 font-medium">Tags</th>
                  <th scope="col" className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((row) => {
                  const locked = row.state === "registered" || row.state === "registering";
                  return (
                    <tr key={row.artifact.id} className="align-top">
                      <td className="px-3 py-2.5">
                        <span className="block max-w-[14rem] truncate font-medium text-ink">
                          {row.artifact.filename}
                        </span>
                        <span className="mt-0.5 block font-mono text-[0.6875rem] text-ink-subtle">
                          {row.artifact.modality} · {formatBytes(row.artifact.size_bytes)}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <Input
                          aria-label={`Title for ${row.artifact.filename}`}
                          value={row.title}
                          disabled={locked}
                          onChange={(e) => update(row.artifact.id, { title: e.target.value })}
                        />
                      </td>
                      <td className="min-w-[13rem] px-3 py-2.5">
                        <TagInput
                          id={`topics-${row.artifact.id}`}
                          aria-label={`Topics for ${row.artifact.filename}`}
                          value={row.topics}
                          disabled={locked}
                          onChange={(v) => update(row.artifact.id, { topics: v })}
                          placeholder="Add a topic"
                        />
                      </td>
                      <td className="min-w-[13rem] px-3 py-2.5">
                        <TagInput
                          id={`tags-${row.artifact.id}`}
                          aria-label={`Tags for ${row.artifact.filename}`}
                          value={row.tags}
                          disabled={locked}
                          onChange={(v) => update(row.artifact.id, { tags: v })}
                          placeholder="Add a tag"
                        />
                      </td>
                      <td className="px-3 py-2.5">
                        <RowStatus
                          row={row}
                          onRegister={() => void register([row.artifact.id])}
                          onEnrich={() => void enrich([row.artifact.id])}
                          onRemove={() => {
                            if (
                              window.confirm(
                                `Delete ${row.artifact.filename}? This cannot be undone.`,
                              )
                            ) {
                              void remove(row.artifact.id);
                            }
                          }}
                          busy={busy}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              loading={busy}
              disabled={awaiting.length === 0}
              onClick={() => void register(awaiting.map((row) => row.artifact.id))}
            >
              Confirm and register {awaiting.length || ""}
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              disabled={awaiting.length === 0}
              onClick={() => void enrich(awaiting.map((row) => row.artifact.id))}
            >
              Enrich all with local AI
            </Button>
            <Link href="/construct/library">
              <Button variant="ghost">Library</Button>
            </Link>
            <p className="w-full text-xs text-ink-subtle">
              Registering re-verifies each file against its checksum, then chunks and embeds
              it so it can be searched. Rows you leave stay as drafts.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

function RowStatus({
  row,
  onRegister,
  onEnrich,
  onRemove,
  busy,
}: {
  row: Row;
  onRegister: () => void;
  onEnrich: () => void;
  onRemove: () => void;
  busy: boolean;
}) {
  if (row.state === "enriching") {
    return <span className="text-[0.6875rem] text-ink-subtle">Asking the model…</span>;
  }
  if (row.state === "registered") {
    return (
      <span
        data-testid="row-registered"
        className="rounded-md bg-success/12 px-2 py-1 text-[0.6875rem] font-medium text-success"
      >
        Registered
      </span>
    );
  }
  if (row.state === "registering") {
    return <span className="text-[0.6875rem] text-ink-subtle">Registering…</span>;
  }
  return (
    <div className="space-y-1">
      <div className="flex gap-1.5">
        <button
          type="button"
          onClick={onRegister}
          className="rounded-md border border-line px-2 py-1 text-[0.6875rem] font-medium text-ink-muted transition-colors hover:border-accent hover:text-accent"
        >
          Register
        </button>
        <button
          type="button"
          onClick={onRemove}
          data-testid="row-delete"
          title="Delete this file and anything derived from it"
          className="rounded-md border border-line px-2 py-1 text-[0.6875rem] font-medium text-ink-muted transition-colors hover:border-danger hover:text-danger"
        >
          Delete
        </button>
        <button
          type="button"
          onClick={onEnrich}
          disabled={busy}
          title="Ask the local model to propose metadata for this row"
          className="rounded-md border border-line px-2 py-1 text-[0.6875rem] font-medium text-ink-muted transition-colors hover:border-accent hover:text-accent disabled:opacity-40"
        >
          Enrich
        </button>
      </div>
      {row.enrichedBy && (
        <p className="max-w-[12rem] text-[0.625rem] text-ink-subtle">
          Suggested by {row.enrichedBy}. Check before confirming.
        </p>
      )}
      {row.note && <p className="max-w-[12rem] text-[0.625rem] text-ink-subtle">{row.note}</p>}
      {row.error && <p className="max-w-[12rem] text-[0.625rem] text-danger">{row.error}</p>}
    </div>
  );
}

function toRow(artifact: CerebroArtifact): Row {
  const metadata = artifact.metadata;
  return {
    artifact,
    // Prefilled by the same enrichment a single upload runs; still a draft.
    title: metadata.title ?? "",
    topics: metadata.topics ?? [],
    tags: metadata.tags ?? [],
    state: "awaiting",
  };
}

function metadataOf(row: Row): CerebroArtifactMetadata {
  return {
    ...row.artifact.metadata,
    title: row.title,
    topics: row.topics,
    tags: row.tags,
  };
}
