"use client";

import { useRef, useState } from "react";

import { api } from "@/lib/api";
import type { CerebroRecallSource, CerebroRecallTelemetry } from "@/lib/api";
import { streamRecall } from "@/lib/recallStream";

/**
 * Assisted Recollection beside the results.
 *
 * Retrieval-first and local-only: the service retrieves from the user's
 * registered documents and a local model only ever sees those passages. When
 * retrieval finds nothing, no model is called and the panel says so instead
 * of producing prose.
 *
 * The answer streams. Sources appear before the first word, so the evidence
 * can be read while the answer is still being written, and what the run cost
 * is shown when it finishes — model, duration and the daemon's own token
 * counts, not an estimate.
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
  const [sources, setSources] = useState<CerebroRecallSource[]>([]);
  const [answer, setAnswer] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<CerebroRecallTelemetry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState(false);
  // One exchange of memory: enough for a follow-up, and it never becomes
  // evidence — retrieval runs again for every question.
  const lastExchange = useRef<{ question: string; answer: string } | null>(null);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setAnswer("");
    setNote(null);
    setTelemetry(null);
    setSources([]);
    setAsked(true);
    try {
      const history = lastExchange.current ? [lastExchange.current] : [];
      await streamRecall({ question: text, topic, history }, (event_) => {
        if (event_.type === "sources") setSources(event_.sources);
        else if (event_.type === "delta") setAnswer((a) => a + event_.text);
        else if (event_.type === "error") setError(event_.message);
        else {
          // The final event carries the whole answer, with citations to
          // passages that do not exist already removed. It replaces the
          // streamed text rather than appending to it.
          if (event_.answer !== null) {
            setAnswer(event_.answer);
            lastExchange.current = { question: text, answer: event_.answer };
          }
          setNote(event_.note);
          setTelemetry(event_.telemetry);
        }
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reach CEREBRO.");
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

      {asked && !error && (
        <div data-testid="recollection-answer" className="flex flex-col gap-2">
          {answer ? (
            <p className="whitespace-pre-wrap text-ink">{answer}</p>
          ) : (
            busy && <p className="text-ink-muted">Reading your library...</p>
          )}
          {note && <p className="text-xs text-ink-muted">{note}</p>}

          {sources.length > 0 && (
            <ol className="flex flex-col gap-1.5 border-t border-line pt-2 text-xs">
              {sources.map((source) => (
                <li key={source.fragment_id} className="text-ink-muted">
                  <span className="font-medium text-ink">[{source.index}]</span>{" "}
                  {/* Clickable: every citation resolves to the stored original. */}
                  <a
                    href={api.artifactContentUrl(source.artifact_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent hover:underline"
                  >
                    {source.title || source.filename}
                  </a>
                  {describeLocation(source.source_location)}
                  <span className="block text-ink-subtle">{source.excerpt}</span>
                </li>
              ))}
            </ol>
          )}

          {/* What actually ran. Measured by the daemon, not asserted here. */}
          {telemetry && (
            <p data-testid="recollection-telemetry" className="text-xs text-ink-subtle">
              {telemetry.model}
              {telemetry.duration_ms !== null && ` · ${telemetry.duration_ms} ms`}
              {telemetry.completion_tokens !== null &&
                ` · ${telemetry.completion_tokens} tokens out`}
              {telemetry.prompt_tokens !== null && ` · ${telemetry.prompt_tokens} in`}
              {` · ${telemetry.passages} passages, top score ${telemetry.top_score.toFixed(3)}`}
            </p>
          )}
        </div>
      )}
    </aside>
  );
}

function describeLocation(location: Record<string, number | string>): string {
  const parts = Object.entries(location)
    .filter(([, value]) => value !== null && value !== "")
    .map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`);
  // Only what extraction established; a modality without pages has none.
  return parts.length > 0 ? ` · ${parts.join(", ")}` : "";
}
