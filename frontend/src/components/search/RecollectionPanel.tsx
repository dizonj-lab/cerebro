"use client";

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { CerebroRecallAnswer } from "@/lib/api";

/**
 * Assisted Recollection beside the results.
 *
 * Retrieval-first and local-only: the service retrieves from the user's
 * registered documents and a local model only ever sees those passages. When
 * retrieval finds nothing, no model is called and the panel says so instead
 * of producing prose.
 *
 * Nothing is sent on typing, on a search, or on selecting a result. Only the
 * ask button sends.
 */
export function RecollectionPanel({
  question,
  onQuestionChange,
  topic,
}: {
  question: string;
  onQuestionChange: (value: string) => void;
  topic: string | null;
}) {
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState<CerebroRecallAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const asked = question.trim();
    if (!asked || busy) return;
    setBusy(true);
    setError(null);
    setReply(null);
    try {
      setReply(await api.recall({ question: asked, topic }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reach CEREBRO.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside
      aria-label="Assisted Recollection"
      data-testid="recollection-panel"
      className="flex w-full flex-col gap-3 rounded-lg border border-line bg-surface-subtle p-4 text-sm"
    >
      <div>
        <h2 className="font-semibold text-ink">Assisted Recollection</h2>
        <p className="mt-1 text-xs text-ink-muted">
          Answers are drawn from your registered documents and always cite them.
          Processing stays in the CEREBRO environment.
        </p>
      </div>

      <form onSubmit={ask} className="flex flex-col gap-2">
        <textarea
          value={question}
          onChange={(e) => onQuestionChange(e.target.value)}
          rows={3}
          aria-label="Ask about your knowledge"
          placeholder="Ask about what you have ingested..."
          className="w-full resize-y rounded-md border border-line bg-surface px-2.5 py-2 text-ink outline-none placeholder:text-ink-subtle focus:border-accent"
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="self-start rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {busy ? "Recollecting..." : "Ask"}
        </button>
      </form>

      {error && <p className="text-xs text-danger">{error}</p>}

      {reply && (
        <div data-testid="recollection-answer" className="flex flex-col gap-2">
          {reply.answer ? (
            <p className="whitespace-pre-wrap text-ink">{reply.answer}</p>
          ) : (
            <p className="text-ink-muted">
              {reply.note ?? "No passage in your library answers this."}
            </p>
          )}
          {reply.sources.length > 0 && (
            <ol className="flex flex-col gap-1.5 border-t border-line pt-2 text-xs">
              {reply.sources.map((source) => (
                <li key={source.fragment_id} className="text-ink-muted">
                  <span className="font-medium text-ink">[{source.index}]</span>{" "}
                  <a
                    href={api.artifactContentUrl(source.artifact_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent hover:underline"
                  >
                    {source.title || source.filename}
                  </a>
                  <span className="block text-ink-subtle">{source.excerpt}</span>
                </li>
              ))}
            </ol>
          )}
          {reply.answer && reply.model && (
            <p className="text-xs text-ink-subtle">Phrased locally by {reply.model}.</p>
          )}
        </div>
      )}
    </aside>
  );
}
