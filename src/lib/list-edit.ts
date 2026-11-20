/**
 * Structural editing for Markdown lists: Tab/Shift-Tab move an item together with its
 * children, Backspace removes markup one step at a time (checkbox, then marker), and Enter
 * outdents empty items. Edits only rewrite leading whitespace and markers, never
 * reorder lines, and refuse moves the parser would no longer read as a list (an item nested
 * two levels deeper than its parent becomes paragraph text).
 */
import { ensureSyntaxTree, indentUnit, syntaxTree } from '@codemirror/language';
import {
  countColumn,
  EditorSelection,
  Facet,
  Prec,
  type ChangeSpec,
  type EditorState,
  type Extension,
  type Line,
  type StateCommand,
} from '@codemirror/state';
import { keymap } from '@codemirror/view';
import type { SyntaxNode, Tree } from '@lezer/common';

/** Line starts of list items whose children are folded in the editor. */
export const foldedListItems = Facet.define<readonly number[], readonly number[]>({
  combine: (values) => values[0] ?? [],
});

type ListItem = {
  node: SyntaxNode;
  line: Line;
  mark: SyntaxNode;
  /** First position after the marker and its spacing. */
  contentFrom: number;
  task: SyntaxNode | null;
  /** First position after the task marker and its spacing, or contentFrom. */
  textFrom: number;
};

function treeOf(state: EditorState, upto: number): Tree {
  return ensureSyntaxTree(state, upto, 200) ?? syntaxTree(state);
}

const skipSpace = (state: EditorState, from: number, to: number): number => {
  let pos = from;
  while (pos < to && /[ \t]/.test(state.sliceDoc(pos, pos + 1))) pos += 1;
  return pos;
};

function insideBlockquote(node: SyntaxNode): boolean {
  for (let parent = node.parent; parent; parent = parent.parent) if (parent.name === 'Blockquote') return true;
  return false;
}

/** The list item whose marker starts `line`, outside blockquotes. */
function itemAtLine(state: EditorState, line: Line, tree = treeOf(state, line.to)): ListItem | null {
  const indent = /^[ \t]*/.exec(line.text)![0].length;
  if (indent === line.length) return null;
  let node: SyntaxNode | null = tree.resolveInner(line.from + indent, 1);
  while (node && node.name !== 'ListItem') node = node.parent;
  if (!node || node.from < line.from || insideBlockquote(node)) return null;
  const mark = node.getChild('ListMark');
  if (!mark) return null;
  const contentFrom = skipSpace(state, mark.to, line.to);
  const task = node.getChild('Task')?.getChild('TaskMarker') ?? null;
  const textFrom = task && task.from === contentFrom ? skipSpace(state, task.to, line.to) : contentFrom;
  return { node, line, mark, contentFrom, task: task && task.from === contentFrom ? task : null, textFrom };
}

const parentItem = (item: SyntaxNode): SyntaxNode | null => {
  for (let node = item.parent; node; node = node.parent) if (node.name === 'ListItem') return node;
  return null;
};

const hasChildList = (item: SyntaxNode): boolean => !!(item.getChild('BulletList') || item.getChild('OrderedList'));

const CONTINUATION_STOP = new Set(['ListItem', 'FencedCode', 'CodeBlock', 'Table', 'HTMLBlock']);

/** The item a line without a marker belongs to (a wrapped paragraph, or deleted marker). */
export function continuationOwner(state: EditorState, line: Line, tree = syntaxTree(state)): SyntaxNode | null {
  const indent = /^[ \t]*/.exec(line.text)![0].length;
  if (indent === line.length) return null;
  let node: SyntaxNode | null = tree.resolveInner(line.from + indent, 1);
  while (node && !CONTINUATION_STOP.has(node.name)) node = node.parent;
  if (node?.name !== 'ListItem' || node.from >= line.from || insideBlockquote(node)) return null;
  return node;
}

