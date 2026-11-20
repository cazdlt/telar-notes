import { autocompletion, type Completion, type CompletionContext, type CompletionResult } from '@codemirror/autocomplete';
import type { Extension } from '@codemirror/state';
import type { EditorView } from '@codemirror/view';
import { api } from './api';
import type { TaskRecord } from './types';

/** Typing `[[^^` (Obsidian's vault-wide block search) opens the task picker. */
const PICKER_TRIGGER = /!?\[\[\^\^[^\]]*$/;
const OPEN_TASKS_TTL_MS = 30_000;

let openTasks: { at: number; tasks: Promise<TaskRecord[]> } | null = null;

function loadOpenTasks(): Promise<TaskRecord[]> {
  if (!openTasks || Date.now() - openTasks.at > OPEN_TASKS_TTL_MS) {
    const tasks = api.tasks('not done').then((result) => result.tasks.filter((task) => task.description));
    openTasks = { at: Date.now(), tasks };
    tasks.catch(() => { openTasks = null; });
  }
  return openTasks.tasks;
}

/** Parse the `^id` fragment of an embed such as `![[Note#^id]]`. */
export function blockRefId(fragment: string): string | null {
  return /^#\^([A-Za-z0-9-]+)$/.exec(fragment)?.[1] ?? null;
}

/** Plain-text label for a task description: wikilink labels kept, inline markup dropped. */
export function taskLabel(description: string): string {
  return description
    .replace(/\[\[(?:[^\]|]*\|)?([^\]]*)\]\]/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`]/g, '')
    .trim();
}

/** Shortest Obsidian link name for `path`: the basename unless another note shares it. */
export function noteLinkName(path: string, files: ReadonlySet<string>): string {
  const withoutExtension = path.replace(/\.md$/i, '');
  const base = withoutExtension.split('/').pop() ?? withoutExtension;
  const lower = `${base.toLowerCase()}.md`;
  const shared = [...files].filter((file) => (file.split('/').pop() ?? '').toLowerCase() === lower).length;
  return shared > 1 ? withoutExtension : base;
}

/**
 * Badge for a referenced task on a dated note (daily notes): its completion or
 * cancellation date when that differs from the note's own date, e.g. `done 10-11`.
 */
export function taskRefBadge(task: Pick<TaskRecord, 'status' | 'dates'>, notePath: string): string | null {
  const noteDate = /(\d{4}-\d{2}-\d{2})\.md$/.exec(notePath)?.[1];
  if (!noteDate) return null;
  const closed = task.status.type === 'DONE' ? ['done', task.dates.done] : task.status.type === 'CANCELLED' ? ['cancelled', task.dates.cancelled] : null;
  if (!closed || !closed[1] || closed[1] === noteDate) return null;
  return `${closed[0]} ${closed[1].slice(5)}`;
}

function insertReference(view: EditorView, task: TaskRecord, from: number, to: number, files: ReadonlySet<string>): void {
  void api.ensureTaskBlockId(task.location).then(({ id }) => {
    openTasks = null;
    const insert = `![[${noteLinkName(task.location.path, files)}#^${id}]]`;
    view.dispatch({ changes: { from, to, insert }, selection: { anchor: from + insert.length } });
  });
}

/** Autocomplete that inserts `![[Note#^id]]` for an open task, adding the block ID to its source line if needed. */
export function taskReferencePicker(files: () => ReadonlySet<string>): Extension {
  const source = async (context: CompletionContext): Promise<CompletionResult | null> => {
    const match = context.matchBefore(PICKER_TRIGGER);
    if (!match) return null;
    const queryStart = match.from + match.text.indexOf('^^') + 2;
    const closing = context.state.sliceDoc(context.pos, context.pos + 2) === ']]' ? 2 : 0;
    const tasks = await loadOpenTasks();
    const options: Completion[] = tasks.map((task) => ({
      label: taskLabel(task.description),
      detail: noteLinkName(task.location.path, files()),
      apply: (view, _completion, _from, to) => insertReference(view, task, match.from, to + closing, files()),
    }));
    return { from: queryStart, options, filter: true };
  };
  return autocompletion({ override: [source], activateOnTyping: true, maxRenderedOptions: 30 });
}
