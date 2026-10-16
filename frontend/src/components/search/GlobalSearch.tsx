"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

const HISTORY_KEY = "cerebro.search.history";
const HISTORY_LIMIT = 6;
const DEBOUNCE_MS = 300;

function readHistory(): string[] {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((v) => typeof v === "string") : [];
  } catch {
    // Storage can be unavailable or hold something else. No history is a
    // fine state; a thrown error in the header is not.
    return [];
  }
}

function remember(query: string): string[] {
  const next = [query, ...readHistory().filter((q) => q !== query)].slice(0, HISTORY_LIMIT);
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  } catch {
    // Ignored: the search still runs without a stored history.
  }
  return next;
}

/**
 * The global search box in the header.
 *
 * Typing suggests; it never searches. Suggestions are completions of the
 * user's own confirmed metadata, debounced so a word typed quickly costs one
 * request rather than one per keystroke. Submitting navigates to the search
 * page, which owns the retrieval.
 *
 * History is per-browser (localStorage) rather than server-side: a saved
 * search would be a new stored object, and these are queries the user typed
 * here, on this machine.
 */
export function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  // Cmd/Ctrl+K focuses the box from anywhere in the Construct.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        input.current?.focus();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const prefix = query.trim();
    let live = true;
    // Debounced, and the clearing happens in the timer too: a keystroke
    // must not set state synchronously from an effect body.
    const timer = window.setTimeout(() => {
      if (prefix.length < 2) {
        setSuggestions([]);
        return;
      }
      void (async () => {
        try {
          const body = await api.searchSuggestions(prefix);
          if (live) setSuggestions(body.suggestions);
        } catch {
          if (live) setSuggestions([]);
        }
      })();
    }, DEBOUNCE_MS);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  function go(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setHistory(remember(trimmed));
    setOpen(false);
    input.current?.blur();
    router.push(`/construct/search?q=${encodeURIComponent(trimmed)}`);
  }

  const panel = open && (suggestions.length > 0 || (query.trim() === "" && history.length > 0));

  return (
    <div className="relative mx-auto hidden w-full max-w-md md:block">
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          go(query);
        }}
        className="flex items-center gap-2 rounded-lg border border-line bg-surface-subtle px-3 py-2 text-sm focus-within:border-accent"
      >
        <svg viewBox="0 0 20 20" className="size-4 shrink-0 text-ink-subtle" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <circle cx="8.75" cy="8.75" r="5" />
          <path d="m12.5 12.5 4 4" strokeLinecap="round" />
        </svg>
        <input
          ref={input}
          type="search"
          name="q"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => {
            // Read on focus rather than on mount: localStorage is an
            // external store, and reading it in an effect would set state
            // during the first render of every Construct page.
            setHistory(readHistory());
            setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
              input.current?.blur();
            }
          }}
          role="combobox"
          aria-expanded={Boolean(panel)}
          aria-controls="global-search-suggestions"
          aria-autocomplete="list"
          aria-label="Search your knowledge"
          placeholder="Search your knowledge..."
          className="w-full bg-transparent text-ink outline-none placeholder:text-ink-subtle"
        />
        <kbd className="hidden shrink-0 rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-subtle lg:block">
          ⌘K
        </kbd>
      </form>

      {panel && (
        <ul
          id="global-search-suggestions"
          role="listbox"
          data-testid="search-suggestions"
          className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-subtle"
        >
          {(suggestions.length > 0 ? suggestions : history).map((value) => (
            <li key={value} role="option" aria-selected="false">
              <button
                type="button"
                // Mouse down rather than click: the input blurs first
                // otherwise, and the panel is gone before the click lands.
                onMouseDown={(event) => {
                  event.preventDefault();
                  setQuery(value);
                  go(value);
                }}
                className={cn(
                  "block w-full px-3 py-1.5 text-left text-sm text-ink-muted",
                  "transition-colors hover:bg-surface-subtle hover:text-ink",
                )}
              >
                {value}
              </button>
            </li>
          ))}
          {suggestions.length === 0 && (
            <li className="px-3 py-1 text-xs text-ink-subtle">Recent searches</li>
          )}
        </ul>
      )}
    </div>
  );
}
