"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { layout, reachOf, VIEWBOX } from "@/components/galaxy/layout";
import { colorFor, hueFor } from "@/components/galaxy/palette";
import { api } from "@/lib/api";
import { useGalaxyLayout } from "@/lib/galaxyLayoutState";
import { createPersistedStore } from "@/lib/persistedStore";
import { noteColour, useStickyNotes } from "@/lib/stickyNotes";
import type { StickyNote } from "@/lib/stickyNotes";

/** How the reader likes the Galaxy drawn. Per browser; nothing about the library. */
export const useGalaxySettings = createPersistedStore("cerebro-galaxy-settings", {
  /** Percentages on the lines. */
  showFigures: true,
  /** Links between topics no document carries together. */
  showDiscovered: true,
  /** Resemblances only just above typical, drawn faint. */
  showWeakLinks: true,
  /** 0.6–2.5: how strongly lines are drawn. Light canvases want more. */
  lineContrast: 1,
  /** Keep the map dark even when the app is light. */
  darkCanvas: false,
  /** The soft halo around each node. */
  glow: true,
  labelSize: "M" as "S" | "M" | "L",
});
const LABEL_SCALE = { S: 0.85, M: 1, L: 1.2 } as const;
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
  /** Where a typed idea would land, placed by the page's what-if bar. */
  lens?: CerebroLens | null;
  onClearLens?: () => void;
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
  lens = null,
  onClearLens,
}: GalaxyCanvasProps) {
  const [view, setView] = useState({ scale: 1, x: 0, y: 0, angle: 0 });
  const [hovered, setHovered] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<GraphEdge | null>(null);
  // Hovering the placed idea opens its details, even when the window is folded.
  const [lensPeek, setLensPeek] = useState(false);
  const [settings, setSettings] = useGalaxySettings();
  const stickies = useStickyNotes();
  const [settingsOpen, setSettingsOpen] = useState(false);
  // A node the user pinned: its window stays after the pointer leaves.
  const [pinned, setPinned] = useState<string | null>(null);
  const contrast = settings.lineContrast;
  const labelScale = LABEL_SCALE[settings.labelSize] ?? 1;
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
  // A drag ends with a click on the same node. Without this, dragging an
  // opened topic also closed it, and its passages vanished mid-move.
  const justDragged = useRef(false);

  const positions = useMemo(() => {
    const base = layout(graph.nodes, expandedTopic, graph.edges);
    // An opened topic carries its passages with it when dragged, so they stay
    // readable as its own. A passage the user dragged separately stays where
    // they put it.
    const parentId = expandedTopic ? `topic:${expandedTopic}` : null;
    const parent = parentId ? base.get(parentId) : undefined;
    const carried = parentId && parent && moved[parentId];
    const dx = carried ? moved[parentId].x - parent.x : 0;
    const dy = carried ? moved[parentId].y - parent.y : 0;
    if (dx || dy) {
      for (const [id, point] of base) {
        if (point.node.type === "fragment" && !moved[id]) {
          base.set(id, { ...point, x: point.x + dx, y: point.y + dy });
        }
      }
    }
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

  return (
    <div className={cn("relative size-full overflow-hidden bg-scene", settings.darkCanvas && "scene-dark")} data-canvas-frame>
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
            // One rule for every line between two topics, or a passage and
            // another topic: thickness and brightness follow the measured
            // similarity, solid means they share a document, dotted that
            // they were discovered alike, and each carries its figure.
            // Containment — a passage to its own topic — is structure, and
            // keeps a plain line.
            const contained = edge.kind === "contains";
            const scored = !contained && typeof edge.similarity === "number" && edge.strength != null;
            if (edge.discovered && !settings.showDiscovered) return null;
            if (measured && strength < 0.33 && !settings.showWeakLinks && !touches) return null;
            // Progressive disclosure, but only where there is something to
            // disclose progressively: a weak edge is hidden when stronger
            // ones exist, and shown anyway when they do not. Either way it
            // reappears when one of its endpoints is in focus, which is when
            // the user is asking about that node specifically. A measured
            // edge is never hidden: a weak resemblance is drawn faint instead,
            // which is what makes it a weak one.
            if (!measured && !scored && !edge.strong && hasStrongEdges && !touches) return null;
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
            const showFigure = scored && settings.showFigures && lit;
            const baseOpacity = scored
              ? lit
                ? 0.22 + strength * 0.6
                : 0.05
              : lit
                ? edge.strong
                  ? 0.55
                  : 0.3
                : 0.08;
            const baseWidth = scored ? 0.6 + strength * 1.8 : 0.6 + Math.min(edge.weight, 4) * 0.45;
            return (
              <g key={edge.id}>
                <path
                  d={path}
                  fill="none"
                  stroke={`url(#${gradientId(edge.id)})`}
                  strokeWidth={baseWidth * (0.7 + 0.3 * contrast)}
                  opacity={Math.min(1, baseOpacity * contrast)}
                  strokeDasharray={
                    edge.discovered ? "1.5 3.5" : scored || contained || edge.strong ? undefined : "4 3"
                  }
                  strokeLinecap="round"
                  data-kind={edge.kind}
                  data-strength={scored ? strength : undefined}
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
                    justDragged.current = true;
                  }
                }}
                onFocus={() => setHovered(node.id)}
                onBlur={() => setHovered(null)}
                onClick={(event) => {
                  event.stopPropagation();
                  if (justDragged.current) {
                    justDragged.current = false;
                    return;
                  }
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
                  opacity={settings.glow ? (isSelected ? 0.45 : outside ? 0.1 : 0.22) : 0}
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
                      fontSize: (node.type === "cluster" ? 13 : 9) * labelScale,
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
          {/* Sticky notes from Ask CEREBRO: each points at its document's
              passage when that topic is open, at its topic otherwise. */}
          {(() => {
            const stacked = new Map<string, number>();
            return stickies.notes.map((note) => {
              const anchor =
                (note.fragmentId && positions.get(`fragment:${note.fragmentId}`)) ||
                (note.topic && positions.get(`topic:${note.topic}`)) ||
                null;
              if (!anchor) return null;
              const key = `${anchor.x},${anchor.y}`;
              const stack = stacked.get(key) ?? 0;
              stacked.set(key, stack + 1);
              return (
                <StickyFlag
                  key={note.id}
                  note={note}
                  at={anchor}
                  angle={view.angle}
                  stack={stack}
                  onClose={() => stickies.remove(note.id)}
                />
              );
            });
          })()}

          {/* Drawn last, above the topics, so the idea can always be hovered
              even when it lands right on top of one. */}
          {lens && (
            <LensMark
              lens={lens}
              targets={lensTargets}
              positions={positions}
              angle={view.angle}
              onPeek={setLensPeek}
            />
          )}
        </g>
      </svg>

      {hoveredEdge && <EdgeCard edge={hoveredEdge} graph={graph} />}

      <NodeWindow
        node={(hoveredNode ?? (pinned ? positions.get(pinned)?.node : undefined)) ?? null}
        pinned={Boolean(pinned) && (!hoveredNode || hoveredNode.id === pinned)}
        onPin={(id) => setPinned(id)}
        onOpen={(node) => onSelect(node)}
        onKeepOpen={(id) => setHovered(id)}
        onDismiss={() => setHovered(null)}
      />

      {/* Clear of the Ask CEREBRO launcher, which sits in the same corner at
          a higher stacking level and silently swallowed clicks on the lowest
          button here. */}
      <div className="absolute bottom-[4.25rem] right-4 flex flex-col gap-1.5">
        <ViewButton label="Galaxy settings" onClick={() => setSettingsOpen((v) => !v)}>
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M4 6h8M15 6h1M4 14h2M9 14h7" strokeLinecap="round" />
            <circle cx="13.5" cy="6" r="1.6" />
            <circle cx="7.5" cy="14" r="1.6" />
          </svg>
        </ViewButton>
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

      {/* Notes with nowhere to point — their topic is not one of the clusters
          drawn — are listed rather than silently dropped. */}
      {stickies.notes.some(
        (n) => !(n.fragmentId && positions.has(`fragment:${n.fragmentId}`)) && !(n.topic && positions.has(`topic:${n.topic}`)),
      ) && (
        <div className="absolute bottom-4 left-4 z-20 flex max-w-xs flex-col gap-1">
          {stickies.notes
            .filter(
              (n) => !(n.fragmentId && positions.has(`fragment:${n.fragmentId}`)) && !(n.topic && positions.has(`topic:${n.topic}`)),
            )
            .map((n) => (
              <span
                key={n.id}
                data-testid="sticky-note-tray"
                style={{ background: `color-mix(in srgb, ${noteColour(n.colour)} 55%, transparent)` }}
                className="flex items-center gap-1.5 rounded px-2 py-1 text-[0.6875rem] text-scene-ink"
              >
                <button type="button" aria-label={`Close note ${n.title}`} onClick={() => stickies.remove(n.id)} className="font-bold">
                  ×
                </button>
                <span className="truncate">{n.title}</span>
                <span className="text-scene-ink/60">· topic not on the map</span>
              </span>
            ))}
        </div>
      )}

      {settingsOpen && (
        <SettingsPanel settings={settings} onChange={setSettings} onClose={() => setSettingsOpen(false)} />
      )}

      <Legend graph={graph} />

      {lens && <LensCard lens={lens} peek={lensPeek} onClose={() => onClearLens?.()} />}
    </div>
  );
}

/**
 * An arrow-shaped sticky note on the map: translucent, in the result's
 * colour, with the document's title, its point at the node's edge. Notes on
 * the same node stack upwards. The × closes it; otherwise it stays for the
 * session.
 */
function StickyFlag({
  note,
  at,
  angle,
  stack,
  onClose,
}: {
  note: StickyNote;
  at: { x: number; y: number; radius: number };
  angle: number;
  stack: number;
  onClose: () => void;
}) {
  const colour = noteColour(note.colour);
  const label = note.title.length > 26 ? `${note.title.slice(0, 25)}…` : note.title;
  return (
    <g
      transform={`translate(${at.x} ${at.y}) rotate(${-angle})`}
      data-testid="sticky-note"
      data-note={note.id}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <g transform={`translate(${-at.radius - 3} ${-6 - stack * 25})`}>
        <path
          d="M0,0 L-13,-10.5 L-172,-10.5 L-172,10.5 L-13,10.5 Z"
          style={{ fill: colour, stroke: colour }}
          fillOpacity={0.55}
          strokeOpacity={0.95}
          strokeWidth={1}
        />
        <text x={-152} y={3.5} style={{ fontSize: 10, fontWeight: 600, fill: INK }} className="pointer-events-none select-none">
          {label}
        </text>
        <g
          transform="translate(-163 0)"
          role="button"
          tabIndex={0}
          aria-label={`Close note ${note.title}`}
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onClose();
          }}
          className="cursor-pointer"
        >
          <circle r={7} fill="transparent" />
          <text y={3.5} textAnchor="middle" style={{ fontSize: 11, fontWeight: 700, fill: INK }}>
            ×
          </text>
        </g>
      </g>
    </g>
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
  onPeek,
}: {
  lens: CerebroLens;
  targets: CerebroLens["topics"];
  positions: Map<string, { x: number; y: number }>;
  angle: number;
  onPeek: (open: boolean) => void;
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
      <g
        transform={`translate(${at.x} ${at.y}) rotate(${-angle})`}
        onPointerEnter={() => onPeek(true)}
        onPointerLeave={() => onPeek(false)}
        data-testid="lens-node"
        className="cursor-help"
      >
        {/* A wider target than the diamond, so hovering it is easy. */}
        <circle r={16} fill="transparent" />
        <rect x={-7} y={-7} width={14} height={14} transform="rotate(45)" style={{ fill: INK }} opacity={0.9} />
        <text y={22} textAnchor="middle" style={{ fontSize: 11, fontWeight: 600, fill: LABEL }}>
          “{label}”
        </text>
      </g>
    </g>
  );
}

