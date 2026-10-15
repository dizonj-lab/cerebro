/**
 * Cluster colours, assigned from the data rather than from a fixed list of
 * project-specific topics.
 *
 * A topic's hue is derived from its own name, so the same topic is the same
 * colour on every load and across views, without anybody maintaining a
 * mapping. The palette is a ring of hues chosen to stay distinguishable on a
 * near-black canvas.
 */
const HUES = [196, 160, 265, 38, 340, 220, 12, 285, 95, 315, 180, 50];

function hashOf(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

export function hueFor(category: string): number {
  return HUES[hashOf(category) % HUES.length];
}

export function colorFor(category: string, lightness = 62): string {
  return `hsl(${hueFor(category)} 85% ${lightness}%)`;
}

/** A dimmer, desaturated variant for anything not currently in focus. */
export function mutedColorFor(category: string): string {
  return `hsl(${hueFor(category)} 35% 45%)`;
}
