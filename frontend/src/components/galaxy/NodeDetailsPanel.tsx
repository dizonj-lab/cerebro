"use client";

import Link from "next/link";
import { useState } from "react";

import { colorFor } from "@/components/galaxy/palette";
import { api } from "@/lib/api";
import type { CerebroNodeDetails } from "@/lib/api";
import { cn } from "@/lib/cn";

const TABS = ["Overview", "Related", "Documents", "People"] as const;
type Tab = (typeof TABS)[number];

/**
 * Node details.
 *
 * Fetched per node rather than bundled with the graph, so opening the Galaxy
 * does not pull every node's documents and relationships with it.
 */
export function NodeDetailsPanel({
  details,
  loading,
  onClose,
  onSelectRelated,
}: {
  details: CerebroNodeDetails | null;
  loading: boolean;
  onClose: () => void;
  onSelectRelated: (id: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("Overview");

  if (loading && !details) {
    return (
      <aside className="w-full shrink-0 bg-scene-raised p-4 xl:w-[20rem]">
        <div className="h-5 w-32 animate-pulse rounded bg-scene-ink/10" />
        <div className="mt-4 h-20 animate-pulse rounded bg-scene-ink/5" />
      </aside>
    );
  }
  if (!details) return null;

  const accent = colorFor(details.category);

  return (
    <aside className="flex min-h-0 w-full shrink-0 flex-col bg-scene-raised xl:w-[20rem]">
      <div className="flex items-start justify-between gap-3 border-b border-scene-ink/10 p-4">
        <div className="min-w-0">
          <span
            className="mb-2 block size-8 rounded-full"
            style={{ background: accent, boxShadow: `0 0 18px ${accent}` }}
            aria-hidden="true"
          />
          <h2 className="text-base font-semibold text-scene-ink">{details.label}</h2>
          <span className="mt-1 inline-block rounded-md bg-scene-ink/10 px-2 py-0.5 text-[0.625rem] font-medium text-scene-ink/80">
            {details.type === "cluster" ? "Knowledge Cluster" : "Knowledge Fragment"}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close node details"
          className="rounded-md p-1.5 text-scene-ink/60 transition-colors hover:bg-scene-ink/10"
        >
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="m5.5 5.5 9 9M14.5 5.5l-9 9" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div className="flex gap-1 border-b border-scene-ink/10 px-2" role="tablist">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={cn(
              "border-b-2 px-2.5 py-2 text-xs font-medium transition-colors",
              tab === name
                ? "border-current text-scene-ink"
                : "border-transparent text-scene-ink/50 hover:text-scene-ink/80",
            )}
            style={tab === name ? { color: accent } : undefined}
          >
            {name}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 text-sm">
        {tab === "Overview" && <Overview details={details} />}
        {tab === "Related" && <Related details={details} onSelect={onSelectRelated} />}
        {tab === "Documents" && <Documents details={details} />}
        {tab === "People" && <People details={details} />}
      </div>
    </aside>
  );
}

function Overview({ details }: { details: CerebroNodeDetails }) {
  return (
    <div className="space-y-3">
      {details.description && (
        <p className="text-[0.8125rem] leading-relaxed text-scene-ink/80">{details.description}</p>
      )}
      <Row label="Type">{details.type === "cluster" ? "Cluster" : "Fragment"}</Row>
      <Row label="Category">{details.category}</Row>
      <Row label="Documents">{details.document_count}</Row>
      <Row label="Fragments">{details.fragment_count}</Row>
      <Row label="Relationships">{details.related.length}</Row>
      {/* Provenance is shown, not implied: everything here is registered,
          human-approved knowledge. */}
      <Row label="Provenance">Registered &amp; approved</Row>
      {details.source_location && Object.keys(details.source_location).length > 0 && (
        <Row label="Source location">{describeLocation(details.source_location)}</Row>
      )}

      {/* The other half of the pair: the Galaxy answers what relates to
          what, the Timeline answers when it happened. The focus travels so
          the subject survives the switch. */}
      {details.type === "cluster" && (
        <Link
          href={`/construct/timeline?focus=${encodeURIComponent(details.label)}`}
          className="inline-block pt-1 text-[0.75rem] font-medium text-sky-300 hover:underline"
        >
          See {details.label} over time →
        </Link>
      )}
    </div>
  );
}

function Related({
  details,
  onSelect,
}: {
  details: CerebroNodeDetails;
  onSelect: (id: string) => void;
}) {
  if (!details.related.length) {
    return <Empty>No connections yet. Register more documents sharing this topic.</Empty>;
  }
  return (
    <ul className="space-y-2">
      {details.related.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            onClick={() => onSelect(item.id)}
            className="w-full rounded-lg border border-scene-ink/10 p-2.5 text-left transition-colors hover:border-scene-ink/25 hover:bg-scene-ink/5"
          >
            <span className="block truncate text-[0.8125rem] font-medium text-scene-ink">
              {item.label}
            </span>
            <span className="mt-0.5 block text-[0.6875rem] text-scene-ink/50">{item.relevance}</span>
            {/* Why they are linked, so a co-occurrence is never mistaken for
                a verified semantic relationship. */}
            <span className="mt-1 block text-[0.6875rem] text-scene-ink/40">{item.explanation}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function Documents({ details }: { details: CerebroNodeDetails }) {
  if (!details.documents.length) return <Empty>No source documents.</Empty>;
  return (
    <ul className="space-y-2">
      {details.documents.map((doc) => (
        <li key={`${doc.artifact_id}-${doc.filename}`} className="rounded-lg border border-scene-ink/10 p-2.5">
          <p className="truncate text-[0.8125rem] font-medium text-scene-ink">
            {doc.title || doc.filename}
          </p>
          <p className="mt-0.5 truncate text-[0.6875rem] text-scene-ink/50">
            {doc.filename}
            {doc.source_location ? ` · ${describeLocation(doc.source_location)}` : ""}
          </p>
          {doc.excerpt && (
            <p className="mt-1.5 line-clamp-3 text-[0.6875rem] leading-relaxed text-scene-ink/60">
              “{doc.excerpt}”
            </p>
          )}
          <div className="mt-2 flex gap-3">
            <a
              href={api.artifactContentUrl(doc.artifact_id)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[0.6875rem] font-medium text-sky-300 underline-offset-2 hover:underline"
            >
              Open original
            </a>
            <Link
              href={`/construct/ingest?artifact=${doc.artifact_id}`}
              className="text-[0.6875rem] font-medium text-sky-300 underline-offset-2 hover:underline"
            >
              View artifact
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

function People({ details }: { details: CerebroNodeDetails }) {
  if (!details.people.length) {
    return (
      <Empty>
        No people recorded. People appear only where you confirmed them on a document —
        none are inferred.
      </Empty>
    );
  }
  return (
    <ul className="space-y-2">
      {details.people.map((person) => (
        <li key={person.name} className="rounded-lg border border-scene-ink/10 p-2.5">
          <p className="text-[0.8125rem] font-medium text-scene-ink">{person.name}</p>
          <p className="mt-0.5 text-[0.6875rem] text-scene-ink/50">{person.documents.join(", ")}</p>
        </li>
      ))}
    </ul>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-scene-ink/5 pb-2">
      <span className="text-[0.6875rem] text-scene-ink/50">{label}</span>
      <span className="text-right text-[0.8125rem] text-scene-ink/85">{children}</span>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-4 text-[0.75rem] leading-relaxed text-scene-ink/45">{children}</p>;
}

export function describeLocation(location: Record<string, number | string>): string {
  const parts: string[] = [];
  if (location.page) parts.push(`page ${location.page}`);
  if (location.slide) parts.push(`slide ${location.slide}`);
  if (location.section) parts.push(String(location.section));
  if (!parts.length && location.paragraph) parts.push(`paragraph ${location.paragraph}`);
  return parts.join(" · ") || "whole document";
}