/**
 * Drag a floating window by its header, inside the canvas.
 *
 * A press that does not move is left alone, so the header's own buttons
 * still work; only a real drag moves the window.
 */
function useWindowDrag(
  x: number,
  y: number,
  onMove: (x: number, y: number) => void,
): (event: React.PointerEvent<HTMLElement>) => void {
  return (event) => {
    if ((event.target as Element).closest("button")) return;
    const box = (event.currentTarget.closest("[data-floating]") as HTMLElement | null)?.getBoundingClientRect();
    const frame = (event.currentTarget.closest("[data-canvas-frame]") as HTMLElement | null)?.getBoundingClientRect();
    if (!box || !frame) return;
    event.preventDefault();
    const start = { px: event.clientX, py: event.clientY, x, y };
    const move = (e: PointerEvent) => {
      const nx = start.x + e.clientX - start.px;
      const ny = start.y + e.clientY - start.py;
      // Kept inside the canvas, with its header always reachable.
      onMove(
        Math.round(Math.min(Math.max(0, nx), frame.width - box.width)),
        Math.round(Math.min(Math.max(0, ny), frame.height - 32)),
      );
    };
    const stop = () => {
      globalThis.removeEventListener("pointermove", move);
      globalThis.removeEventListener("pointerup", stop);
    };
    globalThis.addEventListener("pointermove", move);
    globalThis.addEventListener("pointerup", stop);
  };
}

