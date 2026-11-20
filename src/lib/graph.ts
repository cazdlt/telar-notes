import type { LinksIndex } from './types';

export type GraphNode = { id: string; label: string; group: string; degree: number; x: number; y: number; vx: number; vy: number; pinned: boolean };
export type GraphEdge = { source: number; target: number };
export type Graph = { nodes: GraphNode[]; edges: GraphEdge[]; neighbors: Set<number>[] };

export type BuildOptions = { scope?: Set<string>; hiddenGroups?: Set<string>; orphans?: boolean };
export type Forces = { repulsion: number; spring: number; springLength: number; gravity: number };

export const DEFAULT_FORCES: Forces = { repulsion: 2000, spring: 0.3, springLength: 50, gravity: 0.005 };

const DAMPING = 0.82;
const MAX_SPEED = 40;

const HUES = [28, 200, 140, 280, 350, 60, 170, 230];

const groupOf = (path: string): string => (path.includes('/') ? path.split('/')[0] : '');

/** Collect the notes within `depth` link hops of `center`, following links in both directions. */
export function localScope(index: LinksIndex, center: string, depth: number): Set<string> {
  const scope = new Set([center]);
  let frontier = [center];
  for (let hop = 0; hop < depth && frontier.length; hop++) {
    const next: string[] = [];
    for (const path of frontier) {
      const entry = index[path];
      for (const other of [...(entry?.links_to ?? []), ...(entry?.linked_from ?? [])]) {
        if (!scope.has(other)) { scope.add(other); next.push(other); }
      }
    }
    frontier = next;
  }
  return scope;
}

/**
 * Build an undirected graph from the links index.
 *
 * Every Markdown note in the index or among link targets becomes a node, except those under hidden
 * folders such as `.trash/`; reciprocal links collapse into one edge.
 * `scope` restricts the graph to a subset of paths (e.g. from `localScope`), `hiddenGroups`
 * drops notes by top-level folder, and `orphans: false` drops notes left without any edge.
 */
export function buildGraph(index: LinksIndex, { scope, hiddenGroups, orphans = true }: BuildOptions = {}): Graph {
  const ids = new Map<string, number>();
  const nodes: GraphNode[] = [];
  const add = (id: string): number | undefined => {
    if ((scope && !scope.has(id)) || hiddenGroups?.has(groupOf(id)) || !/\.md$/i.test(id) || id.split('/').some((part) => part.startsWith('.'))) return undefined;
    let i = ids.get(id);
    if (i === undefined) {
      i = nodes.length;
      ids.set(id, i);
      const angle = i * 2.39996;
      const radius = 12 * Math.sqrt(i + 1);
      nodes.push({ id, label: id.split('/').at(-1)?.replace(/\.md$/i, '') || id, group: groupOf(id), degree: 0, x: radius * Math.cos(angle), y: radius * Math.sin(angle), vx: 0, vy: 0, pinned: false });
    }
    return i;
  };
  for (const path of Object.keys(index)) add(path);
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();
  for (const [path, entry] of Object.entries(index)) {
    const a = add(path);
    if (a === undefined) continue;
    for (const target of entry.links_to) {
      const b = add(target);
      if (b === undefined || a === b) continue;
      const key = a < b ? `${a}:${b}` : `${b}:${a}`;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({ source: a, target: b });
    }
  }
  const neighbors = nodes.map(() => new Set<number>());
  for (const { source, target } of edges) {
    nodes[source].degree++;
    nodes[target].degree++;
    neighbors[source].add(target);
    neighbors[target].add(source);
  }
  if (!orphans && nodes.some((node) => node.degree === 0)) {
    return buildGraph(index, { scope: new Set(nodes.filter((node) => node.degree > 0).map((node) => node.id)) });
  }
  return { nodes, edges, neighbors };
}

/** Advance the force layout one tick; `alpha` in (0, 1] scales how far nodes move. */
export function stepLayout(graph: Graph, alpha: number, forces: Forces = DEFAULT_FORCES): void {
  const { nodes, edges } = graph;
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const d2 = Math.max(dx * dx + dy * dy, 1);
      const f = forces.repulsion / d2 / Math.sqrt(d2);
      a.vx += dx * f; a.vy += dy * f;
      b.vx -= dx * f; b.vy -= dy * f;
    }
  }
  for (const { source, target } of edges) {
    const a = nodes[source];
    const b = nodes[target];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.max(Math.hypot(dx, dy), 0.01);
    // Weaken springs touching hubs so they don't collapse their neighborhoods (d3-force's default).
    const f = (forces.spring * (d - forces.springLength)) / d / Math.min(a.degree, b.degree);
    a.vx += dx * f; a.vy += dy * f;
    b.vx -= dx * f; b.vy -= dy * f;
  }
  for (const node of nodes) {
    node.vx = (node.vx - node.x * forces.gravity) * DAMPING;
    node.vy = (node.vy - node.y * forces.gravity) * DAMPING;
    const speed = Math.hypot(node.vx, node.vy);
    if (speed > MAX_SPEED) { node.vx *= MAX_SPEED / speed; node.vy *= MAX_SPEED / speed; }
    if (node.pinned) { node.vx = 0; node.vy = 0; continue; }
    node.x += node.vx * alpha;
    node.y += node.vy * alpha;
  }
}

/** Assign colors to the largest groups (top-level folders); smaller groups get none. */
export function groupColors(graph: Graph): Map<string, string> {
  const counts = new Map<string, number>();
  for (const node of graph.nodes) counts.set(node.group, (counts.get(node.group) ?? 0) + 1);
  const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return new Map(ranked.slice(0, HUES.length).map(([group], i) => [group, `hsl(${HUES[i]} 55% 60%)`]));
}
