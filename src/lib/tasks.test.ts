import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import { markdown } from '@codemirror/lang-markdown';
import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { ObsidianGFM, startsWithTaskMarker } from './tasks';

function taskMarkers(source: string): string[] {
  const state = EditorState.create({ doc: source, extensions: [markdown({ extensions: ObsidianGFM })] });
  const tree = ensureSyntaxTree(state, state.doc.length, 5000) ?? syntaxTree(state);
  const markers: string[] = [];
  tree.iterate({
    enter(node) {
      if (node.name === 'TaskMarker') markers.push(state.doc.sliceString(node.from, node.to));
    },
  });
  return markers;
}

describe('ObsidianTaskList', () => {
  it('parses custom status symbols as tasks', () => {
    expect(taskMarkers(['- [ ] todo', '- [-] cancelled', '\t- [>] nested', '- [I] idea', '', '> - [?] quoted'].join('\n')))
      .toEqual(['[ ]', '[-]', '[>]', '[I]', '[?]']);
  });

  it('leaves links, unknown symbols, and markers without text as plain list items', () => {
    expect(taskMarkers(['- [[Harlan]]', '- [z] unknown', '- [x]', 'not a list [x] item'].join('\n'))).toEqual([]);
  });
});

describe('startsWithTaskMarker', () => {
  it('matches only three-character markers with a known symbol', () => {
    expect(startsWithTaskMarker('[X]')).toBe(true);
    expect(startsWithTaskMarker('["] quote')).toBe(true);
    expect(startsWithTaskMarker('[[l')).toBe(false);
  });
});
