import { EditorView, WidgetType } from '@codemirror/view';
import { api } from '../../api';
import { renderInlineMarkdown } from '../../markdown-renderer';
import { taskRefBadge } from '../../task-refs';
import { appendStatusOptions } from '../../tasks';
import type { TaskRecord } from '../../types';
import { appendLinkedText, enhanceRenderedMarkdown, renderTaskDescription, resolveInternalLink } from '../links';
import { loadTaskQuery, taskKey, taskQueryCache, taskQueryKey, taskRefCache } from '../task-cache';
import type { LivePreviewOptions } from '../types';

/** Inline rendering of `![[Note#^id]]`: the referenced task itself, toggled in its source note. */
export class TaskRefWidget extends WidgetType {
  constructor(private readonly target: string, private readonly blockId: string, private readonly options: LivePreviewOptions) { super(); }
  eq(other: TaskRefWidget): boolean { return other.target === this.target && other.blockId === this.blockId; }
  toDOM(view: EditorView): HTMLElement {
    const wrapper = document.createElement('span');
    wrapper.className = 'cm-task-ref';
    const resolved = resolveInternalLink(this.target, this.options, true);
    const key = `${resolved.path}#${this.blockId}`;
    const missing = () => {
      wrapper.replaceChildren(`Missing task: ${this.target}#^${this.blockId}`);
      wrapper.className = 'cm-task-ref cm-task-ref-missing';
    };
    const render = (task: TaskRecord) => {
      wrapper.className = `cm-task-ref cm-task-ref-${task.status.type.toLowerCase()}`;
      const status = document.createElement('select');
      status.className = 'cm-taskbox';
      status.dataset.status = task.status.symbol;
      status.title = 'Task status (updates the source note)';
      appendStatusOptions(status, task.status.symbol);
      status.onchange = () => {
        status.dataset.status = status.value;
        wrapper.classList.add('updating');
        void api.updateTask(task.location, { status: status.value })
          .then(load)
          .catch((error: unknown) => { wrapper.classList.remove('updating'); wrapper.title = error instanceof Error ? error.message : 'Could not update task.'; });
      };
      const description = document.createElement('span');
      description.className = 'cm-task-ref-text';
      const openSource = () => this.options.openFile(task.location.path, undefined, task.location.line);
      // Plain text on purpose: only the source chip navigates, so a stray click never leaves the note.
      description.innerHTML = renderInlineMarkdown(task.description);
      enhanceRenderedMarkdown(description, this.options, { sourcePath: task.location.path, stopExternalPropagation: true });
      description.title = `Linked task from ${task.location.path}\n\n${task.description}`;
      const source = document.createElement('button');
      source.type = 'button';
      source.className = 'cm-task-ref-source';
      source.textContent = `↗ ${this.target.split('/').pop() ?? this.target}`;
      source.title = `Linked task: open it in ${task.location.path}`;
      source.onmousedown = (event) => { event.preventDefault(); openSource(); };
      wrapper.replaceChildren(status, description, source);
      const badge = taskRefBadge(task, this.options.currentPath);
      if (badge) {
        const chip = document.createElement('span');
        chip.className = 'cm-task-ref-badge';
        chip.textContent = badge;
        wrapper.append(chip);
      }
      view.requestMeasure();
    };
    const load = () => api.taskByBlockId(resolved.path, this.blockId)
      .then(({ task }) => { taskRefCache.set(key, task); render(task); })
      .catch(() => { taskRefCache.set(key, null); missing(); });
    if (!resolved.exists) { missing(); return wrapper; }
    const cached = taskRefCache.get(key);
    if (cached) render(cached);
    else if (cached === null) missing();
    else wrapper.textContent = 'Loading task…';
    void load();
    return wrapper;
  }
  ignoreEvent(): boolean { return true; }
}

