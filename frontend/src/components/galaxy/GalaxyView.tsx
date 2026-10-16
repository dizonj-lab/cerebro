"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { GalaxyCanvas } from "@/components/galaxy/GalaxyCanvas";
import { RecallChat } from "@/components/galaxy/RecallChat";
import { KnowledgeTimeline } from "@/components/galaxy/KnowledgeTimeline";
import { NodeDetailsPanel } from "@/components/galaxy/NodeDetailsPanel";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type {
  CerebroGalaxy,
  CerebroNodeDetails,
  CerebroTimelineEvent,
  GraphNode,
} from "@/lib/api";

/**
 * Galaxy and Timeline, as two views of one selection.
 *
 * Selection lives here and flows down, so the two cannot disagree and there
 * is no circular update: a click in either view sets the same state once.
 *
 * Nothing on this screen calls a language model.
 */
export function GalaxyView() {
  const [graph, setGraph] = useState<CerebroGalaxy | null>(null);
  const [events, setEvents] = useState<CerebroTimelineEvent[]>([]);
  const [details, setDetails] = useState<CerebroNodeDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Workspace shape. The galaxy is the thing being read, so it gets to take
  // the whole screen, and the split between it and the timeline is the
  // user's to set rather than a fixed ratio.
  const [panelOpen, setPanelOpen] = useState(true);
  const [maximized, setMaximized] = useState(false);
  const [galaxyHeight, setGalaxyHeight] = useState(460);
  const resize = useRef<{ y: number; start: number } | null>(null);

  // Details are cached per node, so revisiting one costs nothing.
  const cache = useRef(new Map<string, CerebroNodeDetails>());

  useEffect(() => {
    Promise.all([api.galaxy(), api.knowledgeTimeline()])
      .then(([g, t]) => {
        setGraph(g);
        setEvents(t.events);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load your Galaxy."),
      )
      .finally(() => setLoading(false));
  }, []);

  const openNode = useCallback(async (id: string) => {
    setSelectedId(id);
    const cached = cache.current.get(id);
    if (cached) {
      setDetails(cached);
      return;
    }
    setDetailsLoading(true);
    try {
      const fetched = await api.graphNode(id);
      cache.current.set(id, fetched);
      setDetails(fetched);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load that node.");
    } finally {
      setDetailsLoading(false);
    }
  }, []);

  // Fragments arrive only when a cluster is opened — the whole graph is
  // never loaded at once.
  const expand = useCallback(
    async (topic: string | null) => {
      setExpandedTopic(topic);
      if (!topic || !graph) return;
      try {
        const expansion = await api.expandCluster(topic);
        setGraph((current) => {
          if (!current) return current;
          const known = new Set(current.nodes.map((n) => n.id));
          const clusters = current.nodes.filter((n) => n.type === "cluster");
          return {
            ...current,
            nodes: [...clusters, ...expansion.nodes.filter((n) => !known.has(n.id))],
            edges: [
              ...current.edges.filter((e) => e.kind !== "contains"),
              ...expansion.edges,
            ],
          };
        });
      } catch {
        // A failed expansion leaves the cluster view as it was.
        setExpandedTopic(null);
      }
    },
    [graph],
  );

  const onSelectNode = useCallback((node: GraphNode) => void openNode(node.id), [openNode]);

  const onTimelineSelect = useCallback(
    (event: CerebroTimelineEvent) => {
      // Timeline → Galaxy: focus the event's first topic cluster.
      const topic = event.topics[0];
      if (topic) void openNode(`topic:${topic}`);
    },
    [openNode],
  );

  const selectedTopic =
    selectedId?.startsWith("topic:") ? selectedId.slice("topic:".length) : null;
  const selectedArtifactId = details?.source_artifact_id ?? null;

  if (loading) {
    return <div className="h-96 animate-pulse rounded-xl bg-surface-sunken" />;
  }

  if (!graph?.nodes.length) {
    return (
      <div className="rounded-xl border border-line bg-surface p-12 text-center">
        <h1 className="text-xl font-semibold text-ink">Your Knowledge Galaxy Awaits</h1>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-muted">
          The Galaxy is built from documents you have reviewed and registered. Add one,
          confirm its topics, and your first cluster appears here.
        </p>
        <Link href="/construct/ingest" className="mt-6 inline-block">
          <Button>Ingest your first document</Button>
        </Link>
      </div>
    );
  }

  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    resize.current = { y: event.clientY, start: galaxyHeight };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function onResize(event: React.PointerEvent<HTMLDivElement>) {
    const start = resize.current;
    if (!start) return;
    setGalaxyHeight(Math.min(900, Math.max(260, start.start + (event.clientY - start.y))));
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-4",
        // Maximised, the workspace leaves the page flow entirely and covers
        // the shell — the Galaxy is what the screen is for at that point.
        maximized && "fixed inset-0 z-50 overflow-auto bg-canvas p-4",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Knowledge Galaxy</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Explore the connections in your knowledge.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setMaximized((v) => !v)}
          className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
        >
          {maximized ? "Exit full screen" : "Full screen"}
        </button>
      </div>

      <ErrorMessage>{error}</ErrorMessage>

      {/*
        Galaxy and Timeline share one column, so the Timeline is as wide as
        the Galaxy and both grow when the details panel is collapsed. Putting
        the Timeline outside this row made opening the panel push it down
        instead of narrowing it.
      */}
      <div className="flex min-h-0 flex-1 flex-col gap-4 xl:flex-row">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="relative min-w-0" style={{ height: galaxyHeight }}>
          <GalaxyCanvas
            graph={graph}
            selectedId={selectedId}
            expandedTopic={expandedTopic}
            onSelect={onSelectNode}
            onExpand={(topic) => void expand(topic)}
          />
          {/* Anchored inside the workspace, over the lower right. */}
          <RecallChat topic={selectedTopic} />
        </div>

        {/* Drag to give either view more room. */}
        <div
          role="separator"
          aria-label="Resize galaxy"
          onPointerDown={startResize}
          onPointerMove={onResize}
          onPointerUp={() => {
            resize.current = null;
          }}
          className="group mx-auto flex h-3 w-24 cursor-row-resize items-center justify-center rounded-full"
        >
          <span className="h-1 w-full rounded-full bg-line-strong transition-colors group-hover:bg-accent" />
        </div>

        <KnowledgeTimeline
          events={events}
          selectedTopic={selectedTopic}
          selectedArtifactId={selectedArtifactId}
          onSelect={onTimelineSelect}
        />
        </div>

        {panelOpen ? (
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => setPanelOpen(false)}
              aria-label="Collapse details panel"
              title="Collapse details panel"
              className="hidden h-fit rounded-lg border border-white/10 bg-[#101725] p-2 text-white/60 transition-colors hover:text-white xl:block"
            >
              <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path d="M8 5.5 12.5 10 8 14.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {selectedId ? (
              <NodeDetailsPanel
                details={details}
                loading={detailsLoading}
                onClose={() => {
                  setSelectedId(null);
                  setDetails(null);
                }}
                onSelectRelated={(id) => void openNode(id)}
              />
            ) : (
              <aside className="w-full shrink-0 rounded-xl border border-white/10 bg-[#101725] p-5 xl:w-[21rem]">
                <h2 className="text-sm font-semibold text-white">Node Details</h2>
                <p className="mt-2 text-[0.8125rem] leading-relaxed text-white/55">
                  Select a cluster to see what it is built from — the documents behind it,
                  how it connects, and where each fragment came from.
                </p>
                {graph.truncated && (
                  <p className="mt-4 border-t border-white/10 pt-3 text-[0.6875rem] text-white/40">
                    Showing your {graph.nodes.length} largest clusters.
                  </p>
                )}
              </aside>
            )}
          </div>
        ) : (
          // Collapsed to a rail of icons, in the same place, so the panel can
          // be brought back without hunting for a control.
          <aside className="hidden h-fit shrink-0 flex-col gap-1 rounded-xl border border-white/10 bg-[#101725] p-2 xl:flex">
            <button
              type="button"
              onClick={() => setPanelOpen(true)}
              aria-label="Expand details panel"
              title="Node details"
              className="rounded-lg p-2 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
            >
              <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path d="M12 5.5 7.5 10l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <span
              className="mx-auto size-2 rounded-full"
              style={{ background: selectedId ? "#7fa9e2" : "transparent" }}
              aria-hidden="true"
            />
          </aside>
        )}
      </div>

    </div>
  );
}
