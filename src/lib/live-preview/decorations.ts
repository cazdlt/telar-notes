import { syntaxTree } from '@codemirror/language';
import {
  countColumn,
  StateEffect,
  type EditorState,
  type Range,
  type StateEffectType,
} from '@codemirror/state';
import { Decoration, type DecorationSet } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';
import { continuationOwner, itemTextColumn } from '../list-edit';
import { blockRefId } from '../task-refs';
import { startsWithTaskMarker } from '../tasks';
import { fencedCodeText, foldSections, frontmatterRange, listDepth } from './folding';
import { wikiParts } from './links';
import type { BlockRange, FoldTarget, LivePreviewOptions } from './types';
import {
  BulletWidget,
  FoldWidget,
  FrontmatterWidget,
  HorizontalRuleWidget,
  HyperlinkWidget,
  TaskWidget,
  WikiLinkWidget,
} from './widgets/inline';
import { CopyButtonWidget, EmbedWidget, MermaidWidget } from './widgets/media';
import { TableWidget } from './widgets/table';
import { TaskRefWidget, TasksBlockWidget } from './widgets/tasks';

function activeLines(state: EditorState, reading: boolean, persistent: boolean): Set<number> {
  if (reading || persistent) return new Set();
  const lines = new Set<number>();
  for (const range of state.selection.ranges) {
    const first = state.doc.lineAt(range.from).number;
    const last = state.doc.lineAt(range.to).number;
    for (let line = first; line <= last; line += 1) lines.add(line);
  }
  return lines;
}

function rangeActive(state: EditorState, from: number, to: number, active: Set<number>): boolean {
  const first = state.doc.lineAt(from).number;
  const last = state.doc.lineAt(to).number;
  for (let line = first; line <= last; line += 1) if (active.has(line)) return true;
  return false;
}

/**
 * Lines of an item after its first one (wrapped paragraphs, or text whose marker was deleted)
 * drop their source indentation like the item does and align with the item's text, or one
 * level deeper when indented past it, instead of showing raw tab widths.
 */
function decorateContinuationLines(
  state: EditorState,
  item: SyntaxNode,
  active: Set<number>,
  inSkipped: (position: number) => boolean,
  add: (range: Range<Decoration>) => void,
  addLine: (line: number, className: string, attributes?: Record<string, string>) => void,
): void {
  const { doc } = state;
  const first = doc.lineAt(item.from);
  const textColumn = itemTextColumn(state, item);
  const tree = syntaxTree(state);
  const depth = listDepth(item);
  const task = !!item.getChild('Task');
  for (let number = first.number + 1; number <= doc.lineAt(item.to).number; number += 1) {
    const line = doc.line(number);
    const indent = /^[ \t]*/.exec(line.text)![0].length;
    if (active.has(number) || indent === line.length || inSkipped(line.from)) continue;
    if (continuationOwner(state, line, tree)?.from !== item.from) continue;
    const deeper = countColumn(line.text.slice(0, indent), state.tabSize) > textColumn;
    const marker = task && !deeper ? '; --li-marker: calc(28px + .3em)' : '';
    addLine(number, 'cm-li-cont', { style: `--li-depth: ${depth + (deeper ? 1 : 0)}${marker}` });
    if (indent) add(Decoration.replace({}).range(line.from, line.from + indent));
  }
}

