"use client";

import type { CerebroSearchFilters, SearchScope } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * The filter rail.
 *
 * Every control here maps to metadata that actually exists on an artifact.
 * There is no confidence slider and no collection picker: CEREBRO stores
 * neither, and a control that silently matches everything (or nothing) is
 * worse than its absence. Topic options come from the user's own confirmed
 * topics; tags are typed, because an option list of tags the user never
 * applied would be invented.
 */
export interface FilterRailProps {
  filters: CerebroSearchFilters;
  onChange: (next: CerebroSearchFilters) => void;
  scope: SearchScope;
  onScopeChange: (scope: SearchScope) => void;
  topicOptions: string[];
  modalityOptions: string[];
  onClear: () => void;
  activeCount: number;
}

const SCOPES: { value: SearchScope; label: string }[] = [
  { value: "all", label: "Everything" },
  { value: "library", label: "Documents" },
  { value: "knowledge", label: "Knowledge" },
];

const STATUSES: { value: string; label: string }[] = [
  { value: "registered", label: "Registered" },
  { value: "approved", label: "Approved" },
  { value: "inspected", label: "Awaiting review" },
  { value: "rejected", label: "Rejected" },
];

export function FilterRail({
  filters,
  onChange,
  scope,
  onScopeChange,
  topicOptions,
  modalityOptions,
  onClear,
  activeCount,
}: FilterRailProps) {
  function toggle(key: "modalities" | "statuses" | "topics", value: string) {
    const current = filters[key] ?? [];
    onChange({
      ...filters,
      [key]: current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value],
    });
  }

  return (
    <aside
      aria-label="Search filters"
      data-testid="filter-rail"
      className="flex w-full flex-col gap-6 text-sm"
    >
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-ink">Filters</h2>
        {activeCount > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="rounded-md px-2 py-1 text-xs font-medium text-accent transition-colors hover:bg-surface-subtle"
          >
            Clear ({activeCount})
          </button>
        )}
      </div>

      <Group label="Search in">
        <div role="group" className="flex flex-col gap-1">
          {SCOPES.map((option) => (
            <label key={option.value} className="flex items-center gap-2 text-ink-muted">
              <input
                type="radio"
                name="scope"
                value={option.value}
                checked={scope === option.value}
                onChange={() => onScopeChange(option.value)}
                className="accent-accent"
              />
              {option.label}
            </label>
          ))}
        </div>
      </Group>

      {modalityOptions.length > 0 && (
        <Group label="Document type">
          {modalityOptions.map((modality) => (
            <Check
              key={modality}
              label={modality}
              checked={(filters.modalities ?? []).includes(modality)}
              onChange={() => toggle("modalities", modality)}
            />
          ))}
        </Group>
      )}

      <Group label="Ingestion status">
        {/*
          Status is a filter, not a way to promote a draft: an unregistered
          artifact is findable as a document and never as knowledge, whichever
          boxes are ticked here.
        */}
        {STATUSES.map((status) => (
          <Check
            key={status.value}
            label={status.label}
            checked={(filters.statuses ?? []).includes(status.value)}
            onChange={() => toggle("statuses", status.value)}
          />
        ))}
        <p className="pt-1 text-xs text-ink-subtle">
          Only registered documents contribute knowledge.
        </p>
      </Group>

      {topicOptions.length > 0 && (
        <Group label="Topic">
          <div className="max-h-48 overflow-y-auto pr-1">
            {topicOptions.map((topic) => (
              <Check
                key={topic}
                label={topic}
                checked={(filters.topics ?? []).includes(topic)}
                onChange={() => toggle("topics", topic)}
              />
            ))}
          </div>
          <p className="pt-1 text-xs text-ink-subtle">Topics a human confirmed.</p>
        </Group>
      )}

      <Group label="Tag">
        <input
          type="text"
          aria-label="Filter by tag"
          placeholder="Type a tag"
          value={(filters.tags ?? []).join(", ")}
          onChange={(e) =>
            onChange({
              ...filters,
              tags: e.target.value
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean),
            })
          }
          className="w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-ink outline-none placeholder:text-ink-subtle focus:border-accent"
        />
      </Group>

      <Group label="Uploaded">
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            From
            <input
              type="date"
              aria-label="Uploaded from"
              value={filters.uploaded_from ?? ""}
              onChange={(e) => onChange({ ...filters, uploaded_from: e.target.value || null })}
              className="flex-1 rounded-md border border-line bg-surface px-2 py-1 text-ink outline-none focus:border-accent"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            To
            <input
              type="date"
              aria-label="Uploaded to"
              value={filters.uploaded_to ?? ""}
              onChange={(e) => onChange({ ...filters, uploaded_to: e.target.value || null })}
              className="flex-1 rounded-md border border-line bg-surface px-2 py-1 text-ink outline-none focus:border-accent"
            />
          </label>
        </div>
      </Group>
    </aside>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">{label}</h3>
      {children}
    </section>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className={cn("flex items-center gap-2 py-0.5", checked ? "text-ink" : "text-ink-muted")}>
      <input type="checkbox" checked={checked} onChange={onChange} className="accent-accent" />
      <span className="capitalize">{label}</span>
    </label>
  );
}