/** Column where an item's text starts, after its marker and one space. */
export function itemTextColumn(state: EditorState, item: SyntaxNode): number {
  const line = state.doc.lineAt(item.from);
  const mark = item.getChild('ListMark');
  return countColumn(state.sliceDoc(line.from, mark ? mark.to : item.from), state.tabSize) + 1;
}

const indentColumns = (text: string, tabSize: number): number => {
  let column = 0;
  for (const char of text) {
    if (char === ' ') column += 1;
    else if (char === '\t') column += tabSize - (column % tabSize);
    else break;
  }
  return column;
};

/** Removes `columns` of leading indentation from a line, splitting a tab when it overshoots. */
function dedent(state: EditorState, line: Line, columns: number): ChangeSpec | null {
  let column = 0;
  let length = 0;
  while (column < columns && length < line.length) {
    const char = line.text[length];
    if (char === ' ') column += 1;
    else if (char === '\t') column += state.tabSize - (column % state.tabSize);
    else break;
    length += 1;
  }
  if (!length) return null;
  return { from: line.from, to: line.from + length, insert: ' '.repeat(Math.max(0, column - columns)) };
}

const lastLine = (state: EditorState, item: SyntaxNode): number => state.doc.lineAt(item.to).number;

/** Items started on the selected lines, without those nested inside another selected item. */
function selectedRoots(state: EditorState): ListItem[] | null {
  const tree = treeOf(state, state.selection.ranges.at(-1)!.to);
  const roots: ListItem[] = [];
  let coveredTo = 0;
  for (const range of state.selection.ranges) {
    const first = state.doc.lineAt(range.from).number;
    const last = state.doc.lineAt(range.to).number;
    for (let number = first; number <= last; number += 1) {
      if (number <= coveredTo) continue;
      const line = state.doc.line(number);
      const item = itemAtLine(state, line, tree);
      if (!item) {
        if (!line.text.trim() && roots.length) continue;
        return null;
      }
      roots.push(item);
      coveredTo = lastLine(state, item.node);
    }
  }
  return roots.length ? roots : null;
}

function shiftLines(state: EditorState, from: number, to: number, direction: 1 | -1, columns: number): ChangeSpec[] {
  const changes: ChangeSpec[] = [];
  for (let number = from; number <= to; number += 1) {
    const line = state.doc.line(number);
    if (!line.text.trim()) continue;
    if (direction > 0) changes.push({ from: line.from, insert: state.facet(indentUnit) });
    else {
      const change = dedent(state, line, columns);
      if (change) changes.push(change);
    }
  }
  return changes;
}

/** Whether the item on `line` started its list before an edit; lines never move during one. */
function firstItemLines(state: EditorState, from: number, to: number): Set<number> {
  const tree = treeOf(state, state.doc.line(Math.min(to, state.doc.lines)).to);
  const lines = new Set<number>();
  for (let number = Math.max(1, from); number <= Math.min(to, state.doc.lines); number += 1) {
    const item = itemAtLine(state, state.doc.line(number), tree);
    if (item && item.node.prevSibling?.name !== 'ListItem') lines.add(number);
  }
  return lines;
}

/**
 * Sequential numbers for the ordered lists around lines `from`..`to`. A list keeps the number
 * of its first item when that item already started a list, and starts at 1 otherwise.
 */
