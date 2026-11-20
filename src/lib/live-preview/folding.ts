import { syntaxTree } from '@codemirror/language';
import type { EditorState } from '@codemirror/state';
import type { SyntaxNode } from '@lezer/common';
import type { BlockRange, CodeTreeNode, FoldSection, TextDocument, TreeNode } from './types';

export function fencedCodeText(node: CodeTreeNode, doc: TextDocument): string {
  return node
    .getChildren('CodeText')
    .map((child) => doc.sliceString(child.from, child.to))
    .join('');
}

export function fencedBlockAt(state: EditorState, from: number): BlockRange | null {
  const line = state.doc.lineAt(from);
  const inner = syntaxTree(state).resolveInner(line.to, -1);
  for (let node: typeof inner | null = inner; node; node = node.parent) {
    if (node.name === 'FencedCode') return { from: line.from, to: state.doc.lineAt(node.to).to };
  }
  return null;
}

export function listDepth(item: TreeNode): number {
  let depth = 0;
  for (let node = item.parent; node; node = node.parent) if (node.name === 'ListItem') depth += 1;
  return depth;
}

export function frontmatterRange(state: EditorState): BlockRange | null {
  if (state.doc.lines < 2 || state.doc.line(1).text.trim() !== '---') return null;
  for (let line = 2; line <= state.doc.lines; line += 1) {
    if (state.doc.line(line).text.trim() === '---') {
      return { from: state.doc.line(1).from, to: state.doc.line(line).to };
    }
  }
  return null;
}

// List items with nested lists fold; inside blockquotes and callouts the source layout differs.
export function foldableItem(item: SyntaxNode): boolean {
  if (!item.getChild('BulletList') && !item.getChild('OrderedList')) return false;
  for (let node = item.parent; node; node = node.parent) if (node.name === 'Blockquote') return false;
  return true;
}

export function foldSections(state: EditorState): FoldSection[] {
  const headings: Array<{ from: number; first: number; level: number }> = [];
  const callouts: FoldSection[] = [];
  const items: FoldSection[] = [];
  const seenCallouts = new Set<number>();
  syntaxTree(state).iterate({
    enter(node) {
      const heading = node.name.match(/^ATXHeading([1-6])$/);
      if (node.name === 'ListItem' && foldableItem(node.node)) {
        const first = state.doc.lineAt(node.from).number;
        const last = state.doc.lineAt(node.to).number;
        if (last > first) items.push({ kind: 'list', from: state.doc.line(first).from, first, last, defaultCollapsed: false });
      } else if (heading) {
        headings.push({
          from: state.doc.lineAt(node.from).from,
          first: state.doc.lineAt(node.from).number,
          level: Number(heading[1]),
        });
      } else if (node.name === 'Blockquote') {
        const first = state.doc.lineAt(node.from).number;
        const source = state.doc.line(first);
        const callout = source.text.match(/^\s*>\s*\[!(\w+)\]([+-])?\s*(.*)$/);
        if (callout && !seenCallouts.has(source.from)) {
          seenCallouts.add(source.from);
          callouts.push({
            kind: 'callout',
            from: source.from,
            first,
            last: state.doc.lineAt(node.to).number,
            defaultCollapsed: callout[2] === '-',
          });
        }
      }
    },
  });
  const foldableHeadings = headings
    .filter((heading) => heading.level <= 3)
    .map((heading) => {
      const boundary = headings.find(
        (candidate) => candidate.first > heading.first && candidate.level <= heading.level,
      );
      return {
        kind: 'heading' as const,
        from: heading.from,
        first: heading.first,
        last: boundary ? boundary.first - 1 : state.doc.lines,
        defaultCollapsed: false,
      };
    });
  return [...foldableHeadings, ...callouts, ...items].sort((left, right) => left.from - right.from);
}
