import { tags } from '@lezer/highlight';
import { Autolink, Strikethrough, Table, type BlockContext, type LeafBlock, type MarkdownConfig } from '@lezer/markdown';

export type TaskStatus = { symbol: string; name: string; glyph: string };

/** Tasks' core statuses plus the Minimal/ITS theme collection, mirrored by server.py. */
export const TASK_STATUSES: readonly TaskStatus[] = [
  { symbol: ' ', name: 'Todo', glyph: '○' },
  { symbol: '/', name: 'In Progress', glyph: '⏳' },
  { symbol: 'x', name: 'Done', glyph: '✅' },
  { symbol: '-', name: 'Cancelled', glyph: '❌' },
  { symbol: '>', name: 'delegated', glyph: '➡️' },
  { symbol: '<', name: 'deferred', glyph: '📅' },
  { symbol: '?', name: 'question', glyph: '❓' },
  { symbol: '!', name: 'important', glyph: '⚠️' },
  { symbol: '*', name: 'star', glyph: '⭐' },
  { symbol: '"', name: 'quote', glyph: '💬' },
  { symbol: 'l', name: 'location', glyph: '📍' },
  { symbol: 'b', name: 'bookmark', glyph: '🔖' },
  { symbol: 'i', name: 'information', glyph: 'ℹ️' },
  { symbol: 'S', name: 'savings', glyph: '💰' },
  { symbol: 'I', name: 'idea', glyph: '💡' },
  { symbol: 'p', name: 'pros', glyph: '👍' },
  { symbol: 'c', name: 'cons', glyph: '👎' },
  { symbol: 'f', name: 'fire', glyph: '🔥' },
  { symbol: 'k', name: 'key', glyph: '🔑' },
  { symbol: 'w', name: 'win', glyph: '🏆' },
  { symbol: 'u', name: 'up', glyph: '📈' },
  { symbol: 'd', name: 'down', glyph: '📉' },
];

const symbols = new Set([...TASK_STATUSES.map((status) => status.symbol), 'X']);

/** Whether `text` starts with a task marker such as `[ ]`, `[x]`, or `[I]`. */
export function startsWithTaskMarker(text: string): boolean {
  return text[0] === '[' && text[2] === ']' && symbols.has(text[1]);
}

/** Fill a select with every status, marking `selected` and keeping unknown symbols visible. */
export function appendStatusOptions(select: HTMLSelectElement, selected: string): void {
  const known = TASK_STATUSES.some((status) => status.symbol === selected);
  const statuses = known ? TASK_STATUSES : [...TASK_STATUSES, { symbol: selected, name: selected, glyph: selected }];
  for (const status of statuses) {
    const option = document.createElement('option');
    option.value = status.symbol;
    option.textContent = status.glyph;
    option.title = status.name;
    option.selected = status.symbol === selected;
    select.append(option);
  }
}

class TaskParser {
  nextLine(): boolean { return false; }
  finish(cx: BlockContext, leaf: LeafBlock): boolean {
    cx.addLeafElement(leaf, cx.elt('Task', leaf.start, leaf.start + leaf.content.length, [
      cx.elt('TaskMarker', leaf.start, leaf.start + 3),
      ...cx.parser.parseInline(leaf.content.slice(3), leaf.start + 3),
    ]));
    return true;
  }
}

/** GFM's TaskList, extended to every status symbol in TASK_STATUSES. */
export const ObsidianTaskList: MarkdownConfig = {
  defineNodes: [
    { name: 'Task', block: true, style: tags.list },
    { name: 'TaskMarker', style: tags.atom },
  ],
  parseBlock: [{
    name: 'TaskList',
    leaf(cx, leaf) {
      return startsWithTaskMarker(leaf.content) && /^[ \t]/.test(leaf.content.slice(3)) && cx.parentType().name === 'ListItem'
        ? new TaskParser()
        : null;
    },
    after: 'SetextHeading',
  }],
};

/** GFM with ObsidianTaskList in place of the checkbox-only TaskList. */
export const ObsidianGFM: MarkdownConfig[] = [Table, ObsidianTaskList, Strikethrough, Autolink];