export function renumberLists(
  state: EditorState,
  from: number,
  to: number,
  wasFirst: (line: number) => boolean,
): ChangeSpec[] {
  const first = Math.max(1, from - 1);
  const last = Math.min(state.doc.lines, to + 1);
  const tree = treeOf(state, state.doc.line(last).to);
  const lists = new Map<number, SyntaxNode>();
  for (let number = first; number <= last; number += 1) {
    const line = state.doc.line(number);
    const indent = /^[ \t]*/.exec(line.text)![0].length;
    for (let node: SyntaxNode | null = tree.resolveInner(line.from + indent, 1); node; node = node.parent) {
      if (node.name === 'OrderedList') lists.set(node.from, node);
    }
  }
  const changes: ChangeSpec[] = [];
  for (const list of lists.values()) {
    const items = list.getChildren('ListItem');
    const marks = items.map((item) => item.getChild('ListMark'));
    const firstMark = marks[0] && /^\d+/.exec(state.sliceDoc(marks[0].from, marks[0].to));
    if (!firstMark) continue;
    let next = wasFirst(state.doc.lineAt(items[0].from).number) ? Number(firstMark[0]) : 1;
    for (const mark of marks) {
      const digits = mark && /^\d+/.exec(state.sliceDoc(mark.from, mark.to));
      if (mark && digits && digits[0] !== String(next)) {
        changes.push({ from: mark.from, to: mark.from + digits[0].length, insert: String(next) });
      }
      next += 1;
    }
  }
  return changes;
}

/** Applies `changes`, then renumbers the ordered lists they touched, as one transaction. */
const applyWithRenumber = (
  state: EditorState,
  dispatch: Parameters<StateCommand>[0]['dispatch'],
  changes: ChangeSpec[],
  lines: { from: number; to: number },
  userEvent: string,
  wasFirst?: (line: number) => boolean,
  selection?: EditorSelection,
): true => {
  const before = firstItemLines(state, lines.from - 1, lines.to + 1);
  const structural = state.changes(changes);
  const middle = state.update({ changes: structural }).state;
  const renumber = renumberLists(middle, lines.from, lines.to, wasFirst ?? ((line) => before.has(line)));
  const all = structural.compose(middle.changes(renumber));
  dispatch(state.update({
    changes: all,
    selection: (selection ?? state.selection).map(all, 1),
    scrollIntoView: true,
    userEvent,
  }));
  return true;
};

function outdentChanges(state: EditorState, item: ListItem): ChangeSpec[] | null {
  const parent = parentItem(item.node);
  if (!parent) return null;
  const columns = indentColumns(item.line.text, state.tabSize)
    - indentColumns(state.doc.lineAt(parent.from).text, state.tabSize);
  return shiftLines(state, item.line.number, lastLine(state, item.node), -1, columns);
}

/** Tab: nests the selected items, with their children, under the preceding sibling. */
export const indentListItems: StateCommand = ({ state, dispatch }) => {
  const roots = selectedRoots(state);
  if (!roots) return false;
  // Without a preceding sibling the item would jump two levels and stop being a list.
  if (roots.some((item) => item.node.prevSibling?.name !== 'ListItem')) return true;
  const changes = roots.flatMap((item) => shiftLines(state, item.line.number, lastLine(state, item.node), 1, 0));
  return applyWithRenumber(state, dispatch, changes, {
    from: roots[0].line.number,
    to: lastLine(state, roots.at(-1)!.node),
  }, 'input.indent');
};

/** Shift-Tab: moves the selected items, with their children, up one nesting level. */
export const outdentListItems: StateCommand = ({ state, dispatch }) => {
  const roots = selectedRoots(state);
  if (!roots) return false;
  const changes = roots.flatMap((item) => outdentChanges(state, item) ?? []);
  if (!changes.length) return true;
  return applyWithRenumber(state, dispatch, changes, {
    from: roots[0].line.number,
    to: lastLine(state, roots.at(-1)!.node),
  }, 'delete.dedent');
};

function deleteContinuationIndent(
  state: EditorState,
  dispatch: Parameters<StateCommand>[0]['dispatch'],
  line: Line,
  head: number,
): boolean {
  const indent = /^[ \t]*/.exec(line.text)![0].length;
  if (!indent || head !== line.from + indent) return false;
  const owner = continuationOwner(state, line, treeOf(state, line.to));
  if (!owner) return false;
  const column = countColumn(line.text.slice(0, indent), state.tabSize);
  let from = line.from - 1;
  if (column > itemTextColumn(state, owner)) {
    from = head - 1;
    if (line.text[indent - 1] === ' ') {
      const drop = column % state.tabSize || state.tabSize;
      while (from > line.from && head - from < drop && line.text[from - line.from - 1] === ' ') from -= 1;
    }
  }
  dispatch(state.update({ changes: { from, to: head }, selection: { anchor: from }, scrollIntoView: true, userEvent: 'delete.backward' }));
  return true;
}

