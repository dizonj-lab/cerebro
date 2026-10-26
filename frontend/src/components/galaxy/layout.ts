/**
 * Galaxy layout.
 *
 * A deterministic radial arrangement, not a force simulation: clusters sit on
 * a ring around the centre and a cluster's fragments orbit it. The same graph
 * therefore lays out the same way every time, there is no animation loop
 * running behind the view, and the cost is O(n) rather than O(n²) per frame.
 *
 * An opened cluster's passages are placed by what they resemble. One that is
 * alike to another topic leans out towards it, further the stronger the
 * resemblance, so its line to that topic is short and readable. One that
 * resembles nothing outside its own topic orbits close around it: it belongs
 * there, and drawing it at the same distance as the others made it look
 * disconnected rather than self-contained.
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
const FRAGMENT_RING = 92;
/** Passages like nothing else sit closer in. */
const ORBIT_RING = 58;
/** How far a passage leans towards the topic it resembles, at full strength. */
const LEAN = 74;
/** Neighbouring leaning passages fan out by this much, in radians. */
const FAN = 0.42;

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
    const origin = parent ?? { x: CENTRE.x, y: CENTRE.y };
    const fragments = nodes.filter((n) => n.type === "fragment");
    const orbiting = fragments.filter((n) => n.orbit !== false || !n.affinity);
    const leaning = fragments.filter((n) => n.orbit === false && n.affinity);

    orbiting.forEach((node, i) => {
      const angle = (i / Math.max(1, orbiting.length)) * Math.PI * 2;
      // Without similarity data at all (an older API), keep the old ring.
      const ring = node.orbit == null ? FRAGMENT_RING : ORBIT_RING;
      positions.set(node.id, {
        node,
        x: origin.x + Math.cos(angle) * ring,
        y: origin.y + Math.sin(angle) * ring * 0.82,
        radius: 5,
      });
    });

    // Group the leaning passages by the topic they lean towards, and fan each
    // group out around the direction of that topic.
    const byTarget = new Map<string, GraphNode[]>();
    for (const node of leaning) {
      const key = `topic:${node.affinity}`;
      byTarget.set(key, [...(byTarget.get(key) ?? []), node]);
    }
    for (const [target, group] of byTarget) {
      const towards = positions.get(target);
      const base = towards
        ? Math.atan2(towards.y - origin.y, towards.x - origin.x)
        : 0;
      group.forEach((node, i) => {
        const angle = base + (i - (group.length - 1) / 2) * FAN;
        const reach = FRAGMENT_RING + LEAN * (edgeStrength(nodes, node) ?? 0.5);
        positions.set(node.id, {
          node,
          x: origin.x + Math.cos(angle) * reach,
          y: origin.y + Math.sin(angle) * reach * 0.82,
          radius: 5,
        });
      });
    }
  }

  return positions;
}

/**
 * How close a passage is to the other topic it resembles, from 0 to 1.
 *
 * Read from the node's own similarity relative to its siblings, so the layout
 * needs nothing but the nodes; the edges carry the exact figure.
 */
function edgeStrength(nodes: GraphNode[], node: GraphNode): number | null {
  const values = nodes
    .filter((n) => n.type === "fragment" && typeof n.similarity === "number")
    .map((n) => n.similarity as number);
  if (!values.length || typeof node.similarity !== "number") return null;
  const low = Math.min(...values);
  const high = Math.max(...values);
  // A passage that fits its own topic loosely is the one that strays furthest.
  return high > low ? 1 - (node.similarity - low) / (high - low) : 0.5;
}

export const VIEWBOX = { width: 1000, height: 660 };
