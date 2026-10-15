/**
 * Galaxy layout.
 *
 * A deterministic radial arrangement, not a force simulation: clusters sit on
 * a ring around the centre and a cluster's fragments orbit it. The same graph
 * therefore lays out the same way every time, there is no animation loop
 * running behind the view, and the cost is O(n) rather than O(n²) per frame.
 */
import type { GraphNode } from "@/lib/api";

export interface Positioned {
  node: GraphNode;
  x: number;
  y: number;
  radius: number;
}

const CENTRE = { x: 500, y: 330 };
const CLUSTER_RING = 215;
const FRAGMENT_RING = 74;

export function layout(nodes: GraphNode[], expanded: string | null): Map<string, Positioned> {
  const clusters = nodes.filter((n) => n.type === "cluster");
  const positions = new Map<string, Positioned>();

  const maxDocs = Math.max(1, ...clusters.map((c) => c.document_count));

  clusters.forEach((node, i) => {
    const angle = (i / Math.max(1, clusters.length)) * Math.PI * 2 - Math.PI / 2;
    // Alternate radii so labels on a busy ring do not collide.
    const ring = CLUSTER_RING * (i % 2 === 0 ? 1 : 0.72);
    positions.set(node.id, {
      node,
      x: CENTRE.x + Math.cos(angle) * ring,
      y: CENTRE.y + Math.sin(angle) * ring * 0.78,
      // Size carries weight: how many documents confirmed this topic.
      radius: 13 + (node.document_count / maxDocs) * 13,
    });
  });

  if (expanded) {
    const parent = positions.get(expanded);
    const fragments = nodes.filter((n) => n.type === "fragment");
    fragments.forEach((node, i) => {
      const angle = (i / Math.max(1, fragments.length)) * Math.PI * 2;
      const origin = parent ?? { x: CENTRE.x, y: CENTRE.y };
      positions.set(node.id, {
        node,
        x: origin.x + Math.cos(angle) * FRAGMENT_RING,
        y: origin.y + Math.sin(angle) * FRAGMENT_RING * 0.82,
        radius: 5,
      });
    });
  }

  return positions;
}

export const VIEWBOX = { width: 1000, height: 660 };
