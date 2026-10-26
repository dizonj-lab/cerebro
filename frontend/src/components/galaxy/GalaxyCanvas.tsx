"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { layout, reachOf, VIEWBOX } from "@/components/galaxy/layout";
import { colorFor, hueFor } from "@/components/galaxy/palette";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { CerebroGalaxy, CerebroLens, GraphEdge, GraphNode, SimilaritySpace } from "@/lib/api";
import { cn } from "@/lib/cn";

// Scene colours come from tokens, so the canvas follows the light and dark theme with the page.
const INK = "var(--color-scene-ink)";
const OUTSIDE = "var(--color-ink-subtle)";
const LABEL = "color-mix(in srgb, var(--color-scene-ink) 90%, transparent)";
const LABEL_MUTED = "color-mix(in srgb, var(--color-scene-ink) 65%, transparent)";

interface GalaxyCanvasProps {
  graph: CerebroGalaxy;
  selectedId: string | null;
  /**
   * The part of the map an answer rests on, when one has been mapped.
   *
   * `cited` are the documents the answer actually quoted, `retrieved` the
   * ones that were searched up but not used. Everything else greys out. The
   * distinction is what retrieval and the citation guard established, not a
   * judgement about quality.
   */
  answerMap?: { cited: Set<string>; retrieved: Set<string> } | null;
  expandedTopic: string | null;
  onSelect: (node: GraphNode) => void;
  onExpand: (topic: string | null) => void;
}

/**
 * The Galaxy.
 *
 * SVG rather than Canvas or WebGL: the node count is capped server-side at a
 * couple of dozen, which SVG renders comfortably, and it keeps nodes as real
 * elements — focusable, hoverable and reachable by keyboard without
 * reimplementing hit-testing. If the caps are ever raised past a few hundred
 * nodes this is the piece to replace, and the layout module is already
 * separate from the rendering for that reason.
 *
 * Zoom, pan and rotation are a transform on one group, so none of them
 * re-renders React.
 *
 * Rotation earns its place on a radial layout: turning the galaxy brings a
 * cluster hidden behind a label round to the front without disturbing the
 * layout, which is the source of truth for every relationship drawn. It is
 * a change of viewpoint, never of data. Labels counter-rotate so text stays
 * horizontal at any angle — a knowledge map you have to tilt your head to
 * read is a worse map.
 */
