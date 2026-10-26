"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { EventPanel } from "@/components/timeline/EventPanel";
import { Navigator } from "@/components/timeline/Navigator";
import { describeRange } from "@/app/construct/profile/CvPanel";
import {
  colorForLane,
  dateMs,
  describeSpan,
  describeWindow,
  formatEventDate,
  fractionOf,
} from "@/components/timeline/lanes";
import { api, ApiError } from "@/lib/api";
import type { CerebroAnchor, CerebroTimeline, CerebroTimelineEventDetail } from "@/lib/api";
import { cn } from "@/lib/cn";

const YEAR = 365.25 * 24 * 60 * 60 * 1000;
const MIN_SPAN = YEAR / 4;
const MAX_SPAN = YEAR * 60;
const MONTH = YEAR / 12;
/** Axis steps, in months: the first one whose labels sit this far apart wins. */
const TICK_STEPS = [1, 3, 6, 12, 24, 60, 120, 240, 600];
const MIN_TICK_GAP_PX = 72;
/** Cards narrower than this collide, so they are packed onto another row. */
const CARD_WIDTH_PX = 170;
// A card is three lines now — document, date, statement — so rows sit
// further apart than they did at two.
const ROW_HEIGHT_PX = 58;
// The lane's name has a line of its own above the cards. Drawn over the
// canvas, it sat underneath any card dated near the left edge.
const LANE_HEADER_PX = 26;

interface Window {
  from: number;
  to: number;
}

interface Placed {
  event: CerebroTimelineEventDetail;
  left: number;
  row: number;
  /** Near the right edge a card opens to the left of its moment instead. */
  flipped: boolean;
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
  // Cited dates — a paper's year, a link's /2021/ — are not events in the
  // document, so they are hidden until asked for. The count is always shown.
  const [references, setReferences] = useState(false);
  const [width, setWidth] = useState(1000);

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
  const frame = useRef<HTMLElement>(null);

