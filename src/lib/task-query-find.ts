import { syntaxTree } from '@codemirror/language';
import { getSearchQuery, searchPanelOpen, setSearchQuery, type SearchQuery } from '@codemirror/search';
import { EditorSelection, Prec, StateEffect, StateField, Text, type EditorState, type Extension } from '@codemirror/state';
import { EditorView, ViewPlugin, keymap, type Command, type ViewUpdate } from '@codemirror/view';
import { cachedTaskQuery, fencedCodeText, loadTaskQuery, taskKey } from './live-preview';
import { taskLabel } from './task-refs';
import type { TaskRecord } from './types';

type TasksBlock = { from: number; to: number; query: string };
type TaskHit = { from: number; key: string };
type Range = { from: number; to: number };

/** Tasks in the order a query renders them: ungrouped first, then each group recursively. */
export function tasksInDisplayOrder(tasks: TaskRecord[], depth = 0): TaskRecord[] {
  const groups = new Map<string, TaskRecord[]>();
  const ungrouped: TaskRecord[] = [];
  for (const task of tasks) {
    const group = task.groups?.[depth];
    if (!group) ungrouped.push(task);
    else groups.set(group, [...(groups.get(group) ?? []), task]);
  }
  return [...ungrouped, ...[...groups.values()].flatMap((members) => tasksInDisplayOrder(members, depth + 1))];
}

/** Tasks whose visible description matches `query`, in display order. */
export function matchingTasks(tasks: TaskRecord[], query: SearchQuery): TaskRecord[] {
  if (!query.valid) return [];
  return tasksInDisplayOrder(tasks).filter((task) => !query.getCursor(Text.of([taskLabel(task.description)])).next().done);
}

function tasksBlocks(state: EditorState): TasksBlock[] {
  const blocks: TasksBlock[] = [];
  const { doc } = state;
  syntaxTree(state).iterate({
    enter: (node) => {
      if (node.name !== 'FencedCode') return;
      const info = node.node.getChild('CodeInfo');
      if (info && doc.sliceString(info.from, info.to).trim().toLowerCase() === 'tasks') {
        blocks.push({ from: doc.lineAt(node.from).from, to: doc.lineAt(node.to).to, query: fencedCodeText(node.node, doc) });
      }
      return false;
    },
  });
  return blocks;
}

function taskHits(blocks: TasksBlock[], query: SearchQuery, source: string): TaskHit[] {
  return blocks.flatMap((block) => {
    const result = cachedTaskQuery(block.query, source);
    return result ? matchingTasks(result.tasks, query).map((task) => ({ from: block.from, key: taskKey(task) })) : [];
  });
}

/** Document matches outside Tasks blocks; matches in a block's query text are not what the user sees. */
function documentMatches(state: EditorState, query: SearchQuery, blocks: TasksBlock[]): Range[] {
  const matches: Range[] = [];
  const cursor = query.getCursor(state);
  for (let next = cursor.next(); !next.done; next = cursor.next()) {
    const { from, to } = next.value;
    if (!blocks.some((block) => from < block.to && to > block.from)) matches.push({ from, to });
  }
  return matches;
}

function findLast<T>(items: T[], test: (item: T) => boolean): T | undefined {
  for (let index = items.length - 1; index >= 0; index -= 1) if (test(items[index])) return items[index];
  return undefined;
}

const setActiveHit = StateEffect.define<TaskHit | null>();
const tasksLoaded = StateEffect.define<null>();

const activeHit = StateField.define<TaskHit | null>({
  create: () => null,
  update(value, transaction) {
    for (const effect of transaction.effects) if (effect.is(setActiveHit)) return effect.value;
    if (transaction.docChanged || transaction.selection || transaction.effects.some((effect) => effect.is(setSearchQuery))) return null;
    return value;
  },
});

