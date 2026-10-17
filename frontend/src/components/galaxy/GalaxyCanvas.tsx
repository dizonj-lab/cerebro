"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { layout, VIEWBOX } from "@/components/galaxy/layout";
import { colorFor, hueFor } from "@/components/galaxy/palette";
import { api } from "@/lib/api";
import type { CerebroGalaxy, GraphNode } from "@/lib/api";
import { cn } from "@/lib/cn";

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
    const base = layout(graph.nodes, expandedTopic);
    for (const [id, point] of Object.entries(moved)) {
      const existing = base.get(id);
      if (existing) base.set(id, { ...existing, ...point });
    }
    return base;
  }, [graph.nodes, expandedTopic, moved]);

  // What is "in focus" decides what stays bright and what dims. Hover is a
  // preview; selection persists.
  const focus = hovered ?? selectedId;
  const connected = useMemo(() => {
    // A mapped answer takes over the dimming: the map is the point, and
    // hovering should not wash it away.
    if (answerMap) return new Set([...answerMap.cited, ...answerMap.retrieved]);
    if (!focus) return null;
    const set = new Set<string>([focus]);
    for (const edge of graph.edges) {
      if (edge.source === focus) set.add(edge.target);
      if (edge.target === focus) set.add(edge.source);
    }
    return set;
  }, [focus, graph.edges, answerMap]);

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
    <div className="relative size-full overflow-hidden bg-[#070b14]">
      {/* A still backdrop rather than an animated starfield: atmosphere
          without a compositing loop running behind every interaction. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          background:
            "radial-gradient(60% 55% at 50% 45%, rgba(56,110,190,0.22), transparent 70%)," +
            "radial-gradient(40% 40% at 18% 70%, rgba(24,150,130,0.16), transparent 70%)," +
            "radial-gradient(35% 40% at 82% 28%, rgba(140,90,210,0.16), transparent 70%)",
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
            const lit = !connected || connected.has(edge.source) || connected.has(edge.target);
            // A gentle curve reads better than a straight chord on a radial
            // layout, and separates edges that share endpoints.
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2 - Math.abs(a.x - b.x) * 0.07;
            return (
              <path
                key={edge.id}
                d={`M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`}
                fill="none"
                stroke={`url(#${gradientId(edge.id)})`}
                strokeWidth={0.6 + Math.min(edge.weight, 4) * 0.45}
                opacity={lit ? 0.55 : 0.08}
                className="transition-opacity duration-200"
              />
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
                  fill={outside ? "#64748b" : `url(#${gradientId(node.id)})`}
                  opacity={isSelected ? 0.45 : outside ? 0.1 : 0.22}
                  className={isSelected && !answerMap ? "animate-pulse" : undefined}
                />
                {/* Outside the answer, a node keeps its place but loses its
                    colour: it is still knowledge, just not what this answer
                    was built from. */}
                <circle
                  r={radius}
                  fill={outside ? "#64748b" : `url(#${gradientId(node.id)})`}
                />
                <circle
                  r={radius}
                  fill="none"
                  stroke={
                    isSelected
                      ? "#ffffff"
                      : cited
                        ? "#ffffff"
                        : outside
                          ? "#94a3b8"
                          : colorFor(node.category, 78)
                  }
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
                      fill: node.type === "cluster" ? "#e9ecf1" : "#aab3c0",
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
      className="absolute z-20 w-64 rounded-lg border border-white/12 bg-[#101725]/95 p-3 shadow-xl backdrop-blur"
      style={{
        // Kept inside the viewport rather than clipped at an edge.
        left: `${Math.min(62, Math.max(2, left * 100 + 3))}%`,
        top: `${Math.min(62, Math.max(2, top * 100 + 6))}%`,
      }}
    >
      <p className="text-sm font-semibold text-white">{node.label}</p>
      <p className="mt-0.5 text-[0.6875rem] text-white/60">
        {node.type === "cluster" ? "Knowledge Cluster" : "Knowledge Fragment"} ·{" "}
        {node.category}
      </p>
      <p className="mt-2 text-[0.6875rem] text-white/75">
        Found in {node.document_count} document{node.document_count === 1 ? "" : "s"}
        {node.type === "cluster" && (
          <> · {node.fragment_count} fragment{node.fragment_count === 1 ? "" : "s"}</>
        )}
      </p>
      {node.excerpt && (
        <p className="mt-2 line-clamp-3 text-[0.6875rem] leading-relaxed text-white/60">
          {node.excerpt}
        </p>
      )}
      {node.source_filename && (
        <p className="mt-2 border-t border-white/10 pt-2 text-[0.625rem] text-white/50">
          Source: {node.source_filename}
          {node.source_location?.page ? ` · page ${node.source_location.page}` : ""}
        </p>
      )}
      <div className="mt-2.5 flex flex-wrap gap-2 border-t border-white/10 pt-2.5">
        <button
          type="button"
          onClick={onOpen}
          className="rounded-md bg-white/10 px-2 py-1 text-[0.6875rem] font-medium text-white transition-colors hover:bg-white/20"
        >
          Explore
        </button>
        {node.source_artifact_id && (
          <a
            href={api.artifactContentUrl(node.source_artifact_id)}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md bg-white/10 px-2 py-1 text-[0.6875rem] font-medium text-sky-300 transition-colors hover:bg-white/20"
          >
            Open source
          </a>
        )}
      </div>
    </div>
  );
}

function Legend({ graph }: { graph: CerebroGalaxy }) {
  const categories = [...new Set(graph.nodes.map((n) => n.category))].slice(0, 6);
  if (!categories.length) return null;
  return (
    <div // Capped so it cannot run under the chat launcher in the opposite corner.
      className="absolute bottom-4 left-4 flex max-w-[52%] flex-wrap gap-x-4 gap-y-1.5 rounded-lg border border-white/10 bg-[#101725]/80 px-3 py-2 backdrop-blur">
      {categories.map((category) => (
        <span key={category} className="flex items-center gap-1.5 text-[0.6875rem] text-white/70">
          <span className="size-2 rounded-full" style={{ background: colorFor(category) }} />
          {category}
        </span>
      ))}
      {/* Rotation is not discoverable by itself, so it is said once here
          rather than hidden behind a tooltip on a button. */}
      <span className="w-full text-[0.625rem] text-white/35">
        Drag to move · shift-drag to rotate
      </span>
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
      className="grid size-8 place-items-center rounded-md border border-white/12 bg-[#101725]/85 text-sm text-white/80 backdrop-blur transition-colors hover:bg-[#1a2334]"
    >
      {children}
    </button>
  );
}

/** SVG ids must be valid and unique; node ids contain colons and spaces. */
function gradientId(id: string): string {
  return `g-${id.replace(/[^a-zA-Z0-9]/g, "-")}`;
}