/**
 * A floating window on the canvas, shared by the what-if results and node
 * details so the two look and behave the same: a header that drags it, a
 * button that folds it to a tab on the left edge, and a peek — what it
 * describes being hovered — that opens it while folded.
 */
function FloatingWindow({
  testId,
  tabLabel,
  tabTop,
  title,
  minimized,
  onMinimize,
  x,
  y,
  onMove,
  show,
  role,
  headerExtra,
  onClose,
  onPointerEnter,
  onPointerLeave,
  children,
}: {
  testId: string;
  tabLabel: string;
  /** Where its tab sits on the left edge, as a percentage of the canvas height. */
  tabTop: number;
  title: React.ReactNode;
  minimized: boolean;
  onMinimize: (minimized: boolean) => void;
  /** x below zero docks it to the right edge. */
  x: number;
  y: number;
  onMove: (x: number, y: number) => void;
  /** Whether there is something to show right now (open, or peeked). */
  show: boolean;
  role?: string;
  headerExtra?: React.ReactNode;
  onClose?: () => void;
  onPointerEnter?: () => void;
  onPointerLeave?: () => void;
  children: React.ReactNode;
}) {
  const [hoverTab, setHoverTab] = useState(false);
  const startDrag = useWindowDrag(Math.max(0, x), y, onMove);
  const open = show || (minimized && hoverTab);

  return (
    <>
      {minimized && (
        <button
          type="button"
          data-testid={`${testId}-tab`}
          onClick={() => onMinimize(false)}
          onPointerEnter={() => setHoverTab(true)}
          onPointerLeave={() => setHoverTab(false)}
          style={{ top: `${tabTop}%` }}
          className="absolute left-0 z-20 -translate-y-1/2 rounded-r-lg border border-l-0 border-scene-ink/15 bg-scene-raised/95 px-1.5 py-3 text-[0.6875rem] font-medium text-scene-ink/80 shadow-lg [writing-mode:vertical-rl] hover:text-scene-ink"
        >
          {tabLabel} ◂
        </button>
      )}
      {open && (
        <div
          data-floating
          data-testid={testId}
          role={role}
          className="absolute z-30 w-72 rounded-lg border border-scene-ink/15 bg-scene-raised/95 text-xs shadow-xl backdrop-blur"
          style={
            minimized
              ? { left: 40, top: `${tabTop}%`, transform: "translateY(-50%)" }
              : x < 0
                ? { right: 12, top: y }
                : { left: x, top: y }
          }
          onPointerEnter={() => {
            if (minimized) setHoverTab(true);
            onPointerEnter?.();
          }}
          onPointerLeave={() => {
            setHoverTab(false);
            onPointerLeave?.();
          }}
        >
          <div
            onPointerDown={minimized ? undefined : startDrag}
            className={cn(
              "flex items-center justify-between gap-2 border-b border-scene-ink/10 px-3 py-1.5",
              !minimized && "cursor-move",
            )}
          >
            <span className="min-w-0 truncate font-semibold text-scene-ink/85">{title}</span>
            <span className="flex shrink-0 items-center">
              {headerExtra}
              <button
                type="button"
                aria-label={minimized ? `Keep the ${tabLabel.toLowerCase()} window open` : `Minimise the ${tabLabel.toLowerCase()} window`}
                onClick={() => {
                  onMinimize(!minimized);
                  setHoverTab(false);
                }}
                className="rounded px-1.5 text-scene-ink/50 hover:text-scene-ink"
              >
                {minimized ? "▸" : "−"}
              </button>
              {onClose && (
                <button
                  type="button"
                  aria-label={`Close the ${tabLabel.toLowerCase()} window`}
                  onClick={onClose}
                  className="rounded px-1.5 text-scene-ink/50 hover:text-scene-ink"
                >
                  ✕
                </button>
              )}
            </span>
          </div>
          <div className="p-3">{children}</div>
        </div>
      )}
    </>
  );
}

