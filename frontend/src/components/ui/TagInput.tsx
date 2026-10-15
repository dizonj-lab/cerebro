"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";

interface TagInputProps {
  id: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  max?: number;
  disabled?: boolean;
}

/** Chip editor for multi-value fields. Enter or comma commits; Backspace removes. */
export function TagInput({
  id,
  value,
  onChange,
  placeholder = "Add and press Enter",
  max = 20,
  disabled,
}: TagInputProps) {
  const [draft, setDraft] = useState("");

  function commit(raw: string) {
    const tag = raw.trim().replace(/\s+/g, " ");
    if (!tag || value.length >= max) return;
    // Case-insensitive de-duplication, matching the server's normalisation.
    if (value.some((t) => t.toLowerCase() === tag.toLowerCase())) return;
    onChange([...value, tag.slice(0, 60)]);
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5 rounded-md border border-line-strong bg-surface p-1.5",
        disabled && "bg-surface-subtle",
      )}
    >
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-sm bg-accent-subtle py-1 pl-2 pr-1 text-xs font-medium text-accent"
        >
          {tag}
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange(value.filter((t) => t !== tag))}
            aria-label={`Remove ${tag}`}
            className="rounded-sm p-0.5 hover:bg-accent/15"
          >
            <svg viewBox="0 0 12 12" className="size-3" aria-hidden="true">
              <path
                d="M3 3l6 6M9 3l-6 6"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </span>
      ))}

      <input
        id={id}
        value={draft}
        disabled={disabled || value.length >= max}
        placeholder={value.length >= max ? `Limit of ${max} reached` : placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit(draft);
            setDraft("");
          } else if (e.key === "Backspace" && !draft && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => {
          if (draft.trim()) {
            commit(draft);
            setDraft("");
          }
        }}
        className="min-w-[10rem] flex-1 bg-transparent px-1.5 py-1 text-sm text-ink outline-none placeholder:text-ink-subtle"
      />
    </div>
  );
}
