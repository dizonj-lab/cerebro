"use client";

import { useState } from "react";

import { EmptyState } from "@/components/dashboard/primitives";
import type { CerebroDashboard } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * A radial preview of how topics co-occur.
 *
 * Edges are artifacts that carry two topics together — the only relationship
 * the data actually supports. It is not a semantic graph and does not claim
 * to be; the caption says what an edge means.
 *
 * Deliberately small: the node count is capped server-side, and the layout is
 * a fixed radial arrangement rather than a force simulation, so there is no
 * animation loop running behind the dashboard.
 */
export function KnowledgeMap({ graph }: { graph: CerebroDashboard["knowledge_map"] }) {
  const [selected, setSelected] = useState<string | null>(null);

  if (!graph.center || graph.nodes.length === 0) {
    return (
      <EmptyState>
        Register a few documents and their topics will appear here, linked by the
        documents they share.
      </EmptyState>
    );
  }

  const centre = { x: 50, y: 50 };
  const others = graph.nodes.filter((n) => n.label !== graph.center);
  const positions = new Map<string, { x: number; y: number }>([[graph.center, centre]]);

  others.forEach((node, i) => {
    const angle = (i / others.length) * Math.PI * 2 - Math.PI / 2;
    positions.set(node.label, {
      x: 50 + Math.cos(angle) * 33,
      y: 50 + Math.sin(angle) * 30,
    });
  });

  const active = selected ?? graph.center;
  const connected = new Set(
    graph.edges
      .filter((e) => e.source === active || e.target === active)
      .flatMap((e) => [e.source, e.target]),
  );

  return (
    <div>
      <svg viewBox="0 0 100 100" className="h-[248px] w-full" role="img"
        aria-label={`Topic map centred on ${graph.center}`}>
        {graph.edges.map((edge) => {
          const a = positions.get(edge.source);
          const b = positions.get(edge.target);
          if (!a || !b) return null;
          const lit = edge.source === active || edge.target === active;
          return (
            <line
              key={`${edge.source}-${edge.target}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={lit ? "var(--color-accent)" : "var(--color-line-strong)"}
              strokeWidth={lit ? 0.7 : 0.4}
              opacity={lit ? 0.9 : 0.5}
            />
          );
        })}

        {graph.nodes.map((node, i) => {
          const p = positions.get(node.label)!;
          const isCentre = node.label === graph.center;
          const dim = !connected.has(node.label) && node.label !== active;
          return (
            <g
              key={node.label}
              transform={`translate(${p.x} ${p.y})`}
              onMouseEnter={() => setSelected(node.label)}
              onMouseLeave={() => setSelected(null)}
              className="cursor-pointer"
            >
              <title>{`${node.label} — ${node.count} document${node.count === 1 ? "" : "s"}`}</title>
              <circle
                r={isCentre ? 6.5 : 3}
                fill={isCentre ? "var(--color-accent)" : NODE_COLORS[i % NODE_COLORS.length]}
                opacity={dim ? 0.35 : 1}
              />
              <text
                y={isCentre ? 12.5 : -5}
                textAnchor="middle"
                className={cn(
                  "pointer-events-none select-none",
                  isCentre ? "fill-ink" : "fill-ink-muted",
                )}
                style={{ fontSize: isCentre ? 4.6 : 3.9, fontWeight: isCentre ? 600 : 500 }}
                opacity={dim ? 0.4 : 1}
              >
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="mt-1 text-[0.6875rem] text-ink-subtle">
        Topics joined when a registered document carries both.
      </p>
    </div>
  );
}

const NODE_COLORS = [
  "#14b8a6", "#8b5cf6", "#ec4899", "#f59e0b",
  "#38bdf8", "#f97316", "#22c55e", "#a78bfa",
];
