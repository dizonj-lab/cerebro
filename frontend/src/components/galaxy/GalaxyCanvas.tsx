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
 * Zoom and pan are a transform on one group, so neither re-renders React.
 */
export function GalaxyCanvas({
  graph,
  selectedId,
  expandedTopic,
  onSelect,
  onExpand,
}: GalaxyCanvasProps) {
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const [hovered, setHovered] = useState<string | null>(null);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
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
    if (!focus) return null;
    const set = new Set<string>([focus]);
    for (const edge of graph.edges) {
      if (edge.source === focus) set.add(edge.target);
      if (edge.target === focus) set.add(edge.source);
    }
    return set;
  }, [focus, graph.edges]);

  const reset = useCallback(() => {
    setView({ scale: 1, x: 0, y: 0 });
    setMoved({});
  }, []);
  const zoom = useCallback(
    (factor: number) =>
      setView((v) => ({ ...v, scale: Math.min(3, Math.max(0.5, v.scale * factor)) })),
    [],
  );

  function onPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    // Only the empty canvas starts a pan. Capturing the pointer whenever it
    // went down anywhere meant a press on a node was retargeted to the svg
    // and never produced a click, so nodes could not be selected at all.
    if (event.target !== event.currentTarget) return;
    drag.current = { x: event.clientX, y: event.clientY, ox: view.x, oy: view.y };
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const start = drag.current;
    if (!start) return;
    setView((v) => ({
      ...v,
      x: start.ox + (event.clientX - start.x) / v.scale,
      y: start.oy + (event.clientY - start.y) / v.scale,
    }));
  }
  function endDrag() {
    drag.current = null;
    setDragging(false);
  }

  const hoveredNode = hovered ? positions.get(hovered)?.node : undefined;
  const hoveredPoint = hovered ? positions.get(hovered) : undefined;

  return (
    <div className="relative size-full overflow-hidden rounded-xl bg-[#070b14]">
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

        <g transform={`translate(${VIEWBOX.width / 2} ${VIEWBOX.height / 2}) scale(${view.scale}) translate(${-VIEWBOX.width / 2 + view.x} ${-VIEWBOX.height / 2 + view.y})`}>
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
            return (
              <g
                key={node.id}
                transform={`translate(${x} ${y})`}
                opacity={lit ? 1 : 0.25}
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
                  setMoved((current) => ({
                    ...current,
                    [node.id]: {
                      x: start.ox + (event.clientX - start.x) / (scaleX * view.scale),
                      y: start.oy + (event.clientY - start.y) / (scaleX * view.scale),
                    },
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
                  fill={`url(#${gradientId(node.id)})`}
                  opacity={isSelected ? 0.45 : 0.22}
                  className={isSelected ? "animate-pulse" : undefined}
                />
                <circle r={radius} fill={`url(#${gradientId(node.id)})`} />
                <circle
                  r={radius}
                  fill="none"
                  stroke={isSelected ? "#ffffff" : colorFor(node.category, 78)}
                  strokeWidth={isSelected ? 1.6 : 0.7}
                  opacity={isSelected ? 0.95 : 0.5}
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

      <div className="absolute bottom-4 right-4 flex flex-col gap-1.5">
        <ViewButton label="Zoom in" onClick={() => zoom(1.25)}>+</ViewButton>
        <ViewButton label="Zoom out" onClick={() => zoom(0.8)}>−</ViewButton>
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
  view: { scale: number; x: number; y: number };
  onOpen: () => void;
  onKeepOpen: () => void;
  onDismiss: () => void;
}) {
  const left = ((x + view.x - VIEWBOX.width / 2) * view.scale + VIEWBOX.width / 2) / VIEWBOX.width;
  const top = ((y + view.y - VIEWBOX.height / 2) * view.scale + VIEWBOX.height / 2) / VIEWBOX.height;

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
