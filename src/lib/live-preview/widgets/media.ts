import { EditorView, WidgetType } from '@codemirror/view';
import { api } from '../../api';
import { codeLanguageOptions, fenceInfoChange } from '../../code-lang';
import { openDiagramViewer } from '../../diagram-viewer';
import { excalidrawRenderer } from '../../excalidraw-renderer';
import { sanitizeSvg } from '../../markdown-renderer';
import { mermaidRenderer } from '../../mermaid-renderer';
import { resolveVaultPath } from '../../paths';
import { fencedBlockAt } from '../folding';
import { revealBlock, type LivePreviewOptions } from '../types';

export class CopyButtonWidget extends WidgetType {
  constructor(private readonly code: string) { super(); }
  eq(other: CopyButtonWidget): boolean { return other.code === this.code; }
  toDOM(): HTMLElement {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cm-cb-copy';
    button.textContent = 'Copy';
    button.addEventListener('mousedown', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await navigator.clipboard.writeText(this.code);
      button.textContent = 'Copied';
      button.classList.add('ok');
      window.setTimeout(() => { button.textContent = 'Copy'; button.classList.remove('ok'); }, 1200);
    });
    return button;
  }
  ignoreEvent(): boolean { return true; }
}

export class LanguageSelectWidget extends WidgetType {
  constructor(
    private readonly language: string,
    private readonly lineFrom: number,
    private readonly reading: boolean,
  ) { super(); }

  eq(other: LanguageSelectWidget): boolean {
    return other.language === this.language && other.lineFrom === this.lineFrom && other.reading === this.reading;
  }

  toDOM(view: EditorView): HTMLElement {
    const select = document.createElement('select');
    select.className = 'cm-cb-lang';
    select.setAttribute('aria-label', 'Code block language');
    select.disabled = this.reading;
    for (const option of codeLanguageOptions(this.language)) {
      const item = document.createElement('option');
      item.value = option.id;
      item.textContent = option.label;
      if (option.id === this.language) item.selected = true;
      select.append(item);
    }
    select.addEventListener('mousedown', (event) => { event.stopPropagation(); });
    select.addEventListener('change', () => {
      const line = view.state.doc.lineAt(this.lineFrom);
      const change = fenceInfoChange(line.text, line.from, select.value);
      if (!change) return;
      view.dispatch({ changes: change });
    });
    return select;
  }

  ignoreEvent(): boolean { return true; }
}

export class MermaidWidget extends WidgetType {
  constructor(private readonly code: string, private readonly from: number) { super(); }
  eq(other: MermaidWidget): boolean { return other.code === this.code && other.from === this.from; }
  toDOM(view: EditorView): HTMLElement {
    const wrapper = document.createElement('div');
    wrapper.className = 'cm-mermaid';
    const diagram = document.createElement('div');
    diagram.textContent = 'Rendering diagram…';
    const edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'cm-mermaid-edit';
    edit.textContent = 'Edit';
    edit.addEventListener('mousedown', (event) => {
      event.preventDefault();
      const line = view.state.doc.lineAt(this.from);
      view.dispatch({
        effects: revealBlock.of(fencedBlockAt(view.state, this.from) ?? { from: this.from, to: this.from }),
        selection: { anchor: Math.min(line.to + 1, view.state.doc.length) },
      });
      view.focus();
    });
    const expand = document.createElement('button');
    expand.type = 'button';
    expand.className = 'cm-mermaid-expand';
    expand.textContent = 'Expand';
    expand.addEventListener('mousedown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (diagram.querySelector('svg')) openDiagramViewer(diagram.innerHTML);
    });
    void mermaidRenderer.render(this.code).then((svg) => {
      if (!wrapper.isConnected) return;
      diagram.innerHTML = sanitizeSvg(svg);
      view.requestMeasure();
    }).catch((error: unknown) => {
      diagram.textContent = error instanceof Error ? error.message : 'Invalid Mermaid diagram';
      diagram.className = 'cm-diagram-err';
      view.requestMeasure();
    });
    wrapper.append(diagram, edit, expand);
    return wrapper;
  }
  ignoreEvent(): boolean { return false; }
}

export class EmbedWidget extends WidgetType {
  constructor(
    readonly target: string,
    private readonly options: LivePreviewOptions,
    readonly inline = false,
  ) { super(); }
  eq(other: EmbedWidget): boolean { return other.target === this.target && other.inline === this.inline; }
  toDOM(view: EditorView): HTMLElement {
    const wrapper = document.createElement(this.inline ? 'span' : 'div');
    wrapper.className = this.inline ? 'cm-embed cm-embed-inline' : 'cm-embed';
    const resolved = resolveVaultPath(this.target, this.options.currentPath, this.options.files());
    if (!resolved.exists) {
      wrapper.textContent = `Missing attachment: ${this.target}`;
      wrapper.classList.add('cm-diagram-err');
      return wrapper;
    }
    if (/\.(png|jpe?g|gif|webp|svg)$/i.test(resolved.path)) {
      const image = document.createElement('img');
      image.src = api.raw(resolved.path);
      image.alt = this.target;
      image.loading = 'lazy';
      image.addEventListener('load', () => view.requestMeasure());
      wrapper.append(image);
      return wrapper;
    }
    if (this.options.drawings() && /\.excalidraw(?:\.md)?$/i.test(resolved.path)) {
      const diagram = document.createElement('div');
      diagram.className = 'cm-excalidraw-embed';
      diagram.style.maxWidth = `${this.options.drawingWidth()}px`;
      diagram.title = 'Open drawing';
      diagram.textContent = 'Rendering drawing…';
      diagram.addEventListener('mousedown', (event) => {
        event.preventDefault();
        this.options.openDrawing(resolved.path);
      });
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'cm-excalidraw-edit';
      edit.textContent = 'Edit drawing';
      edit.addEventListener('mousedown', (event) => {
        event.preventDefault();
        this.options.openDrawing(resolved.path);
      });
      void excalidrawRenderer.render(resolved.path).then((svg) => {
        if (!wrapper.isConnected) return;
        diagram.innerHTML = svg;
        diagram.querySelector('svg')?.classList.add('cm-excalidraw-svg');
        view.requestMeasure();
      }).catch((error: unknown) => {
        diagram.textContent = error instanceof Error ? error.message : 'Could not render drawing.';
        diagram.className = 'cm-excalidraw-embed cm-diagram-err';
        view.requestMeasure();
      });
      wrapper.append(diagram, edit);
      return wrapper;
    }
    const attachment = document.createElement('a');
    attachment.href = api.raw(resolved.path);
    attachment.target = '_blank';
    attachment.rel = 'noopener noreferrer';
    attachment.textContent = this.target;
    wrapper.append(attachment);
    return wrapper;
  }
  ignoreEvent(): boolean { return false; }
}
