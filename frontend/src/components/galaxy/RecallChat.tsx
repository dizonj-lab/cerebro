"use client";

import { useRef, useState } from "react";

import { api } from "@/lib/api";
import type { CerebroRecallAnswer } from "@/lib/api";
import { streamRecall } from "@/lib/recallStream";
import { cn } from "@/lib/cn";

interface Turn {
  question: string;
  reply: CerebroRecallAnswer | null;
  error?: string;
}

/**
 * Assisted Recollection.
 *
 * Anchored to the lower right of the workspace, collapsed to a launcher until
 * asked for. Nothing is sent anywhere until the user presses send: no request
 * on selection, on hover, or while the Galaxy is being moved.
 *
 * Answers are grounded by construction — the service retrieves from the
 * user's registered documents first and a model only ever sees those
 * passages — so every reply shows its sources.
 */
export function RecallChat({
  topic,
  onShowMe,
}: {
  topic: string | null;
  /** Light up the part of the map this answer was built from. */
  onShowMe?: (reply: CerebroRecallAnswer) => void;
}) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const log = useRef<HTMLDivElement>(null);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const asked = question.trim();
    if (!asked || busy) return;

    setQuestion("");
    setTurns((t) => [...t, { question: asked, reply: null }]);
    setBusy(true);

    const update = (patch: (reply: CerebroRecallAnswer) => CerebroRecallAnswer) =>
      setTurns((t) =>
        t.map((turn, i) =>
          i === t.length - 1
            ? {
                ...turn,
                reply: patch(
                  turn.reply ?? {
                    answer: null,
                    sources: [],
                    grounded: false,
                    model: null,
                    note: null,
                  },
                ),
              }
            : turn,
        ),
      );

    // The last few exchanges, so "what about the other one?" is answerable.
    // Evidence is still retrieved fresh for every question; this only helps
    // the model read what was asked.
    const history = turns
      .filter((turn) => turn.reply?.answer)
      .slice(-3)
      .map((turn) => ({ question: turn.question, answer: turn.reply?.answer ?? "" }));

    try {
      await streamRecall({ question: asked, topic, history }, (e) => {
        if (e.type === "sources") {
          // Evidence first: the citations are readable while the answer is
          // still being written.
          update((reply) => ({ ...reply, sources: e.sources, grounded: e.sources.length > 0 }));
        } else if (e.type === "delta") {
          update((reply) => ({ ...reply, answer: (reply.answer ?? "") + e.text }));
        } else if (e.type === "error") {
          setTurns((t) =>
            t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: e.message } : turn)),
          );
        } else {
          update((reply) => ({
            ...reply,
            // The final answer has citations to absent passages removed, so
            // it replaces what was streamed rather than extending it.
            answer: e.answer ?? reply.answer,
            grounded: e.grounded,
            model: e.model,
            note: e.note,
            cited: e.cited,
            abstained: e.abstained,
            telemetry: e.telemetry,
          }));
        }
        requestAnimationFrame(() => log.current?.scrollTo({ top: log.current.scrollHeight }));
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not reach CEREBRO.";
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: message } : turn)));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => log.current?.scrollTo({ top: log.current.scrollHeight }));
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="absolute bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full border border-scene-ink/15 bg-scene-raised/95 px-4 py-2.5 text-sm font-medium text-scene-ink shadow-xl backdrop-blur transition-colors hover:bg-scene-hover"
      >
        <Spark />
        Ask CEREBRO
      </button>
    );
  }

  return (
    <section className="absolute bottom-4 right-4 z-30 flex h-[23rem] w-[21rem] max-w-[calc(100%-2rem)] flex-col rounded-xl border border-scene-ink/15 bg-scene-overlay/97 shadow-2xl backdrop-blur">
      <header className="flex items-center justify-between gap-2 border-b border-scene-ink/10 px-3 py-2.5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-scene-ink">
          <Spark />
          Ask CEREBRO
        </h2>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Close chat"
          className="rounded-md p-1 text-scene-ink/60 transition-colors hover:bg-scene-ink/10"
        >
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="m5.5 5.5 9 9M14.5 5.5l-9 9" strokeLinecap="round" />
          </svg>
        </button>
      </header>

      {/* What the question will be answered against, stated rather than implied. */}
      <p className="border-b border-scene-ink/10 px-3 py-1.5 text-[0.625rem] text-scene-ink/45">
        {topic ? `Context: ${topic} · ` : ""}Answers come from your registered documents.
      </p>

      <div ref={log} className="flex-1 space-y-3 overflow-y-auto p-3">
        {turns.length === 0 && (
          <p className="text-[0.75rem] leading-relaxed text-scene-ink/45">
            Ask what a concept means, where you learned it, or which documents discuss it.
            Every answer cites the documents it came from.
          </p>
        )}
        {turns.map((turn, i) => (
          <div key={`${turn.question}-${i}`} className="space-y-2">
            <p className="ml-auto w-fit max-w-[85%] rounded-lg rounded-br-sm bg-sky-500/20 px-2.5 py-1.5 text-[0.75rem] text-scene-ink">
              {turn.question}
            </p>
            {turn.error ? (
              <p className="text-[0.75rem] text-rose-300">{turn.error}</p>
            ) : turn.reply ? (
              <Reply reply={turn.reply} onShowMe={onShowMe} />
            ) : (
              <p className="text-[0.75rem] text-scene-ink/40">Searching your library…</p>
            )}
          </div>
        ))}
      </div>

      <form onSubmit={send} className="flex items-center gap-2 border-t border-scene-ink/10 p-2.5">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          aria-label="Ask or describe what you're looking for"
          placeholder="Ask or describe what you're looking for…"
          className="w-full rounded-lg border border-scene-ink/12 bg-scene-ink/5 px-2.5 py-2 text-[0.75rem] text-scene-ink outline-none placeholder:text-scene-ink/35 focus:border-sky-400/60"
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="shrink-0 rounded-lg bg-sky-500 px-3 py-2 text-[0.75rem] font-medium text-on-bright transition-opacity disabled:opacity-40"
        >
          {busy ? "…" : "Send"}
        </button>
      </form>
    </section>
  );
}

