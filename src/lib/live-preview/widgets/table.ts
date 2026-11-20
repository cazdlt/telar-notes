import { EditorView, WidgetType } from '@codemirror/view';
import { renderMarkdown } from '../../markdown-renderer';
import { editTable, tableColumns, type TableEdit } from '../../table-edit';
import { enhanceRenderedMarkdown } from '../links';
import type { LivePreviewOptions } from '../types';

type TableMenuItem = { label: string; run: () => void; danger?: boolean; disabled?: boolean };

function openTableMenu(x: number, y: number, items: TableMenuItem[]): void {
  document.querySelector('.cm-table-menu')?.remove();
  const menu = document.createElement('div');
  menu.className = 'cm-table-menu';
  menu.setAttribute('role', 'menu');
  const close = () => {
    menu.remove();
    window.removeEventListener('mousedown', outside, true);
    window.removeEventListener('keydown', escape, true);
    window.removeEventListener('blur', close);
    window.removeEventListener('scroll', close, true);
  };
  const outside = (event: MouseEvent) => { if (!menu.contains(event.target as Node)) close(); };
  const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
  for (const item of items) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `tcm-item${item.danger ? ' danger' : ''}`;
    button.setAttribute('role', 'menuitem');
    button.textContent = item.label;
    button.disabled = item.disabled ?? false;
    button.addEventListener('mousedown', (event) => event.preventDefault());
    button.addEventListener('click', () => { close(); item.run(); });
    menu.append(button);
  }
  document.body.append(menu);
  const { width, height } = menu.getBoundingClientRect();
  menu.style.left = `${Math.min(x, window.innerWidth - width - 8)}px`;
  menu.style.top = `${Math.min(y, window.innerHeight - height - 8)}px`;
  window.addEventListener('mousedown', outside, true);
  window.addEventListener('keydown', escape, true);
  window.addEventListener('blur', close);
  window.addEventListener('scroll', close, true);
}

export class TableWidget extends WidgetType {
  constructor(private readonly markdown: string, private readonly options: LivePreviewOptions) { super(); }
  eq(other: TableWidget): boolean { return other.markdown === this.markdown; }
  toDOM(view: EditorView): HTMLElement {
    const wrapper = document.createElement('div');
    wrapper.className = 'cm-table-wrap';
    const box = document.createElement('div');
    box.className = 'cm-table-box';
    box.innerHTML = renderMarkdown(this.markdown);
    const table = box.querySelector('table');
    if (table) table.className = 'cm-table';
    enhanceRenderedMarkdown(box, this.options, { table: true });
    wrapper.append(box);
    if (!table) return wrapper;
    const rows = table.rows.length;
    const columns = tableColumns(this.markdown);
    box.append(
      this.addButton('cm-table-add-row', 'Add row', view, { kind: 'insert-row', after: rows - 1 }),
      this.addButton('cm-table-add-col', 'Add column', view, { kind: 'insert-column', after: columns - 1 }),
    );
    // A right-click would otherwise move the caret into the table and reveal its source.
    table.addEventListener('mousedown', (event) => {
      if (event.button === 2 && !this.options.reading()) { event.preventDefault(); event.stopPropagation(); }
    });
    table.addEventListener('contextmenu', (event) => {
      const cell = event.target instanceof Element ? event.target.closest('th, td') : null;
      const row = cell?.parentElement;
      if (!cell || !(row instanceof HTMLTableRowElement) || this.options.reading()) return;
      event.preventDefault();
      event.stopPropagation();
      const column = (cell as HTMLTableCellElement).cellIndex;
      openTableMenu(event.clientX, event.clientY, [
        { label: 'Insert row below', run: () => this.apply(view, wrapper, { kind: 'insert-row', after: row.rowIndex }) },
        { label: 'Insert column right', run: () => this.apply(view, wrapper, { kind: 'insert-column', after: column }) },
        { label: 'Delete row', danger: true, disabled: row.rowIndex === 0, run: () => this.apply(view, wrapper, { kind: 'delete-row', row: row.rowIndex }) },
        { label: 'Delete column', danger: true, disabled: columns < 2, run: () => this.apply(view, wrapper, { kind: 'delete-column', column }) },
      ]);
    });
    return wrapper;
  }
  private addButton(className: string, label: string, view: EditorView, edit: TableEdit): HTMLButtonElement {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `cm-table-add ${className}`;
    button.title = label;
    button.setAttribute('aria-label', label);
    button.textContent = '+';
    button.addEventListener('mousedown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.button === 0 && !event.altKey) this.apply(view, button.closest('.cm-table-wrap')!, edit);
    });
    return button;
  }
  private apply(view: EditorView, wrapper: Element, edit: TableEdit): void {
    if (this.options.reading()) return;
    const from = view.posAtDOM(wrapper);
    const to = from + this.markdown.length;
    // The document may have moved on since this widget was drawn.
    if (view.state.sliceDoc(from, to) !== this.markdown) return;
    view.dispatch({ changes: { from, to, insert: editTable(this.markdown, edit) } });
  }
  ignoreEvent(): boolean { return false; }
}
