/**
 * Galaxy layout.
 *
 * A deterministic radial arrangement, not a force simulation: clusters sit on
 * a ring around the centre and a cluster's fragments orbit it. The same graph
 * therefore lays out the same way every time, there is no animation loop
 * running behind the view, and the cost is O(n) rather than O(n²) per frame.
 *
 * An opened cluster's passages surround it. One that clearly resembles another
 * topic steps a little way out towards it — never far, so it still reads as
 * belonging to its parent — and the rest orbit close around it. Placing
 * passages out in open space by any trace of resemblance left them stranded
 * in the middle of the map, looking attached to nothing.
 */
import type { GraphEdge, GraphNode } from "@/lib/api";

export interface Positioned {
  node: GraphNode;
  x: number;
  y: number;
  radius: number;
}

const CENTRE = { x: 500, y: 330 };
const CLUSTER_RING = 215;
const FRAGMENT_RING = 92;
/** Every passage starts on this ring, close around its own topic. */
const ORBIT_RING = 56;
/** How much further a passage that clearly resembles another topic steps out. */
const LEAN = 34;
/** It never covers more than this share of the way to that topic. */
const MAX_REACH_SHARE = 0.35;
/** Below this strength a resemblance is drawn, faintly, but moves nothing. */
export const LEAN_THRESHOLD = 0.33;
/** Neighbouring leaning passages fan out by this much, in radians. */
const FAN = 0.38;

/**
 * Whether a passage steps out towards another topic, and how strongly.
 *
 * Only a moderate or strong resemblance moves it. A weak one — just above the
 * library's typical similarity — keeps the passage in orbit around its own
 * topic, with its faint line still drawn: the user reads a passage by where it
 * sits, and one hanging in open space looked unattached even when it was not.
 */
export function reachOf(node: GraphNode, edges: GraphEdge[]): { target: string; strength: number } | null {
  if (node.type !== "fragment" || !node.affinity) return null;
  const target = `topic:${node.affinity}`;
  const edge = edges.find((e) => e.source === node.id && e.target === target);
  const strength = edge?.strength ?? 0;
  return strength >= LEAN_THRESHOLD ? { target, strength } : null;
}

export function layout(
  nodes: GraphNode[],
  expanded: string | null,
  edges: GraphEdge[] = [],
): Map<string, Positioned> {
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
    // `expanded` is the topic's label; positions are keyed by node id. Looking
    // it up by label found nothing, so every opened topic's passages were
    // drawn round the middle of the map instead of round their parent.
    const parent = positions.get(`topic:${expanded}`) ?? positions.get(expanded);
    const origin = parent ?? { x: CENTRE.x, y: CENTRE.y };
    const fragments = nodes.filter((n) => n.type === "fragment");
    const reaches = new Map(fragments.map((n) => [n.id, reachOf(n, edges)]));
    const orbiting = fragments.filter((n) => !reaches.get(n.id));
    const leaning = fragments.filter((n) => reaches.get(n.id));

    // The orbit leaves a gap where the leaning passages go, so the two never
    // sit on top of each other.
    const away = leaning.map((n) => {
      const towards = positions.get(reaches.get(n.id)!.target);
      return towards ? Math.atan2(towards.y - origin.y, towards.x - origin.x) : 0;
    });
    orbiting.forEach((node, i) => {
      let angle = (i / Math.max(1, orbiting.length)) * Math.PI * 2 - Math.PI / 2;
      for (const a of away) {
        const gap = Math.atan2(Math.sin(angle - a), Math.cos(angle - a));
        if (Math.abs(gap) < FAN) angle += gap >= 0 ? FAN : -FAN;
      }
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
    // group out around the direction of that topic — a short step, never far
    // enough to leave the parent's neighbourhood.
    const byTarget = new Map<string, GraphNode[]>();
    for (const node of leaning) {
      const key = reaches.get(node.id)!.target;
      byTarget.set(key, [...(byTarget.get(key) ?? []), node]);
    }
    for (const [target, group] of byTarget) {
      const towards = positions.get(target);
      const base = towards ? Math.atan2(towards.y - origin.y, towards.x - origin.x) : 0;
      const distance = towards ? Math.hypot(towards.x - origin.x, towards.y - origin.y) : Infinity;
      group.forEach((node, i) => {
        const angle = base + (i - (group.length - 1) / 2) * FAN;
        const strength = reaches.get(node.id)!.strength;
        const reach = Math.min(ORBIT_RING + 14 + LEAN * strength, Math.max(ORBIT_RING + 8, distance * MAX_REACH_SHARE));
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

export const VIEWBOX = { width: 1000, height: 660 };