function Reply({
  reply,
  onShowMe,
}: {
  reply: CerebroRecallAnswer;
  onShowMe?: (reply: CerebroRecallAnswer) => void;
}) {
  return (
    <div className="w-fit max-w-[92%] space-y-2 rounded-lg rounded-bl-sm bg-scene-ink/8 px-2.5 py-2">
      {reply.answer ? (
        <p className="text-[0.75rem] leading-relaxed text-scene-ink/90">{reply.answer}</p>
      ) : reply.sources.length > 0 ? (
        <p className="text-[0.75rem] leading-relaxed text-scene-ink/75">
          Found {reply.sources.length} passage{reply.sources.length === 1 ? "" : "s"} in your
          library:
        </p>
      ) : null}

      {/* What ran, from the daemon's own accounting. */}
      {reply.telemetry && (
        <p data-testid="chat-telemetry" className="text-[0.625rem] text-scene-ink/45">
          {reply.telemetry.model}
          {reply.telemetry.duration_ms !== null && ` · ${reply.telemetry.duration_ms} ms`}
          {reply.telemetry.completion_tokens !== null &&
            ` · ${reply.telemetry.completion_tokens} tokens`}
        </p>
      )}

      {reply.note && <p className="text-[0.625rem] text-scene-ink/50">{reply.note}</p>}

      {/* Maps the answer onto the galaxy: what it quoted, what it merely
          found, and what it did not touch. */}
      {onShowMe && reply.sources.length > 0 && (
        <button
          type="button"
          data-testid="show-me"
          onClick={() => onShowMe(reply)}
          className="rounded-md border border-sky-400/40 px-2 py-1 text-[0.6875rem] font-medium text-sky-300 transition-colors hover:bg-sky-400/10"
        >
          Show me on the map
        </button>
      )}

      {reply.sources.map((source) => (
        <a
          key={source.fragment_id}
          href={api.artifactContentUrl(source.artifact_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="block rounded-md border border-scene-ink/10 p-2 transition-colors hover:border-scene-ink/25"
        >
          <span className="block text-[0.6875rem] font-medium text-sky-300">
            [{source.index}] {source.title || source.filename}
            {source.source_location?.page ? ` · page ${source.source_location.page}` : ""}
          </span>
          <span className="mt-0.5 block line-clamp-2 text-[0.6875rem] leading-relaxed text-scene-ink/55">
            {source.excerpt}
          </span>
        </a>
      ))}

      {reply.note && <p className="text-[0.625rem] text-scene-ink/40">{reply.note}</p>}
      {reply.model && (
        <p className="text-[0.625rem] text-scene-ink/35">
          Phrased by {reply.model}, running in your CEREBRO environment.
        </p>
      )}
    </div>
  );
}

function Spark() {
  return (
    <svg viewBox="0 0 20 20" className={cn("size-4 shrink-0 text-sky-400")} fill="currentColor" aria-hidden="true">
      <path d="M10 2.5l1.6 4.4 4.4 1.6-4.4 1.6L10 14.5 8.4 10.1 4 8.5l4.4-1.6z" />
    </svg>
  );
}