function step(source: string, forward: boolean): Command {
  return (view) => {
    const { state } = view;
    const query = getSearchQuery(state);
    if (!query.valid) return false;
    const blocks = tasksBlocks(state);
    const hits = taskHits(blocks, query, source);
    if (!hits.length) return false;
    const matches = documentMatches(state, query, blocks);
    const active = state.field(activeHit);
    const activeBlock = active ? blocks.find((block) => block.from === active.from) : undefined;
    const index = active ? hits.findIndex((hit) => hit.from === active.from && hit.key === active.key) : -1;
    let hit: TaskHit | undefined;
    let match: Range | undefined;
    if (forward) {
      const pos = activeBlock ? activeBlock.to : state.selection.main.to;
      hit = index >= 0 ? hits[index + 1] : hits.find((candidate) => candidate.from >= pos);
      match = matches.find((candidate) => candidate.from >= pos);
      if (!hit && !match) { hit = hits[0]; match = matches[0]; }
      if (hit && match && match.from < hit.from) hit = undefined;
    } else {
      const pos = activeBlock ? activeBlock.from : state.selection.main.from;
      hit = index >= 0 ? hits[index - 1] : findLast(hits, (candidate) => candidate.from < pos);
      match = findLast(matches, (candidate) => candidate.to <= pos);
      if (!hit && !match) { hit = hits.at(-1); match = matches.at(-1); }
      if (hit && match && match.from > hit.from) hit = undefined;
    }
    if (hit) {
      // An off-screen block has no DOM yet: scroll to it first so the painter can reach the row.
      const rendered = !!renderedRow(view, hit);
      view.dispatch({ effects: rendered ? setActiveHit.of(hit) : [setActiveHit.of(hit), EditorView.scrollIntoView(hit.from, { y: 'start' })] });
    } else if (match) {
      view.dispatch({ selection: EditorSelection.single(match.from, match.to), scrollIntoView: true, userEvent: 'select.search' });
    }
    return true;
  };
}

function renderedRow(view: EditorView, hit: TaskHit): HTMLElement | undefined {
  return [...view.contentDOM.querySelectorAll<HTMLElement>('.cm-tasks-query .cm-tasks-row')]
    .find((row) => row.dataset.taskKey === hit.key && view.posAtDOM(row.closest('.cm-tasks-query') ?? row) === hit.from);
}

const highlights = typeof CSS !== 'undefined' && 'highlights' in CSS ? CSS.highlights : null;

function textRanges(root: Element, query: SearchQuery): globalThis.Range[] {
  const nodes: { node: globalThis.Text; start: number }[] = [];
  let content = '';
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    nodes.push({ node: node as globalThis.Text, start: content.length });
    content += node.textContent ?? '';
  }
  const locate = (offset: number, end: boolean) => {
    const entry = findLast(nodes, (candidate) => (end ? candidate.start < offset : candidate.start <= offset)) ?? nodes[0];
    return { node: entry.node, offset: offset - entry.start };
  };
  const ranges: globalThis.Range[] = [];
  const cursor = query.getCursor(Text.of(content.split('\n')));
  for (let next = cursor.next(); !next.done; next = cursor.next()) {
    if (next.value.from === next.value.to) continue;
    const start = locate(next.value.from, false);
    const end = locate(next.value.to, true);
    const range = document.createRange();
    range.setStart(start.node, start.offset);
    range.setEnd(end.node, end.offset);
    ranges.push(range);
  }
  return ranges;
}

