/**
 * What the page the user is on can offer Ask CEREBRO.
 *
 * The chat lives in the shell, on every page, so it cannot take props from
 * the Galaxy. A page publishes its context here instead — the topic in focus,
 * and a way to light up the map — and withdraws it when it unmounts. In
 * memory only: nothing about a conversation is stored.
 *
 * An answer mapped from another page is handed to the Galaxy through
 * sessionStorage, read once when the Galaxy opens, then removed.
 */
import { useSyncExternalStore } from "react";

import type { CerebroRecallAnswer, CerebroRecallSource } from "@/lib/api";

export interface RecallContext {
  /** The topic the question is asked in the context of, if any. */
  topic: string | null;
  /** Present on the Galaxy: lights up the part of the map an answer came from. */
  showMe?: (reply: CerebroRecallAnswer) => void;
  /** Present on the Galaxy: opens one document's topic and lights its passage. */
  showSource?: (source: CerebroRecallSource) => void;
}

/**
 * One document found by the chat, as an answer of its own: mapping it lights
 * that document's passage and topic, and `document` tells the Galaxy to open
 * the topic so the passage is on the map, and to offer the file itself.
 */
export function documentAnswer(source: CerebroRecallSource): CerebroRecallAnswer & {
  document: { artifact_id: string; title: string; topic: string | null };
} {
  const title = source.title || source.filename;
  return {
    answer: title,
    sources: [source],
    cited: [source.index],
    grounded: true,
    model: null,
    note: null,
    document: { artifact_id: source.artifact_id, title, topic: source.topics?.[0] ?? null },
  };
}

const EMPTY: RecallContext = { topic: null };
let current: RecallContext = EMPTY;
const listeners = new Set<() => void>();

export function setRecallContext(next: RecallContext | null) {
  current = next ?? EMPTY;
  for (const listener of listeners) listener();
}

export function useRecallContext(): RecallContext {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
    () => EMPTY,
  );
}

const PENDING_MAP = "cerebro-pending-map";

/** Keep an answer for the Galaxy to map when it opens. */
export function queueMap(reply: CerebroRecallAnswer) {
  try {
    window.sessionStorage.setItem(PENDING_MAP, JSON.stringify(reply));
  } catch {
    // Without storage the Galaxy simply opens unmapped.
  }
}

/** The answer waiting to be mapped, taken once. */
export function takeQueuedMap(): CerebroRecallAnswer | null {
  try {
    const raw = window.sessionStorage.getItem(PENDING_MAP);
    window.sessionStorage.removeItem(PENDING_MAP);
    return raw ? (JSON.parse(raw) as CerebroRecallAnswer) : null;
  } catch {
    return null;
  }
}
