"use client";

import { usePathname, useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { api } from "@/lib/api";
import type { CerebroRecallAnswer } from "@/lib/api";
import { createPersistedStore } from "@/lib/persistedStore";
import { queueMap, useRecallContext } from "@/lib/recallContext";
import { streamRecall } from "@/lib/recallStream";
import { cn } from "@/lib/cn";

/** Where the chat window was left, and whether it was open. x below zero docks it bottom right. */
const useRecallWindow = createPersistedStore("cerebro-recall-window", { open: false, x: -1, y: -1 });

const WIDTH = 352;
const HEIGHT = 432;

interface Turn {
  question: string;
  reply: CerebroRecallAnswer | null;
  error?: string;
}

/**
 * Assisted Recollection.
 *
 * Available on every page, floating above it: collapsed to a launcher at the
 * lower right until asked for, then a window the user can drag anywhere —
 * where it was left, and whether it was open, is remembered. Nothing is sent
 * anywhere until the user presses send: no request on selection, on hover,
 * or while the Galaxy is being moved.
 *
 * The page supplies context (see lib/recallContext): the Galaxy's topic in
 * focus, and a way to map an answer. From any other page, "Show me on the
 * map" opens the Galaxy with the answer mapped, and "See on the timeline"
 * opens the Timeline on the answer's topic.
 *
 * Answers are grounded by construction — the service retrieves from the
 * user's registered documents first and a model only ever sees those
 * passages — so every reply shows its sources.
 */
export function RecallChat() {
  const { topic, showMe } = useRecallContext();
  const router = useRouter();
  const pathname = usePathname();
  const [win, setWin] = useRecallWindow();
  const open = win.open;
  const setOpen = (value: boolean) => setWin({ open: value });
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const log = useRef<HTMLDivElement>(null);

  // Follow a streaming answer only while the reader is at the bottom. It used
  // to scroll to the end on every token, so scrolling up to reread something
  // was pulled back down — the chat fought the reader.
  const follow = useRef(true);
  function onScroll() {
    const el = log.current;
    if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  }
  function toEnd(force = false) {
    if (force) follow.current = true;
    if (!follow.current) return;
    requestAnimationFrame(() => log.current?.scrollTo({ top: log.current.scrollHeight }));
  }

  function onShowMe(reply: CerebroRecallAnswer) {
    if (showMe && pathname?.startsWith("/construct/galaxy")) {
      showMe(reply);
      return;
    }
    queueMap(reply);
    router.push("/construct/galaxy");
  }
  function onTimeline(reply: CerebroRecallAnswer) {
    const first = reply.sources.flatMap((s) => s.topics ?? [])[0];
    router.push(first ? `/construct/timeline?focus=${encodeURIComponent(first)}` : "/construct/timeline");
  }

  function startDrag(event: React.PointerEvent<HTMLElement>) {
    if ((event.target as Element).closest("button")) return;
    const box = (event.currentTarget.closest("section") as HTMLElement | null)?.getBoundingClientRect();
    if (!box) return;
    event.preventDefault();
    const start = { px: event.clientX, py: event.clientY, x: box.left, y: box.top };
    const move = (e: PointerEvent) =>
      setWin({
        x: Math.round(Math.min(Math.max(0, start.x + e.clientX - start.px), globalThis.innerWidth - box.width)),
        y: Math.round(Math.min(Math.max(0, start.y + e.clientY - start.py), globalThis.innerHeight - 48)),
      });
    const stop = () => {
      globalThis.removeEventListener("pointermove", move);
      globalThis.removeEventListener("pointerup", stop);
    };
    globalThis.addEventListener("pointermove", move);
    globalThis.addEventListener("pointerup", stop);
  }

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const asked = question.trim();
    if (!asked || busy) return;

    setQuestion("");
    setTurns((t) => [...t, { question: asked, reply: null }]);
    setBusy(true);
    // A new question is the reader asking to see the answer: follow it.
    toEnd(true);

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
        toEnd();
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not reach CEREBRO.";
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: message } : turn)));
    } finally {
      setBusy(false);
      toEnd();
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full border border-scene-ink/15 bg-scene-raised/95 px-4 py-2.5 text-sm font-medium text-scene-ink shadow-xl backdrop-blur transition-colors hover:bg-scene-hover"
      >
        <Spark />
        Ask CEREBRO
      </button>
    );
  }

  return (
    <section
      data-testid="recall-chat"
      style={
        win.x < 0
          ? { right: 20, bottom: 20, width: WIDTH, height: HEIGHT }
          : { left: win.x, top: win.y, width: WIDTH, height: HEIGHT }
      }
      className="fixed z-40 flex max-h-[calc(100dvh-2rem)] max-w-[calc(100vw-2rem)] flex-col rounded-xl border border-scene-ink/15 bg-scene-overlay/97 shadow-2xl backdrop-blur"
    >
      <header
        onPointerDown={startDrag}
        title="Drag to move"
        className="flex cursor-move items-center justify-between gap-2 border-b border-scene-ink/10 px-3 py-2.5"
      >
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

      <div ref={log} onScroll={onScroll} className="flex-1 space-y-3 overflow-y-auto p-3">
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
              <Reply reply={turn.reply} onShowMe={onShowMe} onTimeline={onTimeline} />
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
  onTimeline,
}: {
  reply: CerebroRecallAnswer;
  onShowMe?: (reply: CerebroRecallAnswer) => void;
  onTimeline?: (reply: CerebroRecallAnswer) => void;
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
      {/* The evidence, on the screens that show it best: the map for how it
          connects, the timeline for when. */}
      {reply.sources.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {onShowMe && (
            <button
              type="button"
              data-testid="show-me"
              onClick={() => onShowMe(reply)}
              className="rounded-md border border-sky-400/40 px-2 py-1 text-[0.6875rem] font-medium text-sky-300 transition-colors hover:bg-sky-400/10"
            >
              Show me on the map
            </button>
          )}
          {onTimeline && (
            <button
              type="button"
              data-testid="see-timeline"
              onClick={() => onTimeline(reply)}
              className="rounded-md border border-scene-ink/20 px-2 py-1 text-[0.6875rem] font-medium text-scene-ink/80 transition-colors hover:bg-scene-ink/10"
            >
              See on the timeline
            </button>
          )}
        </div>
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
