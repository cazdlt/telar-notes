import { describe, expect, it } from 'vitest';

import { buildGraph, groupColors, localScope, stepLayout } from './graph';
import type { LinksIndex } from './types';

const index: LinksIndex = {
  'a.md': { links_to: ['b.md', 'dir/c.md'], linked_from: ['b.md'] },
  'b.md': { links_to: ['a.md'], linked_from: ['a.md'] },
  'dir/c.md': { links_to: ['d.md'], linked_from: ['a.md'] },
  'd.md': { links_to: [], linked_from: ['dir/c.md'] },
  'orphan.md': { links_to: [], linked_from: [] },
};

describe('buildGraph', () => {
  it('collapses reciprocal links and counts degree', () => {
    const graph = buildGraph(index);
    expect(graph.nodes.map((node) => node.id)).toEqual(['a.md', 'b.md', 'dir/c.md', 'd.md', 'orphan.md']);
    expect(graph.edges).toHaveLength(3);
    expect(graph.nodes.map((node) => node.degree)).toEqual([2, 1, 2, 1, 0]);
    expect([...graph.neighbors[0]].sort()).toEqual([1, 2]);
  });

  it('uses the file stem as label and the top-level folder as group', () => {
    const node = buildGraph(index).nodes[2];
    expect([node.label, node.group]).toEqual(['c', 'dir']);
    expect(buildGraph(index).nodes[0].group).toBe('');
  });

  it('adds link targets missing from the index', () => {
    const graph = buildGraph({ 'a.md': { links_to: ['ghost.md'], linked_from: [] } });
    expect(graph.nodes.map((node) => node.id)).toEqual(['a.md', 'ghost.md']);
    expect(graph.edges).toEqual([{ source: 0, target: 1 }]);
  });

  it('skips hidden folders and non-note targets', () => {
    const graph = buildGraph({ 'a.md': { links_to: ['.trash/old.md', 'photo.png'], linked_from: [] }, '.claude/x.md': { links_to: ['a.md'], linked_from: [] } });
    expect(graph.nodes.map((node) => node.id)).toEqual(['a.md']);
    expect(graph.edges).toEqual([]);
  });

  it('drops notes without edges when orphans are excluded', () => {
    expect(buildGraph(index, { orphans: false }).nodes.map((node) => node.id)).toEqual(['a.md', 'b.md', 'dir/c.md', 'd.md']);
  });

  it('drops hidden groups and the edges touching them', () => {
    const graph = buildGraph(index, { hiddenGroups: new Set(['dir']) });
    expect(graph.nodes.map((node) => node.id)).toEqual(['a.md', 'b.md', 'd.md', 'orphan.md']);
    expect(graph.edges).toHaveLength(1);
  });

  it('ignores self links', () => {
    expect(buildGraph({ 'a.md': { links_to: ['a.md'], linked_from: ['a.md'] } }).edges).toEqual([]);
  });

  it('restricts nodes and edges to the scope', () => {
    const graph = buildGraph(index, { scope: new Set(['a.md', 'dir/c.md']) });
    expect(graph.nodes.map((node) => node.id)).toEqual(['a.md', 'dir/c.md']);
    expect(graph.edges).toEqual([{ source: 0, target: 1 }]);
  });
});

describe('groupColors', () => {
  it('colors groups by descending size', () => {
    expect([...groupColors(buildGraph(index)).keys()]).toEqual(['', 'dir']);
  });

  it('leaves groups beyond the palette uncolored', () => {
    const many = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [`g${i}/n.md`, { links_to: [], linked_from: [] }]));
    expect(groupColors(buildGraph(many)).size).toBe(8);
  });
});

describe('localScope', () => {
  it('follows links in both directions up to depth', () => {
    expect([...localScope(index, 'dir/c.md', 1)].sort()).toEqual(['a.md', 'd.md', 'dir/c.md']);
    expect([...localScope(index, 'dir/c.md', 2)].sort()).toEqual(['a.md', 'b.md', 'd.md', 'dir/c.md']);
  });

  it('returns only the center for depth zero or unknown notes', () => {
    expect([...localScope(index, 'a.md', 0)]).toEqual(['a.md']);
    expect([...localScope(index, 'missing.md', 2)]).toEqual(['missing.md']);
  });
});

describe('stepLayout', () => {
  it('keeps pinned nodes in place and moves free ones', () => {
    const graph = buildGraph(index);
    graph.nodes[0].pinned = true;
    const [x0, y0, x1] = [graph.nodes[0].x, graph.nodes[0].y, graph.nodes[1].x];
    stepLayout(graph, 1);
    expect([graph.nodes[0].x, graph.nodes[0].y]).toEqual([x0, y0]);
    expect(graph.nodes[1].x).not.toBe(x1);
  });
});