export function buildDecorations(
  state: EditorState,
  options: LivePreviewOptions,
  folded: FoldTarget[],
  toggleFold: StateEffectType<FoldTarget>,
  frontmatterOpen = false,
  toggleFrontmatter: StateEffectType<boolean> = StateEffect.define<boolean>(),
  revealedBlocks: readonly BlockRange[] = [],
): { decorations: DecorationSet; atomic: DecorationSet } {
  const { doc } = state;
  // Persistent mode keeps block widgets (tables, fences, embeds, frontmatter) rendered even
  // under the caret. Inline markup reverts to source only for the element the selection
  // touches, so `**` and link brackets appear around what is being edited, not the whole line.
  const reading = options.reading();
  const active = activeLines(state, reading, options.persistent());
  const revealed = (from: number, to: number): boolean =>
    !reading && state.selection.ranges.some((range) => range.from <= to && range.to >= from);
  const blockRevealed = (from: number): boolean => revealedBlocks.some((block) => from >= block.from && from <= block.to);
  const decorations: Range<Decoration>[] = [];
  const skipped: BlockRange[] = [];
  const decoratedLines = new Set<string>();
  const add = (range: Range<Decoration>) => decorations.push(range);
  const inSkipped = (position: number) => skipped.some((range) => position >= range.from && position < range.to);
  const overlaps = (from: number, to: number) => skipped.some((range) => from < range.to && range.from < to);
  const addLine = (line: number, className: string, attributes?: Record<string, string>) => {
    const key = `${line}:${className}`;
    if (decoratedLines.has(key)) return;
    decoratedLines.add(key);
    add(Decoration.line({ class: className, attributes }).range(doc.line(line).from));
  };

  const sections = foldSections(state);
  const foldedKeys = new Set(folded.map((target) => `${target.kind}:${target.from}`));
  for (const section of sections) {
    if (inSkipped(section.from)) continue;
    const key = `${section.kind}:${section.from}`;
    const collapsed = foldedKeys.has(key);
    add(Decoration.widget({
      widget: new FoldWidget(section, collapsed, toggleFold),
      side: -1,
    }).range(section.from));
    addLine(section.first, `cm-foldable cm-foldable-${section.kind}${collapsed ? ' cm-folded' : ''}`);
    if (!collapsed || section.last <= section.first) continue;
    const from = doc.line(section.first + 1).from;
    const to = doc.line(section.last).to;
    if (overlaps(from, to)) continue;
    add(Decoration.replace({ block: true }).range(from, to));
    skipped.push({ from, to });
  }

  const frontmatter = frontmatterRange(state);
  if (frontmatter) {
    if (!frontmatterOpen && !rangeActive(state, frontmatter.from, frontmatter.to, active)) {
      add(Decoration.replace({ widget: new FrontmatterWidget(frontmatter, false, toggleFrontmatter), block: true }).range(frontmatter.from, frontmatter.to));
      skipped.push(frontmatter);
    } else {
      add(Decoration.widget({ widget: new FrontmatterWidget(frontmatter, true, toggleFrontmatter), block: true, side: -1 }).range(frontmatter.from));
      const first = doc.lineAt(frontmatter.from).number;
      const last = doc.lineAt(frontmatter.to).number;
      for (let line = first; line <= last; line += 1) {
        addLine(line, `cm-frontmatter${line === first ? ' cm-fm-open' : ''}${line === last ? ' cm-fm-close' : ''}`);
      }
    }
  }

  for (const line of active) addLine(line, 'cm-activeLine');

  const text = doc.toString();
  const embedPattern = /!\[\[([^\]|#]+)((?:[#|][^\]]*)?)\]\]/g;
  const inCode = (pos: number): boolean => {
    for (let node: SyntaxNode | null = syntaxTree(state).resolveInner(pos, 1); node; node = node.parent) {
      if (node.name === 'InlineCode' || node.name === 'FencedCode' || node.name === 'CodeBlock') return true;
    }
    return false;
  };
  for (const match of text.matchAll(embedPattern)) {
    const start = match.index ?? 0;
    if (inCode(start)) continue;
    const blockId = blockRefId(match[2]);
    if (blockId) {
      const end = start + match[0].length;
      if (inSkipped(start) || revealed(start, end)) continue;
      add(Decoration.replace({ widget: new TaskRefWidget(match[1].trim(), blockId, options) }).range(start, end));
      skipped.push({ from: start, to: end });
      continue;
    }
    const line = doc.lineAt(start);
    const end = start + match[0].length;
    const target = match[1].trim().replace(/\\$/, '');
    if (active.has(line.number) || inSkipped(start)) continue;
    // An embed alone on its line renders as a block; one sharing the line with text or a
    // list marker renders inline so the rest of the line stays visible.
    if (line.text.trim() === match[0]) {
      if (blockRevealed(line.from)) continue;
      add(Decoration.replace({ widget: new EmbedWidget(target, options), block: true }).range(line.from, line.to));
      skipped.push({ from: line.from, to: line.to });
    } else {
      if (blockRevealed(start) || revealed(start, end)) continue;
      add(Decoration.replace({ widget: new EmbedWidget(target, options, true) }).range(start, end));
      skipped.push({ from: start, to: end });
    }
  }

  syntaxTree(state).iterate({
    enter(node) {
      const { name } = node;
      const line = doc.lineAt(node.from);
      // The root starts at 0, inside any frontmatter; skipping it would skip the whole note.
      if (name === 'Document') return;
      if (inSkipped(node.from)) return false;
      if (frontmatter && node.from >= frontmatter.from && node.from <= frontmatter.to) return false;
      const heading = name.match(/^ATXHeading([1-6])$/);
      if (heading) addLine(line.number, `cm-h${heading[1]}`);
      else if (name === 'HeaderMark' && !revealed(line.from, line.to)) {
        add(Decoration.replace({}).range(node.from, doc.sliceString(node.to, node.to + 1) === ' ' ? node.to + 1 : node.to));
      } else if (name === 'StrongEmphasis' || name === 'Emphasis' || name === 'Strikethrough' || name === 'InlineCode') {
        const styles = { StrongEmphasis: 'cm-strong', Emphasis: 'cm-em', Strikethrough: 'cm-strike', InlineCode: 'cm-code' };
        add(Decoration.mark({ class: styles[name] }).range(node.from, node.to));
      } else if (['EmphasisMark', 'StrikethroughMark', 'CodeMark'].includes(name)) {
        const parent = node.node.parent;
        const element = parent && parent.name !== 'FencedCode' ? parent : line;
        if (!revealed(element.from, element.to)) add(Decoration.replace({}).range(node.from, node.to));
      } else if (name === 'Blockquote') {
        const first = doc.lineAt(node.from).number;
        const last = doc.lineAt(node.to).number;
        const callout = doc.line(first).text.match(/^\s*>\s*\[!(\w+)\]([+-])?\s*(.*)$/);
        const aliases: Record<string, string> = {
          abstract: 'info', summary: 'info', tldr: 'info', todo: 'info', info: 'info',
          tip: 'tip', hint: 'tip', important: 'tip', success: 'success', check: 'success', done: 'success',
          question: 'warning', help: 'warning', faq: 'warning', warning: 'warning', warn: 'warning', caution: 'warning', attention: 'warning',
          failure: 'danger', fail: 'danger', missing: 'danger', danger: 'danger', error: 'danger', bug: 'danger',
          example: 'note', quote: 'note', cite: 'note', note: 'note',
        };
        const type = callout ? aliases[callout[1].toLowerCase()] || 'note' : null;
        for (let number = first; number <= last; number += 1) {
          if (inSkipped(doc.line(number).from)) continue;
          if (type) addLine(number, `cm-callout cm-callout-${type}${number === first ? ' cm-callout-head' : ''}${number === last ? ' cm-callout-last' : ''}`);
          else addLine(number, 'cm-quote');
        }
        if (callout && !active.has(first)) {
          const source = doc.line(first);
          const markerStart = source.text.indexOf('[!');
          const markerEnd = source.text.indexOf(']', markerStart);
          if (markerStart >= 0 && markerEnd > markerStart) {
            let end = source.from + markerEnd + 1;
            if (/^[+-]$/.test(doc.sliceString(end, end + 1))) end += 1;
            if (doc.sliceString(end, end + 1) === ' ') end += 1;
            add(Decoration.replace({}).range(source.from + markerStart, end));
            if (end < source.to) add(Decoration.mark({ class: 'cm-callout-title' }).range(end, source.to));
          }
        }
      } else if (name === 'QuoteMark' && !active.has(line.number)) {
        add(Decoration.replace({}).range(node.from, doc.sliceString(node.to, node.to + 1) === ' ' ? node.to + 1 : node.to));
      } else if ((name === 'BulletList' || name === 'OrderedList') && node.node.parent?.name !== 'ListItem') {
        // Separates a list from an adjacent paragraph that has no blank line in between.
        const first = line.number;
        const last = doc.lineAt(node.to).number;
        if (first > 1 && doc.line(first - 1).text.trim()) addLine(first, 'cm-list-start');
        if (last < doc.lines && doc.line(last + 1).text.trim()) addLine(last, 'cm-list-end');
      } else if (name === 'ListItem') {
        // Rendered items drop their source indentation and hang wrapped lines under the text;
        // items nested in a blockquote keep the source layout.
        const hang = !active.has(line.number) && /^[ \t]*$/.test(doc.sliceString(line.from, node.from));
        if (hang) addLine(line.number, 'cm-li cm-li-hang', { style: `--li-depth: ${listDepth(node.node)}` });
        else addLine(line.number, 'cm-li');
        if (/^[ \t]*$/.test(doc.sliceString(line.from, node.from))) {
          decorateContinuationLines(state, node.node, active, inSkipped, add, addLine);
        }
      } else if (name === 'ListMark' && !active.has(line.number)) {
        const mark = doc.sliceString(node.from, node.to);
        const end = doc.sliceString(node.to, node.to + 1) === ' ' ? node.to + 1 : node.to;
        if (node.from > line.from && /^[ \t]+$/.test(doc.sliceString(line.from, node.from))) {
          add(Decoration.replace({}).range(line.from, node.from));
        }
        if (/^[-*+]$/.test(mark)) {
          if (startsWithTaskMarker(doc.sliceString(end, end + 3))) add(Decoration.replace({}).range(node.from, end));
          else add(Decoration.replace({ widget: new BulletWidget() }).range(node.from, end));
        } else add(Decoration.mark({ class: 'cm-li-num' }).range(node.from, end));
      } else if (name === 'TaskMarker' && !active.has(line.number)) {
        const symbol = doc.sliceString(node.from + 1, node.to - 1);
        add(Decoration.replace({ widget: new TaskWidget(symbol, node.from) }).range(node.from, node.to));
        addLine(line.number, 'cm-li-task');
        if (symbol === 'x' && node.to < line.to) add(Decoration.mark({ class: 'cm-task-done' }).range(node.to, line.to));
      } else if (name === 'HorizontalRule' && !active.has(line.number)) {
        add(Decoration.replace({ widget: new HorizontalRuleWidget() }).range(line.from, line.to));
      } else if (name === 'Table') {
        const from = doc.lineAt(node.from).from;
        const to = doc.lineAt(node.to).to;
        if (!overlaps(from, to) && !rangeActive(state, from, to, active) && !blockRevealed(from)) {
          add(Decoration.replace({ widget: new TableWidget(doc.sliceString(from, to), options), block: true }).range(from, to));
          skipped.push({ from, to });
          return false;
        }
      } else if (name === 'FencedCode') {
        const treeNode = node.node;
        const info = treeNode.getChild('CodeInfo');
        const language = info ? doc.sliceString(info.from, info.to).trim().toLowerCase() : '';
        const code = fencedCodeText(treeNode, doc);
        const from = doc.lineAt(node.from).from;
        const to = doc.lineAt(node.to).to;
        if (language === 'tasks' && !overlaps(from, to) && !rangeActive(state, from, to, active) && !blockRevealed(from)) {
          add(Decoration.replace({ widget: new TasksBlockWidget(code, options), block: true }).range(from, to));
          skipped.push({ from, to });
          return false;
        }
        if (language === 'mermaid' && !overlaps(from, to) && !rangeActive(state, from, to, active) && !blockRevealed(from)) {
          add(Decoration.replace({ widget: new MermaidWidget(code, from), block: true }).range(from, to));
          skipped.push({ from, to });
          return false;
        }
        const first = doc.lineAt(node.from).number;
        const last = doc.lineAt(node.to).number;
        for (let number = first; number <= last; number += 1) {
          addLine(
            number,
            `cm-codeblock${number === first ? ' cm-cb-open' : ''}${number === last ? ' cm-cb-close' : ''}`,
            number === first ? { 'data-lang': language || 'code' } : undefined,
          );
          const codeLine = doc.line(number);
          if (!active.has(number) && (number === first || number === last) && codeLine.length) {
            add(Decoration.replace({}).range(codeLine.from, codeLine.to));
          }
        }
        if (!active.has(first)) add(Decoration.widget({ widget: new CopyButtonWidget(code), side: 1 }).range(doc.line(first).to));
      } else if (name === 'Link' && !revealed(node.from, node.to)) {
        const treeNode = node.node;
        const url = treeNode.getChild('URL');
        if (url) {
          const raw = doc.sliceString(node.from, node.to);
          const label = raw.match(/^\[([^\]]+)\]/)?.[1] || doc.sliceString(url.from, url.to);
          add(Decoration.replace({ widget: new HyperlinkWidget(label, doc.sliceString(url.from, url.to), options, node.from) }).range(node.from, node.to));
          skipped.push({ from: node.from, to: node.to });
          return false;
        }
      } else if (name === 'Image' && !revealed(node.from, node.to)) {
        const url = node.node.getChild('URL');
        if (url) {
          add(Decoration.replace({ widget: new EmbedWidget(doc.sliceString(url.from, url.to), options) }).range(node.from, node.to));
          skipped.push({ from: node.from, to: node.to });
          return false;
        }
      } else if ((name === 'Autolink' || name === 'URL') && !revealed(node.from, node.to)) {
        const raw = doc.sliceString(node.from, node.to);
        const href = raw.replace(/^<|>$/g, '');
        add(Decoration.replace({ widget: new HyperlinkWidget(href, href, options, node.from) }).range(node.from, node.to));
        skipped.push({ from: node.from, to: node.to });
        return false;
      }
      return undefined;
    },
  });

  const tagPattern = /(^|\s)(#[\w/-]+)/g;
  for (const match of text.matchAll(tagPattern)) {
    const start = (match.index ?? 0) + match[1].length;
    const end = start + match[2].length;
    const line = doc.lineAt(start);
    if (!inSkipped(start) && !active.has(line.number) && !/^#{1,6}\s/.test(line.text)) add(Decoration.mark({ class: 'cm-tag' }).range(start, end));
  }

  const wikiPattern = /(?<!!)\[\[([^\]]+)\]\]/g;
  for (const match of text.matchAll(wikiPattern)) {
    const start = match.index ?? 0;
    const end = start + match[0].length;
    if (inSkipped(start) || revealed(start, end)) continue;
    const wiki = wikiParts(match[1]);
    add(Decoration.replace({ widget: new WikiLinkWidget(wiki.target, wiki.label, options, start) }).range(start, end));
  }

  // Replacing decorations remove text from the layout, so the cursor must jump over them
  // in a single step instead of landing on offsets that have no visible position.
  // Every replacing range added above spans text and carries no `class` (only line and
  // mark decorations do), which is what separates them here.
  const replacing = decorations.filter((range) => range.to > range.from && !('class' in range.value.spec));

  try {
    return { decorations: Decoration.set(decorations, true), atomic: Decoration.set(replacing, true) };
  } catch (error) {
    console.warn('[telar] Live Preview decoration overlap', error);
    return { decorations: Decoration.none, atomic: Decoration.none };
  }
}
