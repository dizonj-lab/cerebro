"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import type { CerebroAnchor, CerebroCv } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * The CV, and the chronology CEREBRO reads from it.
 *
 * The CV is the one document that says what a person *did*, in order. Every
 * other artifact says what they wrote or read. That makes it the natural
 * backbone for a timeline — and the most sensitive thing in the library, so
 * the disclosure below is shown before the file picker rather than after.
 *
 * Nothing read here is a fact until the user says so. Entries arrive as
 * suggestions beside the CV's own line, and the timeline is personalised
 * only once they are approved. The rest of CEREBRO stays usable throughout:
 * an incomplete setup is a state, not a lock.
 */
const TYPES = [
  "employment",
  "education",
  "project",
  "certification",
  "professional_development",
  "personal_milestone",
  "other",
] as const;

export function CvPanel() {
  const [cv, setCv] = useState<CerebroCv | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api.cv().then(setCv).catch(() => setCv(null));
  }, []);
  useEffect(load, [load]);

  async function send(file: File) {
    setBusy(true);
    setError(null);
    try {
      setCv(await api.uploadCv(file));
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "The CV could not be read.");
    } finally {
      setBusy(false);
    }
  }

  async function correct(id: string, changes: Partial<CerebroAnchor>) {
    const updated = await api.correctAnchor(id, changes);
    setCv((current) =>
      current
        ? { ...current, anchors: current.anchors.map((a) => (a.id === id ? updated : a)) }
        : current,
    );
  }

  async function approve() {
    setBusy(true);
    try {
      setCv(await api.approveAnchors());
    } finally {
      setBusy(false);
    }
  }

  const status = cv?.status ?? "none";
  const anchors = cv?.anchors ?? [];
  const pending = anchors.filter((a) => a.approval_status === "suggested");

  return (
    <section className="flex flex-col gap-4" data-testid="cv-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-subtle">
          My CV / Resume
        </h2>
        <StatusChip status={status} />
      </div>

      {/* Said before the picker, not after: this is the most personal file
          CEREBRO will hold, and the moment to decide is before uploading. */}
      <p className="text-[0.8125rem] leading-relaxed text-ink-muted">
        Your CV becomes the backbone of your timeline — the periods your knowledge sits
        inside. It is stored in your CEREBRO environment like any other document, is
        visible only to you, and is read by the same local pipeline. A local model is
        asked only if you have AI suggestions switched on in Settings. Nothing CEREBRO
        reads from it is treated as fact until you approve it, and you can replace or
        remove it at any time.
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void send(file);
        }}
        className={cn(
          "rounded-xl border border-dashed p-5 text-center transition-colors",
          dragging ? "border-accent bg-accent/5" : "border-border",
        )}
      >
        <input
          ref={picker}
          type="file"
          accept=".pdf,.docx"
          className="sr-only"
          aria-label="Choose a CV file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void send(file);
            e.target.value = "";
          }}
        />
        {cv?.filename ? (
          <p className="text-sm text-ink">
            <span className="font-medium">{cv.filename}</span>
            {cv.uploaded_at && (
              <span className="text-ink-muted">
                {" "}
                · uploaded {new Date(cv.uploaded_at).toLocaleDateString()}
              </span>
            )}
          </p>
        ) : (
          <p className="text-sm text-ink-muted">Drop a PDF or Word CV here, up to 10 MB.</p>
        )}
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          <Button type="button" variant="secondary" disabled={busy}
            onClick={() => picker.current?.click()}>
            {cv?.filename ? "Replace CV" : "Choose a file"}
          </Button>
          {cv?.artifact_id && (
            <a
              href={api.artifactContentUrl(cv.artifact_id)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center rounded-lg border border-border px-3 py-1.5 text-sm text-ink-muted hover:text-ink"
            >
              Preview
            </a>
          )}
        </div>
        {busy && <p className="mt-2 text-xs text-ink-muted">Reading your CV…</p>}
        {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      </div>

      {anchors.length > 0 && (
        <div className="flex flex-col gap-2" data-testid="cv-anchors">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[0.8125rem] text-ink-muted">
              {pending.length > 0
                ? `${pending.length} entr${pending.length === 1 ? "y" : "ies"} read from your CV. Check each one before it becomes part of your timeline.`
                : "Your timeline is personalised from these entries."}
            </p>
            {pending.length > 0 && (
              <Button type="button" onClick={approve} disabled={busy} data-testid="approve-anchors">
                Approve {pending.length}
              </Button>
            )}
          </div>

          <ul className="flex flex-col gap-2">
            {anchors.map((anchor) => (
              <AnchorRow key={anchor.id} anchor={anchor} onChange={correct} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function AnchorRow({
  anchor,
  onChange,
}: {
  anchor: CerebroAnchor;
  onChange: (id: string, changes: Partial<CerebroAnchor>) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const rejected = anchor.approval_status === "rejected";

  return (
    <li
      data-testid="cv-anchor"
      className={cn(
        "rounded-lg border border-border p-3",
        rejected && "opacity-50",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{anchor.title}</p>
          <p className="text-xs text-ink-muted">
            {describeRange(anchor)}
            {anchor.organization ? ` · ${anchor.organization}` : ""}
            {" · "}
            {anchor.event_type.replace(/_/g, " ")}
          </p>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <button type="button" onClick={() => setOpen((v) => !v)}
            className="rounded-md border border-border px-2 py-1 text-xs text-ink-muted hover:text-ink">
            {open ? "Done" : "Edit"}
          </button>
          <button
            type="button"
            onClick={() => onChange(anchor.id, { approval_status: rejected ? "suggested" : "rejected" })}
            className="rounded-md border border-border px-2 py-1 text-xs text-ink-muted hover:text-ink"
          >
            {rejected ? "Restore" : "Remove"}
          </button>
        </div>
      </div>

      {/* The CV's own line. Shown rather than summarised: it is the only way
          to check a reading without opening the document. */}
      {anchor.evidence_text && (
        <p className="mt-1.5 truncate text-[0.6875rem] italic text-ink-subtle">
          “{anchor.evidence_text}”
        </p>
      )}
      {anchor.user_edited && anchor.extracted?.title && anchor.extracted.title !== anchor.title && (
        <p className="mt-1 text-[0.6875rem] text-ink-subtle">
          Your CV said “{anchor.extracted.title}”.
        </p>
      )}

      {open && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Field label="Title" value={anchor.title}
            onCommit={(v) => onChange(anchor.id, { title: v })} />
          <Field label="Organization" value={anchor.organization ?? ""}
            onCommit={(v) => onChange(anchor.id, { organization: v || null })} />
          <Field label="Start (YYYY-MM-DD)" value={anchor.start_date ?? ""}
            onCommit={(v) => onChange(anchor.id, { start_date: v || null })} />
          <Field label="End (YYYY-MM-DD)" value={anchor.end_date ?? ""}
            hint="Leave empty if it has not ended, or the CV did not say."
            onCommit={(v) => onChange(anchor.id, { end_date: v || null })} />
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            Type
            <select
              value={anchor.event_type}
              onChange={(e) => onChange(anchor.id, { event_type: e.target.value })}
              className="rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-ink"
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
        </div>
      )}
    </li>
  );
}

function Field({
  label,
  value,
  hint,
  onCommit,
}: {
  label: string;
  value: string;
  hint?: string;
  onCommit: (value: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-muted">
      {label}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => draft !== value && onCommit(draft)}
        className="rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-ink"
      />
      {hint && <span className="text-[0.6875rem] text-ink-subtle">{hint}</span>}
    </label>
  );
}

/**
 * A date range at the precision the CV gave, and no more.
 *
 * A year-only range reads as years. An absent end reads as "present" when
 * there is a start, because the CV not stating an end is what "still there"
 * looks like on paper — but the stored value remains null, so nothing
 * downstream treats today as a date the document asserted.
 */
export function describeRange(anchor: {
  start_date: string | null;
  end_date: string | null;
  date_precision: string;
}): string {
  const show = (iso: string | null) => {
    if (!iso) return null;
    const date = new Date(`${iso}T00:00:00`);
    if (anchor.date_precision === "year") return String(date.getUTCFullYear());
    if (anchor.date_precision === "month") {
      return date.toLocaleDateString(undefined, { month: "short", year: "numeric" });
    }
    return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  };
  const from = show(anchor.start_date);
  const to = show(anchor.end_date);
  if (!from && !to) return "Date not stated";
  if (from && !to) return `${from} – present`;
  if (!from && to) return `until ${to}`;
  return `${from} – ${to}`;
}

function StatusChip({ status }: { status: string }) {
  const text =
    status === "approved"
      ? "Timeline personalised"
      : status === "needs_review"
        ? "Needs review"
        : "Setup incomplete";
  return (
    <span
      data-testid="cv-status"
      className={cn(
        "rounded-full px-2.5 py-0.5 text-[0.6875rem] font-medium",
        status === "approved"
          ? "bg-accent/15 text-accent"
          : "bg-surface-subtle text-ink-muted",
      )}
    >
      {text}
    </span>
  );
}
