"use client";

import Link from "next/link";
import { useState } from "react";

import { api } from "@/lib/api";

/**
 * The five actions a result offers.
 *
 * Each one resolves to something that exists: the stored original, the
 * review screen for that artifact, a grounded question about the passage, a
 * citation naming the source location extraction established, and a filter
 * on a confirmed topic. Nothing here infers a location or a relationship.
 */
export interface ResultActionsProps {
  artifactId: string;
  filename: string;
  title: string | null;
  sourceLocation?: Record<string, number | string>;
  excerpt?: string;
  topic?: string | null;
  onAsk: () => void;
  onFilterTopic?: (topic: string) => void;
}

export function citation(
  filename: string,
  title: string | null,
  sourceLocation: Record<string, number | string> = {},
): string {
  // Only the keys extraction actually established. A missing page is absent
  // from the citation rather than guessed as page 1.
  const parts = Object.entries(sourceLocation)
    .filter(([, value]) => value !== null && value !== "")
    .map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`);
  const where = parts.length > 0 ? `, ${parts.join(", ")}` : "";
  return `${title || filename} (${filename}${where})`;
}

export function ResultActions({
  artifactId,
  filename,
  title,
  sourceLocation,
  topic,
  onAsk,
  onFilterTopic,
}: ResultActionsProps) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    const text = citation(filename, title, sourceLocation);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard access can be refused. Say nothing rather than claiming a
      // copy that did not happen.
      setCopied(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 pt-2 text-xs">
      <a
        href={api.artifactContentUrl(artifactId)}
        target="_blank"
        rel="noreferrer"
        className="font-medium text-accent hover:underline"
      >
        Open source
      </a>
      <Link
        href={`/construct/ingest?artifact=${artifactId}`}
        className="font-medium text-ink-muted hover:text-ink hover:underline"
      >
        Open in library
      </Link>
      <button
        type="button"
        onClick={onAsk}
        className="font-medium text-ink-muted hover:text-ink hover:underline"
      >
        Ask about this
      </button>
      <button
        type="button"
        onClick={copy}
        className="font-medium text-ink-muted hover:text-ink hover:underline"
      >
        {copied ? "Citation copied" : "Copy citation"}
      </button>
      {topic && onFilterTopic && (
        <button
          type="button"
          onClick={() => onFilterTopic(topic)}
          className="font-medium text-ink-muted hover:text-ink hover:underline"
        >
          More on {topic}
        </button>
      )}
    </div>
  );
}