export function GalaxyCanvas({
  graph,
  selectedId,
  answerMap = null,
  expandedTopic,
  onSelect,
  onExpand,
}: GalaxyCanvasProps) {
  const [view, setView] = useState({ scale: 1, x: 0, y: 0, angle: 0 });
  const [hovered, setHovered] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<GraphEdge | null>(null);
  // The what-if lens: a piece of text placed among the topics by the same
  // model that embedded the library. Nothing is stored.
  const [lens, setLens] = useState<CerebroLens | null>(null);
  const [lensText, setLensText] = useState("");
  const [lensBusy, setLensBusy] = useState(false);
  const [lensError, setLensError] = useState<string | null>(null);

  async function placeText(event: React.FormEvent) {
    event.preventDefault();
    const text = lensText.trim();
    if (text.length < 2) return;
    setLensBusy(true);
    setLensError(null);
    try {
      setLens(await api.lens(text));
    } catch (e) {
      setLensError(e instanceof ApiError ? e.message : "Could not place that text.");
    } finally {
      setLensBusy(false);
    }
  }
  const drag = useRef<{
    mode: "pan" | "rotate";
    x: number;
    y: number;
    ox: number;
    oy: number;
    angle: number;
    from: number;
  } | null>(null);
  // Mirrored in state only so the cursor can change; the ref carries the
  // actual drag maths, because a ref must not be read during render.
  const [dragging, setDragging] = useState(false);

  // Nodes the user has dragged. The computed layout stays the source of
  // truth for everything else, so dragging one node never relays the rest.
  const [moved, setMoved] = useState<Record<string, { x: number; y: number }>>({});
  const nodeDrag = useRef<{ id: string; x: number; y: number; ox: number; oy: number } | null>(
    null,
  );

  const positions = useMemo(() => {
    const base = layout(graph.nodes, expandedTopic, graph.edges);
    for (const [id, point] of Object.entries(moved)) {
      const existing = base.get(id);
      if (existing) base.set(id, { ...existing, ...point });
    }
    return base;
  }, [graph.nodes, graph.edges, expandedTopic, moved]);

  // What is "in focus" decides what stays bright and what dims. Hover is a
  // preview; selection persists.
  const focus = hovered ?? selectedId;
  // Whether hiding the weakest edges would leave anything to look at. An
  // edge resting on one document is the weakest claim the graph makes, but
  // in a young library it is also the only claim available — hiding it
  // unconditionally drew an empty map and called that restraint. So the
  // threshold is relative: weak edges step aside when stronger ones exist,
  // and stand in for them when none do.
  // Only documented edges count here: a strong similarity must not hide the
  // one-document co-occurrences of a young library.
  const hasStrongEdges = useMemo(
    () => graph.edges.some((edge) => edge.strong && !isMeasured(edge)),
    [graph.edges],
  );
  // The topics the lens text lands near: above typical, strongest first.
  const lensTargets = useMemo(
    () => (lens ? lens.topics.filter((t) => t.above_typical && positions.has(t.id)).slice(0, 3) : []),
    [lens, positions],
  );
  const connected = useMemo(() => {
    // A mapped answer takes over the dimming: the map is the point, and
    // hovering should not wash it away.
    if (answerMap) return new Set([...answerMap.cited, ...answerMap.retrieved]);
    // So does the lens: what matters is where the text would land.
    if (lens) return new Set(lensTargets.map((t) => t.id));
    if (!focus) return null;
    const set = new Set<string>([focus]);
    for (const edge of graph.edges) {
      if (edge.source === focus) set.add(edge.target);
      if (edge.target === focus) set.add(edge.source);
    }
    return set;
  }, [focus, graph.edges, answerMap, lens, lensTargets]);

  const reset = useCallback(() => {
    setView({ scale: 1, x: 0, y: 0, angle: 0 });
    setMoved({});
  }, []);
  const rotate = useCallback(
    (degrees: number) => setView((v) => ({ ...v, angle: (v.angle + degrees) % 360 })),
    [],
  );
  const zoom = useCallback(
    (factor: number) =>
      setView((v) => ({ ...v, scale: Math.min(3, Math.max(0.5, v.scale * factor)) })),
    [],
  );

  function onPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    // Only the empty canvas starts a gesture. Capturing the pointer whenever
    // it went down anywhere meant a press on a node was retargeted to the svg
    // and never produced a click, so nodes could not be selected at all.
    if (event.target !== event.currentTarget) return;
    // Dragging still moves the galaxy, which is what the hand expects.
    // Holding shift turns it instead, so one gesture does not have to mean
    // two things and neither has to be given up.
    const mode = event.shiftKey ? "rotate" : "pan";
    drag.current = {
      mode,
      x: event.clientX,
      y: event.clientY,
      ox: view.x,
      oy: view.y,
      angle: view.angle,
      from: angleFromCentre(event),
    };
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const start = drag.current;
    if (!start) return;
    if (start.mode === "rotate") {
      // The galaxy follows the pointer round its centre, so the turn tracks
      // the hand rather than an arbitrary pixels-per-degree rate.
      const turned = angleFromCentre(event) - start.from;
      setView((v) => ({ ...v, angle: start.angle + turned }));
      return;
    }
    setView((v) => {
      // The pan is applied before the rotation, so a screen-space drag has
      // to be turned back into layout space or the galaxy slides sideways
      // when it is turned.
      const [dx, dy] = unrotate(
        (event.clientX - start.x) / v.scale,
        (event.clientY - start.y) / v.scale,
        v.angle,
      );
      return { ...v, x: start.ox + dx, y: start.oy + dy };
    });
  }
  function endDrag() {
    drag.current = null;
    setDragging(false);
  }

  const hoveredNode = hovered ? positions.get(hovered)?.node : undefined;
  const hoveredPoint = hovered ? positions.get(hovered) : undefined;

  return (
    <div className="relative size-full overflow-hidden bg-scene">
      {/* A still backdrop rather than an animated starfield: atmosphere
          without a compositing loop running behind every interaction. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          background:
            "radial-gradient(60% 55% at 50% 45%, var(--scene-glow-1), transparent 70%)," +
            "radial-gradient(40% 40% at 18% 70%, var(--scene-glow-2), transparent 70%)," +
            "radial-gradient(35% 40% at 82% 28%, var(--scene-glow-3), transparent 70%)",
        }}
      />

      <svg
        viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`}
        className={cn("relative size-full touch-none", dragging ? "cursor-grabbing" : "cursor-grab")}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={() => {
          endDrag();
          setHovered(null);
        }}
        role="application"
        aria-label="Knowledge Galaxy"
      >
        <defs>
          {graph.nodes.map((node) => {
            const hue = hueFor(node.category);
            return (
              <radialGradient key={node.id} id={gradientId(node.id)}>
                <stop offset="0%" stopColor={`hsl(${hue} 100% 92%)`} />
                <stop offset="45%" stopColor={`hsl(${hue} 90% 62%)`} />
                <stop offset="100%" stopColor={`hsl(${hue} 85% 45%)`} stopOpacity="0.1" />
              </radialGradient>
            );
          })}
          {graph.edges.map((edge) => {
            const a = positions.get(edge.source);
            const b = positions.get(edge.target);
            if (!a || !b) return null;
            return (
              <linearGradient
                key={edge.id}
                id={gradientId(edge.id)}
                gradientUnits="userSpaceOnUse"
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              >
                <stop offset="0%" stopColor={colorFor(a.node.category)} />
                <stop offset="100%" stopColor={colorFor(b.node.category)} />
              </linearGradient>
            );
          })}
        </defs>

        <g
          data-testid="galaxy-transform"
          data-angle={Math.round(view.angle)}
          transform={`translate(${VIEWBOX.width / 2} ${VIEWBOX.height / 2}) scale(${view.scale}) rotate(${view.angle}) translate(${-VIEWBOX.width / 2 + view.x} ${-VIEWBOX.height / 2 + view.y})`}
        >
          {graph.edges.map((edge) => {
            const a = positions.get(edge.source);
            const b = positions.get(edge.target);
            if (!a || !b) return null;
            const touches = focus === edge.source || focus === edge.target;
            // A measured edge is a cosine similarity; everything else is an
            // observation about documents. The two are drawn differently so
            // the eye never mistakes one for the other.
            const measured = isMeasured(edge);
            const strength = edge.strength ?? 0;
            // Progressive disclosure, but only where there is something to
            // disclose progressively: a weak edge is hidden when stronger
            // ones exist, and shown anyway when they do not. Either way it
            // reappears when one of its endpoints is in focus, which is when
            // the user is asking about that node specifically. A measured
            // edge is never hidden: a weak resemblance is drawn faint instead,
            // which is what makes it a weak one.
            if (!measured && !edge.strong && hasStrongEdges && !touches) return null;
            const lit = !connected || connected.has(edge.source) || connected.has(edge.target);
            // A gentle curve reads better than a straight chord on a radial
            // layout, and separates edges that share endpoints.
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2 - Math.abs(a.x - b.x) * 0.07;
            const path = `M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`;
            // The curve's own midpoint, where its figure is written.
            const lx = (a.x + 2 * mx + b.x) / 4;
            const ly = (a.y + 2 * my + b.y) / 4;
            // Figures only on lines that are a similarity link. A passage's
            // fit to its own topic, written on the line to its parent, read
            // as a score for a relationship; it is in the hover card instead.
            const showFigure =
              measured &&
              typeof edge.similarity === "number" &&
              lit &&
              (edge.source.startsWith("fragment:") || edge.discovered || touches);
            return (
              <g key={edge.id}>
                <path
                  d={path}
                  fill="none"
                  stroke={`url(#${gradientId(edge.id)})`}
                  strokeWidth={measured ? 0.6 + strength * 1.8 : 0.6 + Math.min(edge.weight, 4) * 0.45}
                  opacity={
                    measured
                      ? lit
                        ? 0.22 + strength * 0.6
                        : 0.05
                      : lit
                        ? edge.strong
                          ? 0.55
                          : 0.3
                        : 0.08
                  }
                  strokeDasharray={
                    measured ? (edge.discovered ? "1.5 3.5" : undefined) : edge.strong ? undefined : "4 3"
                  }
                  strokeLinecap="round"
                  data-kind={edge.kind}
                  data-strength={measured ? strength : undefined}
                  className="transition-opacity duration-200"
                />
                {showFigure && (
                  <g
                    transform={`translate(${lx} ${ly}) rotate(${-view.angle})`}
                    className="pointer-events-none select-none"
                    data-testid="edge-figure"
                  >
                    <rect
                      x={-13}
                      y={-6.5}
                      width={26}
                      height={13}
                      rx={6.5}
                      style={{ fill: "var(--color-scene)", stroke: LABEL_MUTED }}
                      strokeWidth={0.5}
                      opacity={0.92}
                    />
                    <text
                      y={3}
                      textAnchor="middle"
                      style={{ fontSize: 8.5, fontWeight: 600, fill: LABEL }}
                    >
                      {Math.round((edge.similarity ?? 0) * 100)}%
                    </text>
                  </g>
                )}
                {/* A wide invisible companion: a 1px curve is far too thin
                    to hit with a pointer, and an edge nobody can hover is an
                    edge that cannot explain itself. */}
                <path
                  d={path}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={6}
                  data-testid="galaxy-edge"
                  className="cursor-help"
                  onPointerEnter={() => setHoveredEdge(edge)}
                  onPointerLeave={() => setHoveredEdge(null)}
                />
              </g>
            );
          })}

          {lens && <LensMark lens={lens} targets={lensTargets} positions={positions} angle={view.angle} />}

          {[...positions.values()].map(({ node, x, y, radius }) => {
            const lit = !connected || connected.has(node.id);
            const isSelected = node.id === selectedId;
            // Three states when an answer is mapped: quoted, merely found,
            // and not part of this answer at all.
            const cited = answerMap?.cited.has(node.id) ?? false;
            const retrieved = answerMap?.retrieved.has(node.id) ?? false;
            const outside = Boolean(answerMap) && !cited && !retrieved;
            const mappedOpacity = answerMap ? (cited ? 1 : retrieved ? 0.6 : 0.16) : null;
            return (
              <g
                key={node.id}
                transform={`translate(${x} ${y}) rotate(${-view.angle})`}
                opacity={mappedOpacity ?? (lit ? 1 : 0.25)}
                onPointerEnter={() => setHovered(node.id)}
                onPointerDown={(event) => {
                  // Nodes are draggable so a crowded cluster can be pulled
                  // apart to read it. Capture on the node, not the canvas.
                  event.stopPropagation();
                  const start = positions.get(node.id);
                  if (!start) return;
                  nodeDrag.current = {
                    id: node.id,
                    x: event.clientX,
                    y: event.clientY,
                    ox: start.x,
                    oy: start.y,
                  };
                  (event.target as Element).setPointerCapture?.(event.pointerId);
                }}
                onPointerMove={(event) => {
                  const start = nodeDrag.current;
                  if (!start || start.id !== node.id) return;
                  const svg = event.currentTarget.ownerSVGElement;
                  const scaleX = (svg?.clientWidth ?? VIEWBOX.width) / VIEWBOX.width;
                  // Same correction as the pan: the pointer moves in screen
                  // space, the node lives in layout space.
                  const [dx, dy] = unrotate(
                    (event.clientX - start.x) / (scaleX * view.scale),
                    (event.clientY - start.y) / (scaleX * view.scale),
                    view.angle,
                  );
                  setMoved((current) => ({
                    ...current,
                    [node.id]: { x: start.ox + dx, y: start.oy + dy },
                  }));
                }}
                onPointerUp={(event) => {
                  const start = nodeDrag.current;
                  nodeDrag.current = null;
                  // A press that did not move is a click, not a drag.
                  if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 4) {
                    event.stopPropagation();
                  }
                }}
                onFocus={() => setHovered(node.id)}
                onBlur={() => setHovered(null)}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(node);
                  if (node.type === "cluster") {
                    onExpand(expandedTopic === node.label ? null : node.label);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-label={`${node.label}, ${node.type}`}
                className="cursor-pointer outline-none transition-opacity duration-200 focus-visible:opacity-100"
              >
                {/* Halo. Only the selected node pulses, so the scene is still
                    unless the user is doing something. */}
                <circle
                  r={radius * 2.6}
                  style={{ fill: outside ? OUTSIDE : `url(#${gradientId(node.id)})` }}
                  opacity={isSelected ? 0.45 : outside ? 0.1 : 0.22}
                  className={isSelected && !answerMap ? "animate-pulse" : undefined}
                />
                {/* Outside the answer, a node keeps its place but loses its
                    colour: it is still knowledge, just not what this answer
                    was built from. */}
                <circle
                  r={radius}
                  style={{ fill: outside ? OUTSIDE : `url(#${gradientId(node.id)})` }}
                />
                <circle
                  r={radius}
                  fill="none"
                  style={{
                    stroke: isSelected || cited ? INK : outside ? OUTSIDE : colorFor(node.category, 78),
                  }}
                  strokeWidth={isSelected || cited ? 1.6 : 0.7}
                  opacity={isSelected || cited ? 0.95 : outside ? 0.35 : 0.5}
                />
                {(node.type === "cluster" || node.id === focus) && (
                  <text
                    y={radius + 13}
                    textAnchor="middle"
                    className="pointer-events-none select-none"
                    style={{
                      fontSize: node.type === "cluster" ? 13 : 9,
                      fontWeight: node.type === "cluster" ? 600 : 400,
                      fill: node.type === "cluster" ? LABEL : LABEL_MUTED,
                    }}
                  >
                    {node.label.length > 34 ? `${node.label.slice(0, 33)}…` : node.label}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {hoveredEdge && <EdgeCard edge={hoveredEdge} graph={graph} />}

      {hoveredNode && hoveredPoint && (
        <HoverCard
          node={hoveredNode}
          x={hoveredPoint.x}
          y={hoveredPoint.y}
          view={view}
          onOpen={() => onSelect(hoveredNode)}
          onKeepOpen={() => setHovered(hoveredNode.id)}
          onDismiss={() => setHovered(null)}
        />
      )}

      {/* Clear of the Ask CEREBRO launcher, which sits in the same corner at
          a higher stacking level and silently swallowed clicks on the lowest
          button here. */}
      <div className="absolute bottom-[4.25rem] right-4 flex flex-col gap-1.5">
        <ViewButton label="Zoom in" onClick={() => zoom(1.25)}>+</ViewButton>
        <ViewButton label="Zoom out" onClick={() => zoom(0.8)}>−</ViewButton>
        <ViewButton label="Rotate anticlockwise" onClick={() => rotate(-15)}>
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M4 10a6 6 0 1 0 2.2-4.65" strokeLinecap="round" />
            <path d="M3.5 3.5v3h3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </ViewButton>
        <ViewButton label="Rotate clockwise" onClick={() => rotate(15)}>
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M16 10a6 6 0 1 1-2.2-4.65" strokeLinecap="round" />
            <path d="M16.5 3.5v3h-3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </ViewButton>
        <ViewButton label="Reset view" onClick={reset}>
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M4 7.5V4h3.5M16 12.5V16h-3.5M16 7.5V4h-3.5M4 12.5V16h3.5" strokeLinecap="round" />
          </svg>
        </ViewButton>
      </div>

      <Legend graph={graph} />

      {/* The what-if lens. Typed text is embedded by the library's own model
          — on the GPU where the local Ollama serves it — and placed among
          the topics. Nothing is stored. */}
      <form
        onSubmit={placeText}
        className="absolute left-1/2 top-3 z-20 flex w-[min(28rem,60%)] -translate-x-1/2 items-center gap-1.5 rounded-full border border-scene-ink/15 bg-scene-raised/90 py-1 pl-3.5 pr-1 shadow-lg backdrop-blur"
      >
        <span aria-hidden="true" className="text-xs text-scene-ink/45">What if…</span>
        <input
          value={lensText}
          onChange={(e) => setLensText(e.target.value)}
          placeholder="type an idea to see where it would land"
          aria-label="Place an idea in your Galaxy"
          maxLength={1000}
          className="min-w-0 flex-1 bg-transparent py-1 text-xs text-scene-ink outline-none placeholder:text-scene-ink/35"
        />
        {lens ? (
          <button
            type="button"
            onClick={() => {
              setLens(null);
              setLensText("");
            }}
            className="rounded-full px-3 py-1 text-xs text-scene-ink/70 hover:text-scene-ink"
          >
            Clear
          </button>
        ) : (
          <button
            type="submit"
            disabled={lensBusy || lensText.trim().length < 2}
            className="rounded-full bg-scene-ink/10 px-3 py-1 text-xs font-medium text-scene-ink transition-colors hover:bg-scene-ink/20 disabled:opacity-40"
          >
            {lensBusy ? "Placing…" : "Place"}
          </button>
        )}
      </form>
      {lensError && (
        <p className="absolute left-1/2 top-14 z-20 -translate-x-1/2 rounded-md bg-scene-raised/95 px-3 py-1.5 text-xs text-rose-400">
          {lensError}
        </p>
      )}
      {lens && <LensCard lens={lens} />}
    </div>
  );
}

/** Similarity edges are measurements; every other kind is an observation. */
function isMeasured(edge: GraphEdge): boolean {
  return edge.kind === "similar_meaning" || edge.kind === "similar_words";
}

function pct(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

/**
 * The lens text, drawn where it would land.
 *
 * It sits at the similarity-weighted middle of the topics it is most alike
 * to, with a dashed line and a figure to each. Text like nothing in the
 * library sits at the centre, alone, which is itself the answer.
 */
function LensMark({
  lens,
  targets,
  positions,
  angle,
}: {
  lens: CerebroLens;
  targets: CerebroLens["topics"];
  positions: Map<string, { x: number; y: number }>;
  angle: number;
}) {
  const points = targets.map((t) => ({ t, p: positions.get(t.id)! }));
  const total = points.reduce((sum, { t }) => sum + t.similarity, 0);
  const at = total
    ? {
        x: points.reduce((sum, { t, p }) => sum + p.x * t.similarity, 0) / total,
        y: points.reduce((sum, { t, p }) => sum + p.y * t.similarity, 0) / total + (points.length === 1 ? 46 : 0),
      }
    : { x: VIEWBOX.width / 2, y: VIEWBOX.height / 2 };
  const label = lens.text.length > 28 ? `${lens.text.slice(0, 27)}…` : lens.text;
  return (
    <g data-testid="lens-mark">
      {points.map(({ t, p }) => (
        <g key={t.id}>
          <line
            x1={at.x}
            y1={at.y}
            x2={p.x}
            y2={p.y}
            style={{ stroke: INK }}
            strokeWidth={0.8 + t.strength * 1.6}
            strokeDasharray="5 4"
            opacity={0.25 + t.strength * 0.55}
          />
          <g transform={`translate(${(at.x + p.x) / 2} ${(at.y + p.y) / 2}) rotate(${-angle})`}>
            <rect x={-15} y={-7} width={30} height={14} rx={7} style={{ fill: "var(--color-scene)", stroke: INK }} strokeWidth={0.6} />
            <text y={3.5} textAnchor="middle" style={{ fontSize: 9, fontWeight: 700, fill: LABEL }}>
              {pct(t.similarity)}
            </text>
          </g>
        </g>
      ))}
      <g transform={`translate(${at.x} ${at.y}) rotate(${-angle})`}>
        <rect x={-7} y={-7} width={14} height={14} transform="rotate(45)" style={{ fill: INK }} opacity={0.9} />
        <text y={22} textAnchor="middle" style={{ fontSize: 11, fontWeight: 600, fill: LABEL }}>
          “{label}”
        </text>
      </g>
    </g>
  );
}

/** What the lens found, in words: the placement, the closest topics, the nearest passages. */
function LensCard({ lens }: { lens: CerebroLens }) {
  const shown = lens.topics.slice(0, 5);
  return (
    <div
      data-testid="lens-card"
      // Top right, clear of the legend on the left and the controls below.
      className="absolute right-3 top-14 z-20 w-72 rounded-lg border border-scene-ink/15 bg-scene-raised/95 p-3 text-xs shadow-xl backdrop-blur"
    >
      <p className="font-medium text-scene-ink">{lens.placement}</p>
      <ul className="mt-2 space-y-1">
        {shown.map((t) => (
          <li key={t.id} className="flex items-center gap-2">
            <span className="w-24 truncate text-scene-ink/75">{t.label}</span>
            <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-scene-ink/10">
              <span
                className="absolute inset-y-0 left-0 rounded-full"
                style={{ width: `${Math.max(2, t.similarity * 100)}%`, background: colorFor(t.label), opacity: t.above_typical ? 0.9 : 0.35 }}
              />
            </span>
            <span className="w-9 text-right tabular-nums text-scene-ink/80">{pct(t.similarity)}</span>
          </li>
        ))}
      </ul>
      {lens.passages.length > 0 && (
        <div className="mt-2 border-t border-scene-ink/10 pt-2">
          <p className="text-[0.625rem] uppercase tracking-wide text-scene-ink/40">Nearest passages</p>
          {lens.passages.map((p) => (
            <p key={p.id} className="mt-1 line-clamp-2 text-[0.6875rem] text-scene-ink/60">
              <span className="text-scene-ink/85">{p.title}</span> · {pct(p.similarity)} — {p.excerpt}
            </p>
          ))}
        </div>
      )}
      <p className="mt-2 border-t border-scene-ink/10 pt-2 text-[0.625rem] text-scene-ink/40">
        Measured with {lens.similarity.model} ({lens.similarity.measures}). A what-if: nothing was
        stored. Your topics typically share {pct(lens.similarity.typical)}.
      </p>
    </div>
  );
}

/** Screen-space delta turned back into layout space. */
function unrotate(dx: number, dy: number, degrees: number): [number, number] {
  const radians = (-degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return [dx * cos - dy * sin, dx * sin + dy * cos];
}

/** Where the pointer sits around the canvas centre, in degrees. */
function angleFromCentre(event: React.PointerEvent<SVGSVGElement>): number {
  const box = event.currentTarget.getBoundingClientRect();
  return (
    (Math.atan2(event.clientY - (box.top + box.height / 2), event.clientX - (box.left + box.width / 2)) *
      180) /
    Math.PI
  );
}

/**
 * The hover preview.
 *
 * Reads only from the node already in memory — no request, and certainly no
 * model call, on hover.
 */
function HoverCard({
  node,
  x,
  y,
  view,
  onOpen,
  onKeepOpen,
  onDismiss,
}: {
  node: GraphNode;
  x: number;
  y: number;
  view: { scale: number; x: number; y: number; angle: number };
  onOpen: () => void;
  onKeepOpen: () => void;
  onDismiss: () => void;
}) {
  // The same transform the canvas group applies, in reverse order of
  // reading: offset by the pan, turned by the angle, scaled about the
  // centre. The card has to follow its node when the galaxy is rotated.
  const radians = (view.angle * Math.PI) / 180;
  const ox = x + view.x - VIEWBOX.width / 2;
  const oy = y + view.y - VIEWBOX.height / 2;
  const rx = ox * Math.cos(radians) - oy * Math.sin(radians);
  const ry = ox * Math.sin(radians) + oy * Math.cos(radians);
  const left = (rx * view.scale + VIEWBOX.width / 2) / VIEWBOX.width;
  const top = (ry * view.scale + VIEWBOX.height / 2) / VIEWBOX.height;

  return (
    <div
      role="tooltip"
      // Reachable rather than inert: the card carries actions, so the pointer
      // has to be able to travel into it without dismissing it.
      onPointerEnter={onKeepOpen}
      onPointerLeave={onDismiss}
      className="absolute z-20 w-64 rounded-lg border border-scene-ink/12 bg-scene-raised/95 p-3 shadow-xl backdrop-blur"
      style={{
        // Kept inside the viewport rather than clipped at an edge.
        left: `${Math.min(62, Math.max(2, left * 100 + 3))}%`,
        top: `${Math.min(62, Math.max(2, top * 100 + 6))}%`,
      }}
    >
      <p className="text-sm font-semibold text-scene-ink">{node.label}</p>
      <p className="mt-0.5 text-[0.6875rem] text-scene-ink/60">
        {node.type === "cluster" ? "Knowledge Cluster" : "Knowledge Fragment"} ·{" "}
        {node.category}
      </p>
      <p className="mt-2 text-[0.6875rem] text-scene-ink/75">
        Found in {node.document_count} document{node.document_count === 1 ? "" : "s"}
        {node.type === "cluster" && (
          <> · {node.fragment_count} fragment{node.fragment_count === 1 ? "" : "s"}</>
        )}
      </p>
      {node.excerpt && (
        <p className="mt-2 line-clamp-3 text-[0.6875rem] leading-relaxed text-scene-ink/60">
          {node.excerpt}
        </p>
      )}
      {node.source_filename && (
        <p className="mt-2 border-t border-scene-ink/10 pt-2 text-[0.625rem] text-scene-ink/50">
          Source: {node.source_filename}
          {node.source_location?.page ? ` · page ${node.source_location.page}` : ""}
        </p>
      )}
      <div className="mt-2.5 flex flex-wrap gap-2 border-t border-scene-ink/10 pt-2.5">
        <button
          type="button"
          onClick={onOpen}
          className="rounded-md bg-scene-ink/10 px-2 py-1 text-[0.6875rem] font-medium text-scene-ink transition-colors hover:bg-scene-ink/20"
        >
          Explore
        </button>
        {node.source_artifact_id && (
          <a
            href={api.artifactContentUrl(node.source_artifact_id)}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md bg-scene-ink/10 px-2 py-1 text-[0.6875rem] font-medium text-sky-300 transition-colors hover:bg-scene-ink/20"
          >
            Open source
          </a>
        )}
      </div>
    </div>
  );
}

/**
 * How to read the Galaxy, pinned to the left.
 *
 * Each entry is a small drawing of the mark it explains, and the figures in
 * it are this library's own: the model that measured similarity, the
 * similarity two topics typically share, the strongest pair, how many links
 * were discovered. They change as the library does, which is the point — a
 * legend with fixed numbers would describe somebody else's galaxy.
 *
 * Collapsible, and inert apart from its toggle, so it never steals a gesture
 * from the nodes beneath it.
 */
function Legend({ graph }: { graph: CerebroGalaxy }) {
  const [open, setOpen] = useState(true);
  const space: SimilaritySpace | null | undefined = graph.similarity;
  const discovered = graph.edges.filter((e) => e.discovered).length;
  // Counted the way they are drawn: only a clear resemblance moves a passage out.
  const fragments = graph.nodes.filter((n) => n.type === "fragment");
  const leaning = fragments.filter((n) => reachOf(n, graph.edges)).length;
  const orbiting = fragments.length - leaning;
  return (
    <div
      data-testid="galaxy-legend"
      className="pointer-events-none absolute left-3 top-3 z-10 w-56 rounded-lg border border-scene-ink/10 bg-scene-raised/85 text-[0.6875rem] text-scene-ink/70 shadow-lg backdrop-blur"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="pointer-events-auto flex w-full items-center justify-between px-3 py-2 text-left font-semibold text-scene-ink/85"
      >
        Reading the Galaxy
        <span aria-hidden="true" className="text-scene-ink/40">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-scene-ink/10 px-3 pb-3 pt-2">
          <LegendRow
            mark={
              <svg viewBox="0 0 36 16" className="h-4 w-9" aria-hidden="true">
                <circle cx="7" cy="8" r="3.5" style={{ fill: LABEL_MUTED }} />
                <circle cx="24" cy="8" r="7" style={{ fill: LABEL }} opacity={0.8} />
              </svg>
            }
          >
            Size — documents behind a topic
          </LegendRow>
          <LegendRow
            mark={
              <svg viewBox="0 0 36 16" className="h-4 w-9" aria-hidden="true">
                <line x1="2" y1="8" x2="34" y2="8" style={{ stroke: LABEL }} strokeWidth="1.8" opacity={0.6} />
              </svg>
            }
          >
            Topics on the same document
          </LegendRow>
          {space && (
            <>
              <LegendRow
                mark={
                  <svg viewBox="0 0 36 16" className="h-4 w-9" aria-hidden="true">
                    <line x1="2" y1="3" x2="34" y2="3" style={{ stroke: LABEL }} strokeWidth="0.7" opacity={0.18} />
                    <line x1="2" y1="8" x2="34" y2="8" style={{ stroke: LABEL }} strokeWidth="1.4" opacity={0.45} />
                    <line x1="2" y1="13" x2="34" y2="13" style={{ stroke: LABEL }} strokeWidth="2.4" opacity={0.85} />
                  </svg>
                }
              >
                Alike in {space.measures} — fainter is weaker.{" "}
                <span className="text-scene-ink/50">
                  {pct(space.typical)} is typical here, {pct(space.ceiling)} the strongest pair
                </span>
              </LegendRow>
              <LegendRow
                mark={
                  <svg viewBox="0 0 36 16" className="h-4 w-9" aria-hidden="true">
                    <line x1="2" y1="8" x2="34" y2="8" style={{ stroke: LABEL }} strokeWidth="1.6" strokeDasharray="1.5 3.5" strokeLinecap="round" />
                  </svg>
                }
              >
                Discovered — alike, but never on one document
                {discovered > 0 && <span className="text-scene-ink/50"> · {discovered} found</span>}
              </LegendRow>
              <LegendRow
                mark={
                  <svg viewBox="0 0 36 16" className="h-4 w-9" aria-hidden="true">
                    <rect x="4" y="2" width="28" height="12" rx="6" style={{ fill: "var(--color-scene)", stroke: LABEL_MUTED }} strokeWidth="0.6" />
                    <text x="18" y="11" textAnchor="middle" style={{ fontSize: 7.5, fontWeight: 600, fill: LABEL }}>62%</text>
                  </svg>
                }
              >
                Similarity, measured — hover a line for why
              </LegendRow>
              <LegendRow
                mark={
                  <svg viewBox="0 0 36 16" className="h-4 w-9" aria-hidden="true">
                    <circle cx="18" cy="8" r="4.5" style={{ fill: LABEL }} opacity={0.7} />
                    <circle cx="18" cy="8" r="7" fill="none" style={{ stroke: LABEL_MUTED }} strokeWidth="0.5" strokeDasharray="1 2" />
                    <circle cx="25" cy="8" r="1.6" style={{ fill: LABEL }} />
                  </svg>
                }
              >
                Passage like nothing else orbits its topic
                {orbiting + leaning > 0 && (
                  <span className="text-scene-ink/50"> · {leaning} reach out, {orbiting} orbit</span>
                )}
              </LegendRow>
            </>
          )}
          <p className="border-t border-scene-ink/10 pt-2 text-[0.625rem] leading-relaxed text-scene-ink/45">
            {space ? (
              <>
                Measured with {space.model}
                {space.learned ? "" : " — shared words, not meaning; connect a local model for meaning"} over{" "}
                {space.vectors.toLocaleString()} passages. Alike is not related: these are resemblances in the text.
              </>
            ) : (
              "Similarity appears once passages have embeddings."
            )}
          </p>
          <p className="text-[0.625rem] text-scene-ink/35">Drag to move · shift-drag to rotate</p>
        </div>
      )}
    </div>
  );
}

function LegendRow({ mark, children }: { mark: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 shrink-0">{mark}</span>
      <span className="leading-snug">{children}</span>
    </div>
  );
}

function ViewButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="grid size-8 place-items-center rounded-md border border-scene-ink/12 bg-scene-raised/85 text-sm text-scene-ink/80 backdrop-blur transition-colors hover:bg-scene-hover"
    >
      {children}
    </button>
  );
}

/** SVG ids must be valid and unique; node ids contain colons and spaces. */
function gradientId(id: string): string {
  return `g-${id.replace(/[^a-zA-Z0-9]/g, "-")}`;
}

/**
 * Why two nodes are connected.
 *
 * Every field here is something CEREBRO observed, and the wording is chosen
 * so none of it reads as more than that. The relationship is named for what
 * was seen — two topics in the same registered document, or a confirmed
 * entity named in one — never for what it might mean: co-occurrence cannot
 * establish that one thing *uses* or *depends on* another, and an edge
 * labelled that way would be a claim with no evidence behind it.
 *
 * Confidence is a count of supporting documents, written as a count. An
 * unexplained percentage would imply a model weighed this; none did.
 */
function EdgeCard({ edge, graph }: { edge: GraphEdge; graph: CerebroGalaxy }) {
  const label = (id: string) => graph.nodes.find((n) => n.id === id)?.label ?? id;
  const measured = isMeasured(edge);
  return (
    <div
      role="tooltip"
      data-testid="edge-card"
      // Bottom centre: the legend holds the top left, the lens card the top right.
      className="pointer-events-none absolute bottom-4 left-1/2 z-30 w-80 -translate-x-1/2 rounded-lg border border-scene-ink/15 bg-scene-overlay/97 p-3 text-xs shadow-2xl"
    >
      <Field label="Relationship">
        {RELATIONSHIP[edge.kind] ?? edge.kind}
        {edge.discovered ? " · discovered" : ""}
      </Field>
      <Field label="Source">{label(edge.source)}</Field>
      <Field label="Target">{label(edge.target)}</Field>
      {typeof edge.similarity === "number" && (
        <Field label="Similarity">
          <span className="font-semibold">{pct(edge.similarity)}</span>
          {measured && edge.relevance ? ` · ${edge.relevance.toLowerCase()}` : ""}
        </Field>
      )}
      {typeof edge.strength === "number" && (
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-scene-ink/10" aria-hidden="true">
          <div className="h-full rounded-full bg-scene-ink/60" style={{ width: `${Math.max(3, edge.strength * 100)}%` }} />
        </div>
      )}
      <p className="mt-2 border-t border-scene-ink/10 pt-2 text-scene-ink/70">{edge.explanation}</p>
      {edge.evidence.length > 0 && (
        <p className="mt-1.5 text-[0.6875rem] text-scene-ink/45">
          From {edge.evidence.join(", ")}
          {edge.evidence_count > edge.evidence.length
            ? ` and ${edge.evidence_count - edge.evidence.length} more`
            : ""}
        </p>
      )}
      <div className="mt-2 flex items-center justify-between border-t border-scene-ink/10 pt-2 text-[0.6875rem] text-scene-ink/45">
        <span>{edge.confidence}</span>
        <span>{edge.status === "registered" ? "Approved knowledge" : edge.status}</span>
      </div>
    </div>
  );
}

/** Observational names. Nothing here asserts what a relationship means. */
const RELATIONSHIP: Record<string, string> = {
  co_occurrence: "Appears in the same document",
  named_in: "Named in documents about",
  contains: "Fragment of",
  similar_meaning: "Alike in meaning",
  similar_words: "Shares wording",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[0.6875rem] text-scene-ink/40">{label}</span>
      <span className="text-right text-[0.75rem] text-scene-ink/85">{children}</span>
    </div>
  );
}
