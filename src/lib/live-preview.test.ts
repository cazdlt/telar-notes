import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import { markdown } from '@codemirror/lang-markdown';
import { EditorState, StateEffect } from '@codemirror/state';
import { GFM } from '@lezer/markdown';
import { describe, expect, it } from 'vitest';
import { buildDecorations, fencedCodeText, linkedTextParts, type LivePreviewOptions } from './live-preview';
import { ObsidianGFM } from './tasks';

describe('fencedCodeText', () => {
  it('keeps every Tasks directive inside a callout', () => {
    const source = [
      '> [!todo]+ Backlog',
      '> ```tasks',
      '> description regex does not match /^$/',
      '> not done',
      '> group by root reverse',
      '> group by heading',
      '> ```',
    ].join('\n');
    const state = EditorState.create({
      doc: source,
      extensions: [markdown({ extensions: [GFM] })],
    });
    let code = '';

    const tree = ensureSyntaxTree(state, state.doc.length, 5000) ?? syntaxTree(state);
    tree.iterate({
      enter(node) {
        if (node.name === 'FencedCode') code = fencedCodeText(node.node, state.doc);
      },
    });

    expect(code).toBe(
      [
        'description regex does not match /^$/',
        'not done',
        'group by root reverse',
        'group by heading',
      ].join('\n'),
    );
  });
});

describe('linkedTextParts', () => {
  it('keeps task text while extracting Obsidian links and aliases', () => {
    expect(linkedTextParts('Ask [[people/Eve|Eve]] about [[Project Atlas]]')).toEqual([
      { kind: 'text', value: 'Ask ' },
      { kind: 'wikilink', target: 'people/Eve', label: 'Eve' },
      { kind: 'text', value: ' about ' },
      { kind: 'wikilink', target: 'Project Atlas', label: 'Project Atlas' },
    ]);
  });
});