/**
 * Backspace at the start of an item's text: drops the checkbox, then the marker, keeping the
 * indentation so another marker can be typed. Children move up a level so they stay a list.
 * On a line without a marker, it removes one indent level while the line sits deeper than the
 * item's text, then joins it with the line above.
 */
export const deleteListMarkup: StateCommand = ({ state, dispatch }) => {
  const range = state.selection.main;
  if (state.selection.ranges.length > 1 || !range.empty) return false;
  const item = itemAtLine(state, state.doc.lineAt(range.head));
  if (!item) return deleteContinuationIndent(state, dispatch, state.doc.lineAt(range.head), range.head);
  const lines = { from: item.line.number, to: lastLine(state, item.node) };
  if (item.task && range.head === item.textFrom) {
    return applyWithRenumber(state, dispatch, [{ from: item.task.from, to: item.textFrom }], lines, 'delete.backward');
  }
  if (range.head !== item.contentFrom) return false;
  const changes: ChangeSpec[] = [{ from: item.mark.from, to: item.contentFrom }];
  const child = item.node.getChild('BulletList') ?? item.node.getChild('OrderedList');
  if (child) {
    const columns = indentColumns(state.doc.lineAt(child.from).text, state.tabSize)
      - indentColumns(item.line.text, state.tabSize);
    changes.push(...shiftLines(state, item.line.number + 1, lines.to, -1, columns));
  }
  return applyWithRenumber(state, dispatch, changes, lines, 'delete.backward');
};

function continuationMarker(state: EditorState, item: ListItem): string {
  const mark = state.sliceDoc(item.mark.from, item.mark.to);
  const ordered = /^(\d+)([.)])$/.exec(mark);
  const marker = ordered ? `${Number(ordered[1]) + 1}${ordered[2]}` : mark;
  return `${marker} ${item.task ? '[ ] ' : ''}`;
}

/**
 * Enter on an item: an empty nested item moves up a level and an empty top-level one loses
 * its marker. At the end of a folded item, the new sibling goes after its hidden children.
 */
export const insertListNewline: StateCommand = ({ state, dispatch }) => {
  const range = state.selection.main;
  if (state.selection.ranges.length > 1 || !range.empty) return false;
  const item = itemAtLine(state, state.doc.lineAt(range.head));
  if (!item || range.head < item.textFrom) return false;
  const lines = { from: item.line.number, to: lastLine(state, item.node) };
  const empty = !state.sliceDoc(item.textFrom, item.line.to).trim();
  if (empty && !hasChildList(item.node)) {
    const outdent = outdentChanges(state, item);
    if (outdent) return applyWithRenumber(state, dispatch, outdent, lines, 'input');
    return applyWithRenumber(state, dispatch, [{ from: item.line.from, to: item.line.to }], lines, 'input');
  }
  if (range.head === item.line.to && hasChildList(item.node) && state.facet(foldedListItems).includes(item.line.from)) {
    const end = state.doc.line(lines.to).to;
    const insert = `${state.lineBreak}${/^[ \t]*/.exec(item.line.text)![0]}${continuationMarker(state, item)}`;
    return applyWithRenumber(
      state, dispatch, [{ from: end, insert }], lines, 'input', () => true,
      EditorSelection.single(end),
    );
  }
  return false;
};

/** Keymap for list editing; it must outrank the Markdown keymap and indentWithTab. */
export function listEditing(): Extension {
  return Prec.highest(keymap.of([
    { key: 'Tab', run: indentListItems, shift: outdentListItems },
    { key: 'Backspace', run: deleteListMarkup },
    { key: 'Enter', run: insertListNewline },
  ]));
}