  // The axis is laid out in pixels, not in a fixed number of labels, so it
  // needs the real width — and again whenever the panel or window resizes.
  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
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
        references,
      })
      .then((body) => {
        setData(body);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : "Could not load the timeline.");
      })
      .finally(() => setLoading(false));
  }, [categories, source, entityType, entity, start, end, references]);

  useEffect(load, [load]);

  // The first load decides the window; later ones leave it alone, so
  // filtering does not throw away where the user had navigated to.
  // Showing or hiding references changes the range itself, so it refits.
  const fitted = useRef(false);
  useEffect(() => {
    if (!data || fitted.current) return;
    fitted.current = true;
    setWindow(fitAll(data));
  }, [data]);

  function toggleReferences() {
    fitted.current = false;
    setReferences((current) => !current);
  }

  function fitAll(body: CerebroTimeline): Window | null {
    if (!body.range.earliest || !body.range.latest) return null;
    const from = dateMs(body.range.earliest);
    const to = dateMs(body.range.latest);
    const pad = Math.max((to - from) * 0.06, YEAR / 6);
    return { from: from - pad, to: to + pad };
  }

  /**
   * The most recent N years of the library, ending at its latest event.
   *
   * Centring on the current view looked reasonable until the view was wide:
   * one year in the middle of 1941–2030 is an empty 1985.
   */
  function showRecent(years: number) {
    if (!data?.range.latest) return;
    const to = dateMs(data.range.latest) + YEAR / 24;
    setWindow({ from: to - YEAR * years, to });
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
    const cardWidth = (CARD_WIDTH_PX / Math.max(width, 1)) * 100;

    for (const lane of lanes) {
      const inLane = data.events
        .filter((event) => event.category === lane.name)
        .map((event) => {
          const left = fractionOf(event.date, window_.from, window_.to) * 100;
          // A card that would run off the right edge opens to the left of its
          // moment instead of being cut off.
          return { event, left, row: 0, flipped: left + cardWidth > 100 };
        })
        // Only what is on screen is rendered.
        .filter((placed) => placed.left > -12 && placed.left <= 100)
        .sort((a, b) => a.left - b.left);

      // Greedy packing over the space each card occupies: one that would
      // overlap the last card on its row drops to the next. Nothing is
      // hidden and nothing overlaps.
      const rowEnds: number[] = [];
      for (const placed of inLane) {
        const startsAt = placed.flipped ? placed.left - cardWidth : placed.left;
        let row = rowEnds.findIndex((end_) => startsAt >= end_);
        if (row === -1) {
          row = rowEnds.length;
          rowEnds.push(-Infinity);
        }
        rowEnds[row] = startsAt + cardWidth;
        placed.row = row;
      }
      byLane.set(lane.name, inLane);
    }
    return byLane;
  }, [data, window_, lanes, width]);

  /**
   * Axis ticks, spaced by pixels rather than by calendar.
   *
   * The step is the first of 1, 3, 6 months or 1, 2, 5, 10, 20, 50 years whose
   * labels land at least MIN_TICK_GAP_PX apart at the current width. Labelling
   * every year regardless printed fifty of them across a fifty-year window,
   * run together into one unreadable string.
   */
  const ticks = useMemo(() => {
    if (!window_) return [] as { at: number; label: string; major: boolean }[];
    const span = window_.to - window_.from;
    const pixels = Math.max(width, 320);
    const step =
      TICK_STEPS.find((months) => ((months * MONTH) / span) * pixels >= MIN_TICK_GAP_PX) ??
      TICK_STEPS[TICK_STEPS.length - 1];
    // Years are the major lines below a yearly step; decades up to five-year
    // steps; beyond that, every fifth tick.
    const majorEvery = step < 12 ? 12 : step <= 60 ? 120 : step * 5;

    const first = new Date(window_.from);
    const years = step / 12;
    let cursor =
      step >= 12
        ? Date.UTC(Math.floor(first.getUTCFullYear() / years) * years, 0, 1)
        : Date.UTC(first.getUTCFullYear(), Math.floor(first.getUTCMonth() / step) * step, 1);

    const out: { at: number; label: string; major: boolean }[] = [];
    while (cursor <= window_.to) {
      const date = new Date(cursor);
      const at = ((cursor - window_.from) / span) * 100;
      if (at >= 0) {
        const newYear = date.getUTCMonth() === 0;
        out.push({
          at,
          label:
            step >= 12 || newYear
              ? String(date.getUTCFullYear())
              : date.toLocaleDateString(undefined, { month: "short", timeZone: "UTC" }),
          major: (date.getUTCFullYear() * 12 + date.getUTCMonth()) % majorEvery === 0,
        });
      }
      cursor = Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + step, 1);
    }
    return out;
  }, [window_, width]);

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
    fitted.current = false;
    if (data) setWindow(fitAll(data));
  }

  return (
    <div className="flex h-[calc(100dvh-7.5rem)] min-h-0 flex-col gap-2 text-scene-ink">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Timeline</h1>
          <p className="text-sm text-scene-ink/55">Explore the evolution of your knowledge over time</p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-scene-ink/10 bg-scene-ink/5 p-0.5 text-xs">
          <span className="rounded-md bg-sky-500 px-3 py-1.5 font-medium text-on-bright">Timeline</span>
          <Link href="/construct/galaxy" className="rounded-md px-3 py-1.5 text-scene-ink/65 hover:text-scene-ink">
            Galaxy
          </Link>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select
          aria-label="Category"
          value={categories[0] ?? ""}
          onChange={(e) => setCategories(e.target.value ? [e.target.value] : [])}
          className="rounded-lg border border-scene-ink/10 bg-scene-ink/5 px-3 py-2 text-scene-ink outline-none"
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
          className="max-w-[12rem] rounded-lg border border-scene-ink/10 bg-scene-ink/5 px-3 py-2 text-scene-ink outline-none"
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
          className="rounded-lg border border-scene-ink/10 bg-scene-ink/5 px-3 py-2 text-scene-ink outline-none"
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
            className="max-w-[12rem] rounded-lg border border-scene-ink/10 bg-scene-ink/5 px-3 py-2 text-scene-ink outline-none"
          >
            <option value="">Any</option>
            {(data?.entity_values?.[entityType] ?? []).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        )}

        <label className="flex items-center gap-1.5 text-scene-ink/55">
          <span className="sr-only">From</span>
          <input
            type="date"
            aria-label="From date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="rounded-lg border border-scene-ink/10 bg-scene-ink/5 px-2 py-2 text-scene-ink outline-none"
          />
        </label>
        <label className="flex items-center gap-1.5 text-scene-ink/55">
          <span className="sr-only">To</span>
          <input
            type="date"
            aria-label="To date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="rounded-lg border border-scene-ink/10 bg-scene-ink/5 px-2 py-2 text-scene-ink outline-none"
          />
        </label>

        <button
          type="button"
          onClick={reset}
          className="rounded-lg border border-scene-ink/10 px-3 py-2 text-scene-ink/70 hover:text-scene-ink"
        >
          Reset
        </button>

        {data && (
          <span className="ml-auto flex items-center gap-2 text-scene-ink/55" data-testid="timeline-summary">
            <span>
              <span className="font-medium text-scene-ink">{data.total}</span> event
              {data.total === 1 ? "" : "s"}
            </span>
            {data.references.total > 0 && (
              <>
                <span aria-hidden="true">·</span>
                <span data-testid="timeline-references">
                  {data.references.total} reference{data.references.total === 1 ? "" : "s"}{" "}
                  {data.references.included ? "shown" : "hidden"}
                </span>
                <button
                  type="button"
                  onClick={toggleReferences}
                  title="Dates a document cites — a paper's year, a link's path — rather than states as something that happened."
                  className="rounded-md border border-scene-ink/15 px-2 py-0.5 text-scene-ink/75 hover:text-scene-ink"
                >
                  {data.references.included ? "Hide" : "Show"}
                </button>
              </>
            )}
            <span
              className="text-scene-ink/30"
              title={`${data.extraction.method} v${data.extraction.version} · ${Math.round(data.took_ms)} ms`}
            >
              · dates read from the text ({data.extraction.method})
            </span>
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1 gap-2">
        <section
          ref={frame}
          aria-label="Knowledge timeline"
          className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-scene-ink/10 bg-scene"
        >
          {error && <p className="p-4 text-sm text-rose-300">{error}</p>}
          {!error && loading && !data && <p className="p-4 text-sm text-scene-ink/50">Reading your knowledge…</p>}
          {!error && data && data.total === 0 && (
            <div className="p-6 text-sm" data-testid="timeline-empty">
              <p className="font-medium">No dated statements in your registered documents yet.</p>
              <p className="mt-1 text-scene-ink/55">
                The timeline is built from dates the documents themselves give — “in March 2021”,
                “on 2023-09-12”. Registering a document that states dates will fill it.
              </p>
            </div>
          )}

          {data && data.total > 0 && window_ && (
            <>
              {/* What is on screen, in words, and the ways to change it. */}
              <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-scene-ink/10 px-3 py-1.5 text-xs">
                <p>
                  <span className="font-medium" data-testid="timeline-window">
                    {describeWindow(window_.from, window_.to)}
                  </span>
                  <span className="text-scene-ink/45" data-testid="zoom-level">
                    {" "}
                    · {describeSpan(window_.to - window_.from)}
                  </span>
                </p>
                <div role="group" aria-label="Zoom" className="flex items-center gap-1 text-scene-ink/70">
                  <button type="button" aria-label="Zoom out" onClick={() => zoom(1.4)} className="size-7 rounded-md border border-scene-ink/15 hover:text-scene-ink">−</button>
                  <button type="button" aria-label="Zoom in" onClick={() => zoom(0.7)} className="size-7 rounded-md border border-scene-ink/15 hover:text-scene-ink">+</button>
                  <span aria-hidden="true" className="mx-1 h-4 w-px bg-scene-ink/15" />
                  <button type="button" onClick={() => data && setWindow(fitAll(data))} className="rounded-md border border-scene-ink/15 px-2 py-1 hover:text-scene-ink">All</button>
                  <button type="button" onClick={() => showRecent(10)} title="The most recent 10 years" className="rounded-md border border-scene-ink/15 px-2 py-1 hover:text-scene-ink">10 y</button>
                  <button type="button" onClick={() => showRecent(1)} title="The most recent year" className="rounded-md border border-scene-ink/15 px-2 py-1 hover:text-scene-ink">1 y</button>
                </div>
              </div>

              <div className="relative h-7 shrink-0 border-b border-scene-ink/10" data-testid="timeline-axis">
                {/* A label too close to the right edge would be cut off; its
                    gridline still marks the moment. */}
                {ticks.filter((tick) => tick.at < 96).map((tick) => (
                  <span
                    key={`${tick.label}-${tick.at}`}
                    style={{ left: `${tick.at}%` }}
                    className={cn(
                      "absolute top-1.5 whitespace-nowrap pl-1.5 text-[0.7rem]",
                      tick.major ? "font-semibold text-scene-ink/85" : "text-scene-ink/50",
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
                  className="relative shrink-0 border-b border-scene-ink/10 bg-scene-ink/[0.02]"
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
                      className="absolute h-4 overflow-hidden rounded border border-scene-ink/20 bg-scene-ink/10 px-1.5 text-left text-[0.65rem] leading-[0.9rem] text-scene-ink/80 hover:bg-scene-ink/20"
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
                      tick.major ? "bg-scene-ink/10" : "bg-scene-ink/5",
                    )}
                  />
                ))}

                {lanes.map((lane) => {
                  const placed = visible.get(lane.name) ?? [];
                  const count = lane.count;
                  // A lane with nothing in it is a row of noise.
                  if (count === 0) return null;
                  const rows = Math.max(1, ...placed.map((p) => p.row + 1));
                  return (
                    <div
                      key={lane.name}
                      data-testid={`lane-${lane.name}`}
                      style={{ minHeight: `${LANE_HEADER_PX + rows * ROW_HEIGHT_PX + 8}px` }}
                      className="relative border-b border-scene-ink/5"
                    >
                      <div className="pointer-events-none sticky left-0 z-10 flex items-baseline gap-2 px-3 pt-1.5">
                        <span className="text-xs font-semibold" style={{ color: lane.color }}>
                          {lane.name}
                        </span>
                        <span className="text-[0.65rem] text-scene-ink/40">
                          {count} event{count === 1 ? "" : "s"}
                        </span>
                      </div>

                      {placed.map(({ event, left, row, flipped }) => {
                        const dimmed = related !== null && !related.has(event.id);
                        const cited = event.kind === "reference";
                        return (
                          <button
                            key={event.id}
                            type="button"
                            style={{
                              ...(flipped ? { right: `${100 - left}%` } : { left: `${left}%` }),
                              top: `${LANE_HEADER_PX + row * ROW_HEIGHT_PX}px`,
                            }}
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
                                ? "border-scene-ink/40 bg-scene-ink/15"
                                : "border-scene-ink/10 bg-scene-ink/[0.06] hover:border-scene-ink/25",
                              cited && "border-dashed opacity-70",
                              dimmed && "opacity-25",
                            )}
                          >
                            <span
                              aria-hidden="true"
                              className={cn("absolute top-2 size-2.5 rounded-full", flipped ? "-right-1" : "-left-1")}
                              style={{
                                background: cited ? "transparent" : lane.color,
                                border: cited ? `1.5px solid ${lane.color}` : undefined,
                                boxShadow: cited ? undefined : `0 0 10px ${lane.color}`,
                              }}
                            />
                            {/* The stem that ties a card to its moment. */}
                            <span
                              aria-hidden="true"
                              className={cn("absolute top-5 h-6 w-px", flipped ? "-right-[1px]" : "-left-[1px]")}
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
                            <span className="block truncate text-[0.7rem] font-medium text-scene-ink">
                              {event.document?.title ?? event.filename}
                            </span>
                            <span className="block text-[0.65rem] text-scene-ink/45">
                              {formatEventDate(event)}
                              {cited ? " · cited" : event.document?.pages ? ` · ${event.document.pages}p` : ""}
                            </span>
                            <span className="mt-0.5 block truncate text-[0.6rem] text-scene-ink/35">
                              {event.title}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>

              <Navigator histogram={data.histogram} window={window_} onChange={setWindow} />
            </>
          )}

          {/* An anchor, with the CV line that produced it. Related artifacts
              are deliberately absent: CEREBRO has no evidence tying a
              document to a period beyond their dates overlapping, and
              overlapping dates are not a relationship. */}
          {selectedAnchor && (
            <div
              data-testid="anchor-details"
              className="absolute bottom-24 right-4 z-30 max-w-sm rounded-lg border border-scene-ink/15 bg-scene-overlay/97 p-3 text-xs shadow-2xl"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="font-medium text-scene-ink">{selectedAnchor.title}</p>
                <button
                  type="button"
                  aria-label="Close anchor details"
                  onClick={() => setSelectedAnchor(null)}
                  className="rounded p-0.5 text-scene-ink/50 hover:text-scene-ink"
                >
                  ✕
                </button>
              </div>
              <p className="mt-0.5 text-scene-ink/55">
                {describeRange(selectedAnchor)}
                {selectedAnchor.organization ? ` · ${selectedAnchor.organization}` : ""}
              </p>
              <p className="mt-1 text-[0.65rem] text-scene-ink/40">
                {selectedAnchor.event_type.replace(/_/g, " ")} ·{" "}
                {selectedAnchor.provenance_type === "user_entered"
                  ? "you added this"
                  : "from your CV"}
              </p>
              {selectedAnchor.evidence_text && (
                <p className="mt-2 border-t border-scene-ink/10 pt-2 italic text-scene-ink/45">
                  “{selectedAnchor.evidence_text}”
                </p>
              )}
            </div>
          )}

          {/* Hover preview: no request, nothing selected, just what it says. */}
          {hovered && hovered.id !== selected?.id && (
            <div
              data-testid="timeline-hover"
              className="pointer-events-none absolute bottom-24 left-4 z-30 max-w-sm rounded-lg border border-scene-ink/15 bg-scene-overlay/95 p-3 text-xs shadow-2xl"
            >
              <p className="font-medium text-scene-ink">
                {hovered.document?.title ?? hovered.filename}
              </p>
              <p className="mt-0.5 text-[0.65rem] text-scene-ink/40">
                {hovered.filename}
                {hovered.document?.pages
                  ? ` · ${hovered.document.pages} page${hovered.document.pages === 1 ? "" : "s"}`
                  : ""}
              </p>

              {/* Three dates that do not mean the same thing, so each one
                  says where it came from. A date the file does not assert is
                  shown as unknown rather than filled in with the upload
                  time. */}
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 border-t border-scene-ink/10 pt-2">
                <DocumentDate label="Created" value={hovered.document?.created ?? null} />
                <DocumentDate label="Modified" value={hovered.document?.modified ?? null} />
                <DocumentDate label="Registered" value={hovered.document?.registered ?? null} />
              </dl>

              <p className="mt-2 border-t border-scene-ink/10 pt-2 text-scene-ink/55">
                {formatEventDate(hovered)} ·{" "}
                {hovered.kind === "reference"
                  ? `cited (${hovered.reference_basis}) — a date this document refers to, not something that happened in it`
                  : hovered.event_type}
              </p>
              <p className="mt-1 line-clamp-3 text-scene-ink/45">{hovered.evidence}</p>
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
            className="shrink-0 rounded-xl border border-scene-ink/10 bg-scene-sunken px-2 text-xs text-scene-ink/60"
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
      <dt className="text-[0.65rem] text-scene-ink/40">{label}</dt>
      <dd className={cn("text-[0.65rem]", value ? "text-scene-ink/70" : "text-scene-ink/30")}>
        {value
          ? // Created and modified are dates; registered is a full timestamp. Both are read
            // as a calendar date, so a timestamp no longer becomes "Invalid Date".
            new Date(dateMs(value)).toLocaleDateString(undefined, {
              day: "numeric",
              month: "short",
              year: "numeric",
              timeZone: "UTC",
            })
          : label === "Registered"
            ? "—"
            : "not stated by the document"}
      </dd>
    </>
  );
}
