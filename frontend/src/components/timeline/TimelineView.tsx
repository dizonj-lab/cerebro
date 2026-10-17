"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { EventPanel } from "@/components/timeline/EventPanel";
import { Navigator } from "@/components/timeline/Navigator";
import { describeRange } from "@/app/construct/profile/CvPanel";
import { colorForLane, formatEventDate, fractionOf } from "@/components/timeline/lanes";
import { api, ApiError } from "@/lib/api";
import type { CerebroAnchor, CerebroTimeline, CerebroTimelineEventDetail } from "@/lib/api";
import { cn } from "@/lib/cn";

const YEAR = 365.25 * 24 * 60 * 60 * 1000;
const MIN_SPAN = YEAR / 4;
const MAX_SPAN = YEAR * 60;
/** Cards narrower than this collide, so they are packed onto another row. */
const CARD_WIDTH_PX = 170;
// A card is three lines now — document, date, statement — so rows sit
// further apart than they did at two.
const ROW_HEIGHT_PX = 58;

interface Window {
  from: number;
  to: number;
}

interface Placed {
  event: CerebroTimelineEventDetail;
  left: number;
  row: number;
}

/**
 * The Knowledge Timeline.
 *
 * Events are the dated statements in the user's registered documents, placed
 * at the date the text gives. The window is a pair of timestamps rather than
 * a scroll position: zoom, pan, fit and the navigator all move the same two
 * numbers, and only events inside them are rendered — so a library of
 * thousands costs what is on screen.
 */
