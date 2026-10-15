"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { GalaxyCanvas } from "@/components/galaxy/GalaxyCanvas";
import { KnowledgeTimeline } from "@/components/galaxy/KnowledgeTimeline";
import { NodeDetailsPanel } from "@/components/galaxy/NodeDetailsPanel";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { ApiError, api } from "@/lib/api";
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

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Knowledge Galaxy</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Explore the connections in your knowledge.
        </p>
      </div>

      <ErrorMessage>{error}</ErrorMessage>

      <div className="flex flex-col gap-4 xl:flex-row">
        <div className="h-[28rem] min-w-0 flex-1 xl:h-[34rem]">
          <GalaxyCanvas
            graph={graph}
            selectedId={selectedId}
            expandedTopic={expandedTopic}
            onSelect={onSelectNode}
            onExpand={(topic) => void expand(topic)}
          />
        </div>

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

      <KnowledgeTimeline
        events={events}
        selectedTopic={selectedTopic}
        selectedArtifactId={selectedArtifactId}
        onSelect={onTimelineSelect}
      />
    </div>
  );
}
