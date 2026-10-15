"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ArtifactStatus, formatBytes } from "@/components/construct/ArtifactStatus";
import { PageHeader } from "@/components/construct/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { LoadingState } from "@/components/ui/LoadingState";
import { ApiError, api } from "@/lib/api";
import type { CerebroArtifactSummary } from "@/lib/api";

export function LibraryView() {
  const [items, setItems] = useState<CerebroArtifactSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
            <li key={a.id}>
              <Link
                href={`/construct/ingest?artifact=${a.id}`}
                className="flex items-start justify-between gap-4 py-3.5 transition-colors hover:bg-surface-subtle"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink">
                    {a.title || a.filename}
                  </span>
                  <span className="mt-0.5 block truncate font-mono text-xs text-ink-subtle">
                    {a.filename} · {formatBytes(a.size_bytes)} · {a.modality}
                  </span>
                </span>
                <ArtifactStatus status={a.status} className="mt-0.5 shrink-0" />
              </Link>
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