export function TimelineView() {
  const [data, setData] = useState<CerebroTimeline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<CerebroTimelineEventDetail | null>(null);
  const [hovered, setHovered] = useState<CerebroTimelineEventDetail | null>(null);
  const [selectedAnchor, setSelectedAnchor] = useState<CerebroAnchor | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [window_, setWindow] = useState<Window | null>(null);

  // Arriving from the Galaxy with ?focus=Atlas opens on that lane, so the
  // subject survives the switch between the two views.
  const params = useSearchParams();
  const [categories, setCategories] = useState<string[]>(() => {
    const focus = params.get("focus");
    return focus ? [focus] : [];
  });
  const [source, setSource] = useState<string>("");
  const [entityType, setEntityType] = useState<string>("");
  const [entity, setEntity] = useState<string>("");
  const [start, setStart] = useState<string>("");
  const [end, setEnd] = useState<string>("");

  const canvas = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; top: number; window: Window } | null>(null);

  // Written as a promise chain rather than an awaited call so that nothing
  // sets state synchronously inside the effect below: that would re-render
  // every page in the shell before this one had its data.
  const load = useCallback(() => {
    api
      .timeline({
        categories,
        sources: source ? [source] : [],
        entity_type: entityType || undefined,
        entity: entity || undefined,
        start: start || undefined,
        end: end || undefined,
      })
      .then((body) => {
        setData(body);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : "Could not load the timeline.");
      })
      .finally(() => setLoading(false));
  }, [categories, source, entityType, entity, start, end]);

  useEffect(load, [load]);

  // The first load decides the window; later ones leave it alone, so
  // filtering does not throw away where the user had navigated to.
  const fitted = useRef(false);
  useEffect(() => {
    if (!data || fitted.current) return;
    fitted.current = true;
    setWindow(fitAll(data));
  }, [data]);

  function fitAll(body: CerebroTimeline): Window | null {
    if (!body.range.earliest || !body.range.latest) return null;
    const from = new Date(`${body.range.earliest}T00:00:00`).getTime();
    const to = new Date(`${body.range.latest}T00:00:00`).getTime();
    const pad = Math.max((to - from) * 0.08, YEAR / 6);
    return { from: from - pad, to: to + pad };
  }

  function zoom(factor: number) {
    setWindow((current) => {
      if (!current) return current;
      const span = current.to - current.from;
      const next = Math.min(MAX_SPAN, Math.max(MIN_SPAN, span * factor));
      const middle = (current.from + current.to) / 2;
      return { from: middle - next / 2, to: middle + next / 2 };
    });
  }

  function beginPan(event: React.PointerEvent) {
    if (!window_) return;
    // Anywhere on the canvas drags it, lane backgrounds included. It used to
    // require the press to land on the canvas element itself, so a drag
    // started over a lane — which is most of the surface — did nothing at
    // all, and the timeline felt fixed. Cards stop the event themselves, so
    // a press on one is still that card's.
    if ((event.target as Element).closest?.("button")) return;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      top: canvas.current?.scrollTop ?? 0,
      window: window_,
    };
    const move = (e: PointerEvent) => {
      const state = drag.current;
      const width = canvas.current?.clientWidth ?? 1;
      if (!state) return;
      const span = state.window.to - state.window.from;
      const shift = ((e.clientX - state.x) / width) * span;
      setWindow({ from: state.window.from - shift, to: state.window.to - shift });
      // Vertically it is a scroll, not a change of window: the lanes are a
      // list, and dragging up should reach the lane below rather than move
      // time.
      if (canvas.current) canvas.current.scrollTop = state.top - (e.clientY - state.y);
    };
    const end_ = () => {
      drag.current = null;
      globalThis.removeEventListener("pointermove", move);
      globalThis.removeEventListener("pointerup", end_);
    };
    globalThis.addEventListener("pointermove", move);
    globalThis.addEventListener("pointerup", end_);
  }

  function onWheel(event: React.WheelEvent) {
    if (!window_) return;
    // Trackpads send horizontal deltas for a two-finger swipe, which is a
    // pan; the vertical axis, with a modifier or not, zooms.
    if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      const span = window_.to - window_.from;
      const shift = (event.deltaX / (canvas.current?.clientWidth ?? 1)) * span;
      setWindow({ from: window_.from + shift, to: window_.to + shift });
    } else {
      zoom(event.deltaY > 0 ? 1.12 : 0.89);
    }
  }

  // The lanes the API decided on: the owner's own confirmed topics, or the
  // six named ones when the library has none. The page follows the data
  // rather than imposing a taxonomy of its own.
  const lanes = useMemo(
    () =>
      (data?.lanes ?? []).map((lane, index) => ({
        name: lane.name,
        count: lane.count,
        color: colorForLane(lane.name, index),
      })),
    [data],
  );

  // One source of colour for the lanes and for the navigator's bars, so a
  // category reads the same in both.
  const laneColor = useCallback(
    (category: string) => lanes.find((lane) => lane.name === category)?.color ?? "#64748b",
    [lanes],
  );

  /**
   * Anchor periods, packed onto rows so none hides another.
   *
   * Careers overlap — a role begins before a course ends — and a single row
   * drew the later band on top of the earlier one, which did not just look
   * wrong: the covered band stopped being clickable. Rows are assigned
   * greedily in start order, the same way the event cards are packed.
   */
  const placedAnchors = useMemo(() => {
    if (!data?.anchors?.length || !window_) return [];
    const ends: number[] = [];
    const placed: { anchor: CerebroAnchor; left: number; width: number; row: number }[] = [];

    for (const anchor of data.anchors) {
      if (!anchor.start_date) continue;
      const from = fractionOf(anchor.start_date, window_.from, window_.to) * 100;
      // No end date means it has not ended, so the band runs to the edge of
      // the window rather than to a date nobody stated.
      const to = anchor.end_date
        ? fractionOf(anchor.end_date, window_.from, window_.to) * 100
        : 100;
      if (to < 0 || from > 100) continue;
      const left = Math.max(0, from);
      const width = Math.max(1.5, Math.min(100, to) - left);
      let row = ends.findIndex((end) => end <= left);
      if (row === -1) {
        row = ends.length;
        ends.push(0);
      }
      ends[row] = left + width;
      placed.push({ anchor, left, width, row });
    }
    return placed;
  }, [data, window_]);

  const anchorRows = Math.max(1, ...placedAnchors.map((p) => p.row + 1));

  const visible = useMemo(() => {
    if (!data || !window_) return new Map<string, Placed[]>();
    const byLane = new Map<string, Placed[]>();
    const width = canvas.current?.clientWidth ?? 1000;
    const minimumGap = (CARD_WIDTH_PX / width) * 100;

    for (const lane of lanes) {
      const inLane = data.events
        .filter((event) => event.category === lane.name)
        .map((event) => ({
          event,
          left: fractionOf(event.date, window_.from, window_.to) * 100,
          row: 0,
        }))
        // Only what is on screen is rendered, with a margin so a card
        // entering from the side is not drawn mid-animation.
        .filter((placed) => placed.left > -12 && placed.left < 112)
        .sort((a, b) => a.left - b.left);

      // Greedy packing: a card that would overlap the last one on its row
      // drops to the next. Nothing is hidden and nothing overlaps.
      const rowEnds: number[] = [];
      for (const placed of inLane) {
        let row = rowEnds.findIndex((end_) => placed.left >= end_);
        if (row === -1) {
          row = rowEnds.length;
          rowEnds.push(0);
        }
        rowEnds[row] = placed.left + minimumGap;
        placed.row = row;
      }
      byLane.set(lane.name, inLane);
    }
    return byLane;
  }, [data, window_, lanes]);

  const ticks = useMemo(() => {
    if (!window_) return [] as { at: number; label: string; major: boolean }[];
    const span = window_.to - window_.from;
    const out: { at: number; label: string; major: boolean }[] = [];
    const first = new Date(window_.from);
    // Adaptive: years when the span is wide, quarters in the middle, months
    // when it is narrow enough for them to be readable.
    const step = span > YEAR * 12 ? "year" : span > YEAR * 2 ? "quarter" : "month";
    const cursor = new Date(Date.UTC(first.getUTCFullYear(), 0, 1));
    while (cursor.getTime() < window_.to + YEAR) {
      const at = ((cursor.getTime() - window_.from) / span) * 100;
      const month = cursor.getUTCMonth();
      if (at > -5 && at < 105) {
        if (step === "year" && month === 0) {
          out.push({ at, label: String(cursor.getUTCFullYear()), major: true });
        } else if (step === "quarter" && month % 3 === 0) {
          out.push({
            at,
            label: month === 0 ? String(cursor.getUTCFullYear()) : `Q${month / 3 + 1}`,
            major: month === 0,
          });
        } else if (step === "month") {
          out.push({
            at,
            label:
              month === 0
                ? String(cursor.getUTCFullYear())
                : cursor.toLocaleDateString(undefined, { month: "short" }),
            major: month === 0,
          });
        }
      }
      cursor.setUTCMonth(month + (step === "month" ? 1 : step === "quarter" ? 3 : 12));
    }
    return out;
  }, [window_]);

  const zoomPercent = window_ && data ? Math.round((YEAR * 6) / (window_.to - window_.from) * 100) : 100;
  const related = selected
    ? new Set(
        (data?.events ?? [])
          .filter(
            (event) =>
              event.artifact_id === selected.artifact_id ||
              Object.entries(event.entities).some(([field, values]) =>
                (selected.entities[field] ?? []).some((value) => values.includes(value)),
              ),
          )
          .map((event) => event.id),
      )
    : null;

  function reset() {
    setCategories([]);
    setSource("");
    setEntityType("");
    setEntity("");
    setStart("");
    setEnd("");
    if (data) setWindow(fitAll(data));
  }

  return (
    <div className="flex h-[calc(100dvh-7.5rem)] min-h-0 flex-col gap-2 text-white">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Timeline</h1>
          <p className="text-sm text-white/55">Explore the evolution of your knowledge over time</p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 p-0.5 text-xs">
          <span className="rounded-md bg-sky-500 px-3 py-1.5 font-medium text-[#07121f]">Timeline</span>
          <Link href="/construct/galaxy" className="rounded-md px-3 py-1.5 text-white/65 hover:text-white">
            Galaxy
          </Link>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select
          aria-label="Category"
          value={categories[0] ?? ""}
          onChange={(e) => setCategories(e.target.value ? [e.target.value] : [])}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white outline-none"
        >
          <option value="">All Categories</option>
          {lanes.map((lane) => (
            <option key={lane.name} value={lane.name}>{lane.name}</option>
          ))}
        </select>

        <select
          aria-label="Source"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="max-w-[12rem] rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white outline-none"
        >
          <option value="">All Sources</option>
          {(data?.sources ?? []).map(([id, filename]) => (
            <option key={id} value={id}>{filename}</option>
          ))}
        </select>

        <select
          aria-label="Entity type"
          value={entityType}
          onChange={(e) => {
            setEntityType(e.target.value);
            setEntity("");
          }}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white outline-none"
        >
          <option value="">All Entity Types</option>
          {Object.keys(data?.entity_values ?? {}).map((field) => (
            <option key={field} value={field}>{field}</option>
          ))}
        </select>

        {entityType && (
          <select
            aria-label="Entity"
            value={entity}
            onChange={(e) => setEntity(e.target.value)}
            className="max-w-[12rem] rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white outline-none"
          >
            <option value="">Any</option>
            {(data?.entity_values?.[entityType] ?? []).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        )}

        <label className="flex items-center gap-1.5 text-white/55">
          <span className="sr-only">From</span>
          <input
            type="date"
            aria-label="From date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-white outline-none"
          />
        </label>
        <label className="flex items-center gap-1.5 text-white/55">
          <span className="sr-only">To</span>
          <input
            type="date"
            aria-label="To date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-white outline-none"
          />
        </label>

        <button
          type="button"
          onClick={reset}
          className="rounded-lg border border-white/10 px-3 py-2 text-white/70 hover:text-white"
        >
          Reset
        </button>

        {data && (
          <span className="ml-auto text-white/40" data-testid="timeline-summary">
            {data.total} event{data.total === 1 ? "" : "s"} · {data.extraction.method} v
            {data.extraction.version} · {Math.round(data.took_ms)} ms
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1 gap-2">
        <section
          aria-label="Knowledge timeline"
          className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-white/10 bg-[#070b14]"
        >
          {error && <p className="p-4 text-sm text-rose-300">{error}</p>}
          {!error && loading && !data && <p className="p-4 text-sm text-white/50">Reading your knowledge…</p>}
          {!error && data && data.total === 0 && (
            <div className="p-6 text-sm" data-testid="timeline-empty">
              <p className="font-medium">No dated statements in your registered documents yet.</p>
              <p className="mt-1 text-white/55">
                The timeline is built from dates the documents themselves give — “in March 2021”,
                “on 2023-09-12”. Registering a document that states dates will fill it.
              </p>
            </div>
          )}

          {data && data.total > 0 && window_ && (
            <>
              <div className="relative h-10 shrink-0 border-b border-white/10">
                {ticks.map((tick) => (
                  <span
                    key={`${tick.label}-${tick.at}`}
                    style={{ left: `${tick.at}%` }}
                    className={cn(
                      "absolute top-2 -translate-x-1/2 text-[0.7rem]",
                      tick.major ? "font-semibold text-white/80" : "text-white/40",
                    )}
                  >
                    {tick.label}
                  </span>
                ))}
              </div>

              {/* The chronology the user states about themselves, behind the
                  chronology their documents state. It is a backdrop: an
                  artifact never takes its date from the period it falls in,
                  and no document is attached to an employer merely for
                  overlapping it in time. */}
              {placedAnchors.length > 0 && (
                <div
                  data-testid="anchor-band"
                  style={{ height: `${anchorRows * 20 + 8}px` }}
                  className="relative shrink-0 border-b border-white/10 bg-white/[0.02]"
                >
                  {placedAnchors.map(({ anchor, left, width, row }) => (
                    <button
                      key={anchor.id}
                      type="button"
                      data-testid="anchor-period"
                      title={`${anchor.title}${anchor.organization ? ` · ${anchor.organization}` : ""} — ${describeRange(anchor)}`}
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={() => setSelectedAnchor(anchor)}
                      style={{ left: `${left}%`, width: `${width}%`, top: `${row * 20 + 4}px` }}
                      className="absolute h-4 overflow-hidden rounded border border-white/20 bg-white/10 px-1.5 text-left text-[0.65rem] leading-[0.9rem] text-white/80 hover:bg-white/20"
                    >
                      <span className="truncate">{anchor.organization ?? anchor.title}</span>
                    </button>
                  ))}
                </div>
              )}

              <div
                ref={canvas}
                onPointerDown={beginPan}
                onWheel={onWheel}
                data-testid="timeline-canvas"
                className="relative min-h-0 flex-1 cursor-grab overflow-y-auto active:cursor-grabbing"
              >
                {/* Gridlines, one per tick, behind everything. */}
                {ticks.map((tick) => (
                  <span
                    key={`grid-${tick.label}-${tick.at}`}
                    aria-hidden="true"
                    style={{ left: `${tick.at}%` }}
                    className={cn(
                      "pointer-events-none absolute inset-y-0 w-px",
                      tick.major ? "bg-white/10" : "bg-white/5",
                    )}
                  />
                ))}

                {lanes.map((lane) => {
                  const placed = visible.get(lane.name) ?? [];
                  const count = lane.count;
                  if (lane.name === "Other" && count === 0) return null;
                  const rows = Math.max(1, ...placed.map((p) => p.row + 1));
                  return (
                    <div
                      key={lane.name}
                      data-testid={`lane-${lane.name}`}
                      style={{ minHeight: `${rows * ROW_HEIGHT_PX + 26}px` }}
                      className="relative border-b border-white/5"
                    >
                      <div className="pointer-events-none absolute left-0 top-2 z-10 pl-3">
                        <span
                          className="block text-xs font-semibold"
                          style={{ color: lane.color }}
                        >
                          {lane.name}
                        </span>
                        <span className="block text-[0.65rem] text-white/35">
                          {count} event{count === 1 ? "" : "s"}
                        </span>
                      </div>

                      {placed.map(({ event, left, row }) => {
                        const dimmed = related !== null && !related.has(event.id);
                        return (
                          <button
                            key={event.id}
                            type="button"
                            style={{ left: `${left}%`, top: `${row * ROW_HEIGHT_PX + 8}px` }}
                            onPointerDown={(e) => e.stopPropagation()}
                            onClick={() => setSelected(event)}
                            onDoubleClick={() =>
                              globalThis.open(api.artifactContentUrl(event.artifact_id), "_blank")
                            }
                            onMouseEnter={() => setHovered(event)}
                            onMouseLeave={() => setHovered(null)}
                            data-testid="timeline-event"
                            className={cn(
                              "absolute w-[10.5rem] rounded-lg border px-2.5 py-1.5 text-left transition-all duration-150",
                              "backdrop-blur hover:z-20 hover:scale-[1.03]",
                              selected?.id === event.id
                                ? "border-white/40 bg-white/15"
                                : "border-white/10 bg-white/[0.06] hover:border-white/25",
                              dimmed && "opacity-25",
                            )}
                          >
                            <span
                              aria-hidden="true"
                              className="absolute -left-1 top-2 size-2.5 rounded-full"
                              style={{
                                background: lane.color,
                                boxShadow: `0 0 10px ${lane.color}`,
                              }}
                            />
                            {/* The stem that ties a card to its moment. */}
                            <span
                              aria-hidden="true"
                              className="absolute -left-[1px] top-5 h-6 w-px"
                              style={{ background: `${lane.color}66` }}
                            />
                            {/* Document, moment, then what was said. The card
                                used to lead with a sentence lifted out of the
                                middle of the document, which never named the
                                document — so a lane of cards read as noise.
                                The sentence still earns its place, because
                                without it two cards from one document are
                                indistinguishable; it is just no longer the
                                headline. */}
                            <span className="block truncate text-[0.7rem] font-medium text-white">
                              {event.document?.title ?? event.filename}
                            </span>
                            <span className="block text-[0.65rem] text-white/45">
                              {formatEventDate(event)}
                              {event.document?.pages ? ` · ${event.document.pages}p` : ""}
                            </span>
                            <span className="mt-0.5 block truncate text-[0.6rem] text-white/35">
                              {event.title}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>

              <Navigator
                histogram={data.histogram}
                window={window_}
                range={data.range}
                laneColor={laneColor}
                onChange={setWindow}
              />

              <div className="flex flex-wrap items-center gap-3 border-t border-white/10 px-3 py-2 text-[0.65rem]">
                {lanes.filter((lane) => lane.name !== "Other" || lane.count > 0).map((lane) => (
                  <span key={lane.name} className="flex items-center gap-1.5 text-white/55">
                    <span className="size-2 rounded-full" style={{ background: lane.color }} />
                    {lane.name}
                  </span>
                ))}
                <span className="ml-auto flex items-center gap-2 text-white/55">
                  Zoom:
                  <button type="button" aria-label="Zoom in" onClick={() => zoom(0.7)} className="rounded border border-white/15 px-2 py-0.5">+</button>
                  <button type="button" aria-label="Zoom out" onClick={() => zoom(1.4)} className="rounded border border-white/15 px-2 py-0.5">−</button>
                  <span data-testid="zoom-level">{zoomPercent}%</span>
                  <button
                    type="button"
                    onClick={() => data && setWindow(fitAll(data))}
                    className="rounded border border-white/15 px-2 py-0.5"
                  >
                    Fit
                  </button>
                </span>
              </div>
            </>
          )}

          {/* An anchor, with the CV line that produced it. Related artifacts
              are deliberately absent: CEREBRO has no evidence tying a
              document to a period beyond their dates overlapping, and
              overlapping dates are not a relationship. */}
          {selectedAnchor && (
            <div
              data-testid="anchor-details"
              className="absolute bottom-24 right-4 z-30 max-w-sm rounded-lg border border-white/15 bg-[#0e1522]/97 p-3 text-xs shadow-2xl"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="font-medium text-white">{selectedAnchor.title}</p>
                <button
                  type="button"
                  aria-label="Close anchor details"
                  onClick={() => setSelectedAnchor(null)}
                  className="rounded p-0.5 text-white/50 hover:text-white"
                >
                  ✕
                </button>
              </div>
              <p className="mt-0.5 text-white/55">
                {describeRange(selectedAnchor)}
                {selectedAnchor.organization ? ` · ${selectedAnchor.organization}` : ""}
              </p>
              <p className="mt-1 text-[0.65rem] text-white/40">
                {selectedAnchor.event_type.replace(/_/g, " ")} ·{" "}
                {selectedAnchor.provenance_type === "user_entered"
                  ? "you added this"
                  : "from your CV"}
              </p>
              {selectedAnchor.evidence_text && (
                <p className="mt-2 border-t border-white/10 pt-2 italic text-white/45">
                  “{selectedAnchor.evidence_text}”
                </p>
              )}
            </div>
          )}

          {/* Hover preview: no request, nothing selected, just what it says. */}
          {hovered && hovered.id !== selected?.id && (
            <div
              data-testid="timeline-hover"
              className="pointer-events-none absolute bottom-24 left-4 z-30 max-w-sm rounded-lg border border-white/15 bg-[#0e1522]/95 p-3 text-xs shadow-2xl"
            >
              <p className="font-medium text-white">
                {hovered.document?.title ?? hovered.filename}
              </p>
              <p className="mt-0.5 text-[0.65rem] text-white/40">
                {hovered.filename}
                {hovered.document?.pages
                  ? ` · ${hovered.document.pages} page${hovered.document.pages === 1 ? "" : "s"}`
                  : ""}
              </p>

              {/* Three dates that do not mean the same thing, so each one
                  says where it came from. A date the file does not assert is
                  shown as unknown rather than filled in with the upload
                  time. */}
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 border-t border-white/10 pt-2">
                <DocumentDate label="Created" value={hovered.document?.created ?? null} />
                <DocumentDate label="Modified" value={hovered.document?.modified ?? null} />
                <DocumentDate label="Registered" value={hovered.document?.registered ?? null} />
              </dl>

              <p className="mt-2 border-t border-white/10 pt-2 text-white/55">
                {formatEventDate(hovered)} · {hovered.event_type}
              </p>
              <p className="mt-1 line-clamp-3 text-white/45">{hovered.evidence}</p>
            </div>
          )}
        </section>

        {panelOpen ? (
          <EventPanel
            event={selected}
            onClose={() => setPanelOpen(false)}
            onClear={() => setSelected(null)}
            onSelect={setSelected}
          />
        ) : (
          <button
            type="button"
            onClick={() => setPanelOpen(true)}
            aria-label="Show event details"
            className="shrink-0 rounded-xl border border-white/10 bg-[#0b111c] px-2 text-xs text-white/60"
          >
            ▸
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * One of the document's dates, with its origin.
 *
 * Created and modified are claims the file itself makes; CEREBRO cannot
 * establish either by reading the content, so a format that does not carry
 * them leaves them unknown. Saying "unknown" is the honest answer and is
 * deliberately not replaced by the upload time, which records when CEREBRO
 * received the file rather than when anyone wrote it.
 */
function DocumentDate({ label, value }: { label: string; value: string | null }) {
  return (
    <>
      <dt className="text-[0.65rem] text-white/40">{label}</dt>
      <dd className={cn("text-[0.65rem]", value ? "text-white/70" : "text-white/30")}>
        {value
          ? new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
              day: "numeric",
              month: "short",
              year: "numeric",
            })
          : label === "Registered"
            ? "—"
            : "not stated by the document"}
      </dd>
    </>
  );
}