/** What the lens found: the placement, the closest topics, the nearest passages. */
function LensCard({ lens, peek, onClose }: { lens: CerebroLens; peek: boolean; onClose: () => void }) {
  const [layout, arrange] = useGalaxyLayout();
  const shown = lens.topics.slice(0, 5);
  return (
    <FloatingWindow
      testId="lens-card"
      tabLabel="What if"
      tabTop={40}
      title={<>What if “{lens.text}”</>}
      minimized={layout.lensMinimized}
      onMinimize={(lensMinimized) => arrange({ lensMinimized })}
      x={layout.lensX}
      y={layout.lensY}
      onMove={(lensX, lensY) => arrange({ lensX, lensY })}
      show={!layout.lensMinimized || peek}
      onClose={onClose}
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
    </FloatingWindow>
  );
}

/**
 * A node's details, in the same window as the what-if results.
 *
 * Opens while a node is hovered, reading only what is already in memory — no
 * request, and certainly no model call, on hover. The pointer can travel into
 * it without it closing, and the pin keeps it after the pointer leaves.
 */
function NodeWindow({
  node,
  pinned,
  onPin,
  onOpen,
  onKeepOpen,
  onDismiss,
}: {
  node: GraphNode | null;
  pinned: boolean;
  onPin: (id: string | null) => void;
  onOpen: (node: GraphNode) => void;
  onKeepOpen: (id: string) => void;
  onDismiss: () => void;
}) {
  const [layout, arrange] = useGalaxyLayout();
  if (!node && !layout.nodeMinimized) return null;
  return (
    <FloatingWindow
      testId="node-window"
      role="tooltip"
      tabLabel="Details"
      tabTop={62}
      title={node?.label ?? "Details"}
      minimized={layout.nodeMinimized}
      onMinimize={(nodeMinimized) => arrange({ nodeMinimized })}
      x={layout.nodeX}
      y={layout.nodeY}
      onMove={(nodeX, nodeY) => arrange({ nodeX, nodeY })}
      show={Boolean(node)}
      onPointerEnter={() => node && onKeepOpen(node.id)}
      onPointerLeave={onDismiss}
      headerExtra={
        node && (
          <button
            type="button"
            aria-label={pinned ? "Unpin these details" : "Pin these details"}
            aria-pressed={pinned}
            onClick={() => onPin(pinned ? null : node.id)}
            className={cn("rounded px-1.5", pinned ? "text-scene-ink" : "text-scene-ink/50 hover:text-scene-ink")}
          >
            {pinned ? "●" : "○"}
          </button>
        )
      }
      onClose={pinned ? () => onPin(null) : undefined}
    >
      {node && (
        <>
          <p className="text-[0.6875rem] text-scene-ink/60">
            {node.type === "cluster" ? "Knowledge Cluster" : "Knowledge Fragment"} · {node.category}
          </p>
          <p className="mt-2 text-[0.6875rem] text-scene-ink/75">
            Found in {node.document_count} document{node.document_count === 1 ? "" : "s"}
            {node.type === "cluster" && (
              <> · {node.fragment_count} fragment{node.fragment_count === 1 ? "" : "s"}</>
            )}
            {node.type === "fragment" && typeof node.similarity === "number" && (
              <> · {pct(node.similarity)} alike to its topic</>
            )}
          </p>
          {node.excerpt && (
            <p className="mt-2 line-clamp-4 text-[0.6875rem] leading-relaxed text-scene-ink/60">{node.excerpt}</p>
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
              onClick={() => onOpen(node)}
              className="rounded-md bg-scene-ink/10 px-2 py-1 text-[0.6875rem] font-medium text-scene-ink transition-colors hover:bg-scene-ink/20"
            >
              Explore
            </button>
            {node.source_artifact_id && (
              <a
                href={api.artifactContentUrl(node.source_artifact_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-md bg-scene-ink/10 px-2 py-1 text-[0.6875rem] font-medium text-scene-ink transition-colors hover:bg-scene-ink/20"
              >
                Open source
              </a>
            )}
          </div>
        </>
      )}
    </FloatingWindow>
  );
}

/** How the reader likes the Galaxy drawn: labels, line contrast, canvas, glow. */
function SettingsPanel({
  settings,
  onChange,
  onClose,
}: {
  settings: ReturnType<typeof useGalaxySettings>[0];
  onChange: ReturnType<typeof useGalaxySettings>[1];
  onClose: () => void;
}) {
  const toggles: [keyof typeof settings, string, string][] = [
    ["showFigures", "Similarity figures", "Percentages on the lines"],
    ["showDiscovered", "Discovered links", "Topics alike but never on one document"],
    ["showWeakLinks", "Weak resemblances", "Lines only just above typical"],
    ["glow", "Node glow", "The halo around each node"],
    ["darkCanvas", "Always-dark canvas", "Keep the map dark in light mode"],
  ];
  return (
    <div
      data-testid="galaxy-settings"
      className="absolute bottom-[4.25rem] right-14 z-30 w-64 rounded-lg border border-scene-ink/15 bg-scene-raised/95 p-3 text-xs text-scene-ink shadow-xl backdrop-blur"
    >
      <div className="mb-2 flex items-center justify-between">
        <p className="font-semibold">Galaxy settings</p>
        <button type="button" aria-label="Close Galaxy settings" onClick={onClose} className="rounded px-1 text-scene-ink/50 hover:text-scene-ink">
          ✕
        </button>
      </div>
      <label className="block">
        <span className="flex justify-between text-scene-ink/80">
          Line contrast <span className="tabular-nums text-scene-ink/50">{Math.round(settings.lineContrast * 100)}%</span>
        </span>
        <input
          type="range"
          min={0.6}
          max={2.5}
          step={0.1}
          value={settings.lineContrast}
          onChange={(e) => onChange({ lineContrast: Number(e.target.value) })}
          aria-label="Line contrast"
          className="mt-1 w-full accent-[var(--color-accent)]"
        />
      </label>
      <div className="mt-2 space-y-1.5">
        {toggles.map(([key, label, hint]) => (
          <label key={key} className="flex cursor-pointer items-start gap-2">
            <input
              type="checkbox"
              checked={Boolean(settings[key])}
              onChange={(e) => onChange({ [key]: e.target.checked })}
              className="mt-0.5 accent-[var(--color-accent)]"
            />
            <span>
              <span className="block text-scene-ink/85">{label}</span>
              <span className="block text-[0.625rem] text-scene-ink/45">{hint}</span>
            </span>
          </label>
        ))}
      </div>
      <div className="mt-2.5 flex items-center justify-between border-t border-scene-ink/10 pt-2.5">
        <span className="text-scene-ink/80">Label size</span>
        <span className="flex gap-1" role="group" aria-label="Label size">
          {(["S", "M", "L"] as const).map((size) => (
            <button
              key={size}
              type="button"
              aria-pressed={settings.labelSize === size}
              onClick={() => onChange({ labelSize: size })}
              className={cn(
                "size-6 rounded border text-[0.6875rem]",
                settings.labelSize === size ? "border-scene-ink/60 text-scene-ink" : "border-scene-ink/15 text-scene-ink/50",
              )}
            >
              {size}
            </button>
          ))}
        </span>
      </div>
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
  const [layout, arrange] = useGalaxyLayout();
  const open = layout.legendOpen;
  const startDrag = useWindowDrag(layout.legendX, layout.legendY, (x, y) => arrange({ legendX: x, legendY: y }));
  const space: SimilaritySpace | null | undefined = graph.similarity;
  const discovered = graph.edges.filter((e) => e.discovered).length;
  // Counted the way they are drawn: only a clear resemblance moves a passage out.
  const fragments = graph.nodes.filter((n) => n.type === "fragment");
  const leaning = fragments.filter((n) => reachOf(n, graph.edges)).length;
  const orbiting = fragments.length - leaning;
  return (
    <div
      data-testid="galaxy-legend"
      data-floating
      style={{ left: layout.legendX, top: layout.legendY }}
      className="pointer-events-none absolute z-10 w-56 rounded-lg border border-scene-ink/10 bg-scene-raised/85 text-[0.6875rem] text-scene-ink/70 shadow-lg backdrop-blur"
    >
      {/* The header moves it; the button folds it. */}
      <div
        onPointerDown={startDrag}
        className="pointer-events-auto flex cursor-move items-center gap-1 pl-2.5 pr-1"
        title="Drag to move"
      >
        <span aria-hidden="true" className="text-scene-ink/30">⠿</span>
        <button
          type="button"
          onClick={() => arrange({ legendOpen: !open })}
          aria-expanded={open}
          className="flex flex-1 items-center justify-between py-2 pl-1 pr-2 text-left font-semibold text-scene-ink/85"
        >
          Reading the Galaxy
          <span aria-hidden="true" className="text-scene-ink/40">{open ? "−" : "+"}</span>
        </button>
      </div>
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