describe('buildDecorations', () => {
  it('lays out an item\'s continuation lines by depth instead of raw indentation', () => {
    const doc = ['- parent', '\t- child', '\t\t\tdeeper', '\t  aligned', '- next', '\t```', '\tcode', '\t```', ''].join('\n');
    const state = EditorState.create({ doc, selection: { anchor: doc.length }, extensions: [markdown({ extensions: ObsidianGFM })] });
    const options = { reading: () => false, persistent: () => true } as unknown as LivePreviewOptions;
    const continuations: string[] = [];
    buildDecorations(state, options, [], StateEffect.define()).decorations.between(0, doc.length, (from, _to, value) => {
      if (value.spec.class === 'cm-li-cont') continuations.push(`${state.doc.lineAt(from).number}:${value.spec.attributes.style}`);
    });

    expect(continuations).toEqual(['3:--li-depth: 2', '4:--li-depth: 1']);
  });

  it('folds a list item with children, but not a leaf item or one inside a quote', () => {
    const doc = ['- parent', '\t- child', '\t\t- grandchild', '- leaf', '', '> - quoted', '> \t- nested', ''].join('\n');
    const state = EditorState.create({ doc, selection: { anchor: doc.length }, extensions: [markdown({ extensions: ObsidianGFM })] });
    const options = { reading: () => false, persistent: () => true } as unknown as LivePreviewOptions;
    const foldable = (folded: Array<{ kind: 'list'; from: number }>) => {
      const lines: number[] = [];
      let hidden = '';
      buildDecorations(state, options, folded, StateEffect.define()).decorations.between(0, doc.length, (from, to, value) => {
        if (String(value.spec.class ?? '').includes('cm-foldable-list')) lines.push(state.doc.lineAt(from).number);
        if (value.spec.block && !value.spec.widget) hidden = doc.slice(from, to);
      });
      return { lines, hidden };
    };

    expect(foldable([]).lines).toEqual([1, 2]);
    expect(foldable([{ kind: 'list', from: 0 }]).hidden).toBe('\t- child\n\t\t- grandchild');
  });

  it('decorates the body of a note that has frontmatter', () => {
    const doc = ['---', 'aliases: [Zongzhi]', '---', '# Harlan', '- [I] idea', ''].join('\n');
    const state = EditorState.create({ doc, selection: { anchor: doc.length }, extensions: [markdown({ extensions: ObsidianGFM })] });
    const options = { reading: () => false, persistent: () => false } as unknown as LivePreviewOptions;
    const classes: string[] = [];
    buildDecorations(state, options, [], StateEffect.define()).decorations.between(0, doc.length, (_from, _to, value) => {
      if (value.spec.class) classes.push(value.spec.class);
    });

    expect(classes).toEqual(expect.arrayContaining(['cm-h1', 'cm-li-task']));
  });

  it('reveals frontmatter source when opened in persistent mode', () => {
    const doc = ['---', 'aliases: [Zongzhi]', '---', '# Harlan', ''].join('\n');
    const state = EditorState.create({ doc, selection: { anchor: 4 }, extensions: [markdown({ extensions: ObsidianGFM })] });
    const options = { reading: () => false, persistent: () => true } as unknown as LivePreviewOptions;
    const frontmatterLines = (open: boolean) => {
      let count = 0;
      buildDecorations(state, options, [], StateEffect.define(), open).decorations.between(0, doc.length, (_from, _to, value) => {
        if (String(value.spec.class ?? '').startsWith('cm-frontmatter')) count += 1;
      });
      return count;
    };

    expect(frontmatterLines(false)).toBe(0);
    expect(frontmatterLines(true)).toBe(3);
  });

  it('reveals inline markup only for the element under the caret', () => {
    const doc = 'See **one** and **two** here\n';
    const state = EditorState.create({ doc, selection: { anchor: doc.indexOf('one') }, extensions: [markdown({ extensions: ObsidianGFM })] });
    const options = { reading: () => false, persistent: () => true } as unknown as LivePreviewOptions;
    const hidden: string[] = [];
    buildDecorations(state, options, [], StateEffect.define()).decorations.between(0, doc.length, (from, to, value) => {
      if (to > from && !value.spec.class && !value.spec.widget) hidden.push(`${from}-${to}`);
    });

    const two = doc.indexOf('**two**');
    expect(hidden).toEqual([`${two}-${two + 2}`, `${two + 5}-${two + 7}`]);
  });

  it('reveals a revealed Mermaid block source in persistent mode', () => {
    const doc = ['# Diagram', '```mermaid', 'flowchart LR', '  A --> B', '```', ''].join('\n');
    const from = doc.indexOf('```mermaid');
    const state = EditorState.create({ doc, selection: { anchor: from + 11 }, extensions: [markdown({ extensions: ObsidianGFM })] });
    const options = { reading: () => false, persistent: () => true } as unknown as LivePreviewOptions;
    const codeLines = (revealed: Array<{ from: number; to: number }>) => {
      let count = 0;
      buildDecorations(state, options, [], StateEffect.define(), false, StateEffect.define(), revealed).decorations.between(0, doc.length, (_from, _to, value) => {
        if (String(value.spec.class ?? '').startsWith('cm-codeblock')) count += 1;
      });
      return count;
    };

    expect(codeLines([])).toBe(0);
    expect(codeLines([{ from, to: doc.length - 1 }])).toBe(4);
  });

  it('reveals a revealed table source in persistent mode', () => {
    const doc = ['Intro', '', '| a | b |', '| - | - |', '| 1 | 2 |', ''].join('\n');
    const from = doc.indexOf('| a');
    const state = EditorState.create({ doc, selection: { anchor: from }, extensions: [markdown({ extensions: GFM })] });
    const options = { reading: () => false, persistent: () => true } as unknown as LivePreviewOptions;
    const tableWidgets = (revealed: Array<{ from: number; to: number }>) => {
      let count = 0;
      buildDecorations(state, options, [], StateEffect.define(), false, StateEffect.define(), revealed).decorations.between(0, doc.length, (_from, _to, value) => {
        if (value.spec.widget?.constructor.name === 'TableWidget') count += 1;
      });
      return count;
    };

    expect(tableWidgets([])).toBe(1);
    expect(tableWidgets([{ from, to: doc.length - 1 }])).toBe(0);
  });

  it('does not render embeds written inside code', () => {
    const doc = ['Use `![[Note]]` to embed.', '', '```', '![[Other]]', '```', '', '![[Real]]'].join('\n');
    const state = EditorState.create({ doc, selection: { anchor: 0 }, extensions: [markdown({ extensions: GFM })] });
    const options = { reading: () => false, persistent: () => true } as unknown as LivePreviewOptions;
    const targets: string[] = [];
    buildDecorations(state, options, [], StateEffect.define(), false, StateEffect.define(), []).decorations.between(0, doc.length, (_from, _to, value) => {
      if (value.spec.widget?.constructor.name === 'EmbedWidget') targets.push(value.spec.widget.target);
    });
    expect(targets).toEqual(['Real']);
  });

  it('renders an embed inline when it shares its line with text or a list marker', () => {
    const doc = ['Look here ![[a.png]]', '- ![[b.png]]', '', '![[c.png]]'].join('\n');
    const state = EditorState.create({ doc, selection: { anchor: doc.indexOf('\n\n') + 1 }, extensions: [markdown({ extensions: GFM })] });
    const options = { reading: () => false, persistent: () => true } as unknown as LivePreviewOptions;
    const embeds: Array<{ text: string; inline: boolean }> = [];
    buildDecorations(state, options, [], StateEffect.define(), false, StateEffect.define(), []).decorations.between(0, doc.length, (from, to, value) => {
      if (value.spec.widget?.constructor.name === 'EmbedWidget') embeds.push({ text: doc.slice(from, to), inline: value.spec.widget.inline });
    });
    expect(embeds).toEqual([
      { text: '![[a.png]]', inline: true },
      { text: '![[b.png]]', inline: true },
      { text: '![[c.png]]', inline: false },
    ]);
  });

  it('hangs list items by nesting depth and spaces lists from adjacent blocks', () => {
    const doc = ['Intro', '- one', '  - two', '# Outro', '', '> - quoted', ''].join('\n');
    const state = EditorState.create({ doc, selection: { anchor: 0 }, extensions: [markdown({ extensions: ObsidianGFM })] });
    const options = { reading: () => false, persistent: () => false } as unknown as LivePreviewOptions;
    const lines = new Map<number, string[]>();
    const hidden: string[] = [];
    buildDecorations(state, options, [], StateEffect.define()).decorations.between(0, doc.length, (from, to, value) => {
      const { class: className, attributes } = value.spec;
      if (from === to && className) {
        const entry = lines.get(state.doc.lineAt(from).number) ?? [];
        entry.push(className, ...(attributes?.style ? [attributes.style] : []));
        lines.set(state.doc.lineAt(from).number, entry);
      } else if (to > from && !className && !value.spec.widget) hidden.push(doc.slice(from, to));
    });

    expect(lines.get(2)).toEqual(expect.arrayContaining(['cm-list-start', 'cm-li cm-li-hang', '--li-depth: 0']));
    expect(lines.get(3)).toEqual(expect.arrayContaining(['cm-list-end', 'cm-li cm-li-hang', '--li-depth: 1']));
    expect(lines.get(6)).toEqual(expect.arrayContaining(['cm-li']));
    expect(lines.get(6)).not.toEqual(expect.arrayContaining(['cm-li cm-li-hang']));
    expect(hidden).toContain('  ');
  });
});
