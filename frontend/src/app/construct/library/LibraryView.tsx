"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ArtifactStatus, formatBytes } from "@/components/construct/ArtifactStatus";
import { PageHeader } from "@/components/construct/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { LoadingState } from "@/components/ui/LoadingState";
import { EnrichmentQueue } from "@/components/construct/EnrichmentQueue";
import { ApiError, api } from "@/lib/api";
import { useEnrichmentQueue } from "@/lib/useEnrichmentQueue";
import type { CerebroArtifactSummary } from "@/lib/api";

export function LibraryView() {
  const { queue } = useEnrichmentQueue();
  const [items, setItems] = useState<CerebroArtifactSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function remove(artifact: CerebroArtifactSummary) {
    // Confirmed first, and the warning says what goes with it: deleting a
    // registered document removes the knowledge retrieved from it too.
    const extra =
      artifact.status === "registered"
        ? " Its knowledge fragments and embeddings go with it."
        : "";
    if (!window.confirm(`Delete ${artifact.filename}?${extra} This cannot be undone.`)) return;

    setError(null);
    setDeleting(artifact.id);
    try {
      await api.deleteArtifact(artifact.id);
      setItems((current) => current.filter((item) => item.id !== artifact.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete that artifact.");
    } finally {
      setDeleting(null);
    }
  }

  useEffect(() => {
    api
      .artifacts()
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your library."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState label="Loading your library" className="mt-2" />;

  return (
    <div className="mx-auto max-w-3xl pb-4">
      <PageHeader
        title="Library"
        description="Every artifact your knowledge twin is built from."
        action={
          <Link href="/construct/ingest">
            <Button>Add artifact</Button>
          </Link>
        }
      />

      <ErrorMessage className="mt-5">{error}</ErrorMessage>

      {/* The queue belongs to the server, so it is the same here as on
          Ingest — including work started before this page was opened, which
          is what leaving the page used to destroy. */}
      <EnrichmentQueue queue={queue} className="mt-5" />

      {items.length === 0 && !error ? (
        <div className="mt-8 rounded-lg border border-line bg-surface-subtle p-6 text-center">
          <p className="text-sm font-medium text-ink">Nothing captured yet.</p>
          <p className="mx-auto mt-1.5 max-w-sm text-sm text-ink-muted">
            Add a document and CEREBRO will inspect it, draft its metadata and wait for you to
            confirm what it got right.
          </p>
          <Link href="/construct/ingest" className="mt-5 inline-block">
            <Button variant="secondary">Add your first artifact</Button>
          </Link>
        </div>
      ) : (
        <ul className="mt-6 divide-y divide-line border-y border-line">
          {items.map((a) => (
            <li key={a.id} className="flex items-start justify-between gap-3 py-3.5">
              {/* The row and the open control are siblings: an anchor inside
                  an anchor is invalid, and nesting them would make the whole
                  row behave unpredictably. */}
              <Link
                href={`/construct/ingest?artifact=${a.id}`}
                className="-my-1.5 min-w-0 flex-1 rounded-md px-1 py-1.5 transition-colors hover:bg-surface-subtle"
              >
                <span className="block truncate text-sm font-medium text-ink">
                  {a.title || a.filename}
                </span>
                <span className="mt-0.5 block truncate font-mono text-xs text-ink-subtle">
                  {a.filename} · {formatBytes(a.size_bytes)} · {a.modality}
                </span>
              </Link>
              <div className="flex shrink-0 items-center gap-3 pt-0.5">
                <ArtifactStatus status={a.status} />
                <a
                  href={api.artifactContentUrl(a.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-md text-xs font-medium text-accent underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
                >
                  Open original
                  <span className="sr-only"> document {a.filename} in a new tab</span>
                </a>
                <button
                  type="button"
                  onClick={() => void remove(a)}
                  disabled={deleting === a.id}
                  data-testid="delete-artifact"
                  className="rounded-md text-xs font-medium text-ink-muted underline-offset-2 transition-colors hover:text-danger hover:underline disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
                >
                  {deleting === a.id ? "Deleting" : "Delete"}
                  <span className="sr-only"> {a.filename}</span>
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {items.length > 0 && (
        <p className="mt-4 text-xs text-ink-subtle">
          {items.length} artifact{items.length === 1 ? "" : "s"} ·{" "}
          {items.filter((a) => a.status === "registered").length} registered
        </p>
      )}
    </div>
  );
}
