/**
 * Sticky notes: documents Ask CEREBRO found, marked where they sit.
 *
 * "Show in Galaxy" or "Show in Timeline" on a result puts a note — the
 * document's title, in that result's colour — on the place in the Galaxy or
 * the Timeline where the document is. A note stays until its × is pressed or
 * the browser session ends, across pages, so the reader can move between the
 * two views and still see what they were following. Session storage only:
 * nothing is kept once the session is over.
 */
import { useCallback } from "react";

import type { CerebroRecallSource } from "@/lib/api";
import { createPersistedStore } from "@/lib/persistedStore";

export const NOTE_COLOURS = 5;

export interface StickyNote {
  /** The document's artifact id; one note per document. */
  id: string;
  title: string;
  /** 1–5, matching the result's colour in the chat. */
  colour: number;
  /** The passage found, so the Galaxy can point at it when its topic is open. */
  fragmentId: string | null;
  /** The document's first confirmed topic, which the Galaxy points at otherwise. */
  topic: string | null;
}

const useStore = createPersistedStore("cerebro-sticky-notes", { notes: [] as StickyNote[] }, "session");

/** A result's colour: by its place in the answer, so [1] is always the first colour. */
export function colourFor(index: number): number {
  return ((Math.max(1, index) - 1) % NOTE_COLOURS) + 1;
}

// Written out in full: Tailwind emits only the theme variables it finds
// named in the source, and a name assembled from a template is not found.
const NOTE_VARS = ["var(--note-1)", "var(--note-2)", "var(--note-3)", "var(--note-4)", "var(--note-5)"];

export function noteColour(colour: number): string {
  return NOTE_VARS[(Math.max(1, colour) - 1) % NOTE_VARS.length];
}

export function noteFor(source: CerebroRecallSource): StickyNote {
  return {
    id: source.artifact_id,
    title: source.title || source.filename,
    colour: colourFor(source.index),
    fragmentId: source.fragment_id,
    topic: source.topics?.[0] ?? null,
  };
}

export function useStickyNotes(): {
  notes: StickyNote[];
  add: (notes: StickyNote[]) => void;
  remove: (id: string) => void;
} {
  const [state, set] = useStore();
  const add = useCallback(
    (incoming: StickyNote[]) => {
      // One note per document, even when several of its passages were found:
      // the first (best-ranked) passage names it. The latest showing wins, so
      // its colour follows the answer it came from.
      const unique = incoming.filter((n, i) => incoming.findIndex((m) => m.id === n.id) === i);
      const ids = new Set(unique.map((n) => n.id));
      set({ notes: [...state.notes.filter((n) => !ids.has(n.id)), ...unique] });
    },
    [state.notes, set],
  );
  const remove = useCallback((id: string) => set({ notes: state.notes.filter((n) => n.id !== id) }), [state.notes, set]);
  return { notes: state.notes, add, remove };
}