/** Paints matches inside rendered Tasks rows, outlines the current one, and loads queries not yet cached. */
function taskFindPainter(source: string, next: Command, previous: Command): Extension {
  return ViewPlugin.fromClass(class {
    private requested = new Set<string>();
    private pendingScroll: TaskHit | null = null;
    private scrollAttempts = 0;
    constructor(private readonly view: EditorView) {
      view.dom.addEventListener('click', this.onClick, true);
      this.paint(null);
    }
    // The panel's Next/Previous buttons call the stock commands directly.
    private onClick = (event: MouseEvent) => {
      const button = event.target instanceof Element ? event.target.closest('.cm-search button[name=next], .cm-search button[name=prev]') : null;
      if (!button || !(button.getAttribute('name') === 'next' ? next : previous)(this.view)) return;
      event.preventDefault();
      event.stopPropagation();
    };
    update(update: ViewUpdate) {
      const previous = update.startState.field(activeHit);
      this.load();
      this.paint(previous);
    }
    destroy() {
      this.view.dom.removeEventListener('click', this.onClick, true);
      highlights?.delete('task-find');
      highlights?.delete('task-find-current');
    }
    private load() {
      const { state } = this.view;
      if (!searchPanelOpen(state) || !getSearchQuery(state).valid) return;
      for (const block of tasksBlocks(state)) {
        if (cachedTaskQuery(block.query, source) || this.requested.has(block.query)) continue;
        this.requested.add(block.query);
        void loadTaskQuery(block.query, source).then(
          () => this.view.dispatch({ effects: tasksLoaded.of(null) }),
          () => undefined, // The block widget already reports the failure.
        );
      }
    }
    private paint(previous: TaskHit | null) {
      const { state } = this.view;
      const query = getSearchQuery(state);
      const active = state.field(activeHit);
      const searching = searchPanelOpen(state) && query.valid;
      const all: globalThis.Range[] = [];
      const current: globalThis.Range[] = [];
      let activeRow: HTMLElement | null = null;
      for (const row of this.view.contentDOM.querySelectorAll<HTMLElement>('.cm-tasks-query .cm-tasks-row')) {
        const block = row.closest('.cm-tasks-query');
        const isActive = !!active && searching && row.dataset.taskKey === active.key && !!block && this.view.posAtDOM(block) === active.from;
        row.classList.toggle('cm-tasks-row-current', isActive);
        if (isActive) activeRow = row;
        const description = row.querySelector('.cm-tasks-description');
        if (!searching || !description) continue;
        const ranges = textRanges(description, query);
        all.push(...ranges);
        if (isActive) current.push(...ranges);
      }
      if (highlights) {
        highlights.set('task-find', new Highlight(...all));
        highlights.set('task-find-current', new Highlight(...current));
      }
      if (active !== previous) { this.pendingScroll = active; this.scrollAttempts = 0; }
      if (activeRow && this.pendingScroll) {
        const row = activeRow;
        const target = this.pendingScroll.from;
        this.pendingScroll = null;
        // Center the row through CodeMirror so no pending scroll of its own overrides it.
        requestAnimationFrame(() => {
          const block = row.closest('.cm-tasks-query');
          if (!block) return;
          const offset = row.getBoundingClientRect().top - block.getBoundingClientRect().top;
          const margin = this.view.scrollDOM.clientHeight / 2 - row.offsetHeight / 2 - offset;
          this.view.dispatch({ effects: EditorView.scrollIntoView(target, { y: 'start', yMargin: margin }) });
        });
      } else if (this.pendingScroll && this.scrollAttempts < 4) {
        // Unmeasured widgets make CodeMirror's first scroll land short of a distant block.
        const target = this.pendingScroll.from;
        this.scrollAttempts += 1;
        requestAnimationFrame(() => {
          if (this.pendingScroll?.from === target) this.view.dispatch({ effects: EditorView.scrollIntoView(target, { y: 'start' }) });
        });
      }
    }
  });
}

/** Extends the search panel so Find also walks the tasks rendered by Tasks query blocks. */
export function taskQueryFind(source: string): Extension {
  const inSearchField = () => document.activeElement?.getAttribute('main-field') === 'true';
  const next = step(source, true);
  const previous = step(source, false);
  return [
    activeHit,
    taskFindPainter(source, next, previous),
    Prec.highest(keymap.of([
      { key: 'Enter', run: (view) => inSearchField() && next(view), shift: (view) => inSearchField() && previous(view), scope: 'search-panel' },
      { key: 'Mod-g', run: next, shift: previous, scope: 'editor search-panel' },
      { key: 'F3', run: next, shift: previous, scope: 'editor search-panel' },
    ])),
  ];
}