export class TasksBlockWidget extends WidgetType {
  constructor(private readonly query: string, private readonly options: LivePreviewOptions) { super(); }
  eq(other: TasksBlockWidget): boolean { return other.query === this.query; }
  toDOM(view: EditorView): HTMLElement {
    const wrapper = document.createElement('section'); wrapper.className = 'cm-tasks-query'; wrapper.textContent = 'Loading tasks…';
    const render = (tasks: TaskRecord[], errors: string[]) => {
      wrapper.replaceChildren();
      if (errors.length) {
        const warning = document.createElement('div'); warning.className = 'cm-tasks-warning'; warning.setAttribute('role', 'alert');
        const title = document.createElement('strong'); title.textContent = 'Unsupported Tasks query';
        const list = document.createElement('ul');
        for (const error of errors) { const item = document.createElement('li'); item.textContent = error; list.append(item); }
        warning.append(title, list); wrapper.append(warning);
      }
      if (!tasks.length && !errors.length) { wrapper.textContent = 'No tasks found.'; return; }
      const taskRow = (task: TaskRecord): HTMLElement => {
        const row = document.createElement('div'); row.className = 'cm-tasks-row'; row.dataset.taskKey = taskKey(task);
        if (task.indent) row.style.paddingInlineStart = `${Math.min(task.indent, 24)}px`;
        const status = document.createElement('select');
        status.className = 'cm-tasks-status';
        status.dataset.status = task.status.symbol;
        status.title = 'Status';
        appendStatusOptions(status, task.status.symbol);
        const priority = document.createElement('select');
        priority.title = 'Priority';
        for (const value of ['', '⏫', '🔼', '🔺', '⏬', '🔽']) { const option = document.createElement('option'); option.value = value; option.textContent = value || '–'; option.selected = (task.priority || '') === value; priority.append(option); }
        const description = document.createElement('div'); description.className = 'cm-tasks-description';
        renderTaskDescription(
          description,
          task.description,
          this.options,
          task.location.path,
          () => this.options.openFile(task.location.path, undefined, task.location.line),
        );
        const dateField = task.dates.due ? 'due' : task.dates.scheduled ? 'scheduled' : task.dates.start ? 'start' : 'due';
        const date = document.createElement('input'); date.type = 'date'; date.value = task.dates[dateField] || ''; date.title = `${dateField[0].toUpperCase()}${dateField.slice(1)} date`;
        const tooltip = document.createElement('div'); tooltip.className = 'cm-tasks-tooltip'; tooltip.setAttribute('role', 'tooltip'); tooltip.textContent = description.textContent || task.description;
        const update = (patch: Record<string, string | null>) => {
          row.classList.add('updating');
          return api.updateTask(task.location, patch)
            .then(() => loadTaskQuery(this.query, this.options.currentPath, true))
            .then((result) => render(result.tasks, result.errors))
            .catch((error: unknown) => { row.classList.remove('updating'); const warning = document.createElement('p'); warning.className = 'cm-tasks-error'; warning.textContent = error instanceof Error ? error.message : 'Could not update task.'; wrapper.prepend(warning); view.requestMeasure(); });
        };
        status.onchange = () => { status.dataset.status = status.value; void update({ status: status.value }); };
        priority.onchange = () => void update({ priority: priority.value || null });
        date.onchange = () => void update({ [dateField]: date.value || null });
        row.append(status, description, priority, date, tooltip);
        return row;
      };
      const appendGroups = (container: HTMLElement, groupedTasks: TaskRecord[], depth: number): void => {
        const groups = new Map<string, TaskRecord[]>();
        const ungrouped: TaskRecord[] = [];
        for (const task of groupedTasks) {
          const group = task.groups?.[depth];
          if (!group) ungrouped.push(task);
          else groups.set(group, [...(groups.get(group) || []), task]);
        }
        for (const task of ungrouped) container.append(taskRow(task));
        for (const [name, members] of groups) {
          const section = document.createElement('section'); section.className = 'cm-tasks-group';
          const heading = document.createElement('h4'); heading.className = `cm-tasks-group-level-${Math.min(depth, 3)}`;
          appendLinkedText(heading, name, this.options, members[0].location.path);
          const body = document.createElement('div'); body.className = 'cm-tasks-group-body';
          section.append(heading, body); container.append(section);
          appendGroups(body, members, depth + 1);
        }
      };
      appendGroups(wrapper, tasks, 0);
      view.requestMeasure();
    };
    const cached = taskQueryCache.get(taskQueryKey(this.query, this.options.currentPath));
    if (cached) render(cached.tasks, cached.errors);
    void loadTaskQuery(this.query, this.options.currentPath)
      .then((result) => { if (!cached || JSON.stringify(result) !== JSON.stringify(cached)) render(result.tasks, result.errors); })
      .catch((error: unknown) => { if (!cached) wrapper.textContent = error instanceof Error ? error.message : 'Could not load tasks.'; });
    return wrapper;
  }
  ignoreEvent(): boolean { return true; }
}
