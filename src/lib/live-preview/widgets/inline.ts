import { sanitizeUrl } from '@braintree/sanitize-url';
import type { StateEffectType } from '@codemirror/state';
import { EditorView, WidgetType } from '@codemirror/view';
import { appendStatusOptions } from '../../tasks';
import { internalLinkButton } from '../links';
import type { BlockRange, FoldTarget, LivePreviewOptions } from '../types';

export class HorizontalRuleWidget extends WidgetType {
  toDOM(): HTMLElement {
    const rule = document.createElement('hr');
    rule.className = 'cm-hr';
    return rule;
  }
}

export class FoldWidget extends WidgetType {
  constructor(
    private readonly target: FoldTarget,
    private readonly collapsed: boolean,
    private readonly toggleFold: StateEffectType<FoldTarget>,
  ) { super(); }
  eq(other: FoldWidget): boolean {
    return other.target.kind === this.target.kind
      && other.target.from === this.target.from
      && other.collapsed === this.collapsed;
  }
  toDOM(view: EditorView): HTMLElement {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `cm-fold-toggle cm-fold-toggle-${this.target.kind}${this.collapsed ? ' is-collapsed' : ''}`;
    const noun = this.target.kind === 'list' ? 'item' : 'section';
    button.title = this.collapsed ? `Expand ${noun}` : `Collapse ${noun}`;
    button.setAttribute('aria-label', button.title);
    button.setAttribute('aria-expanded', String(!this.collapsed));
    button.addEventListener('mousedown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      view.dispatch({ effects: this.toggleFold.of(this.target) });
      view.focus();
    });
    return button;
  }
  ignoreEvent(): boolean { return true; }
}

export class BulletWidget extends WidgetType {
  toDOM(): HTMLElement {
    const bullet = document.createElement('span');
    bullet.className = 'cm-lp-bullet';
    bullet.textContent = '•';
    return bullet;
  }
}

export class FrontmatterWidget extends WidgetType {
  constructor(
    private readonly range: BlockRange,
    private readonly open: boolean,
    private readonly toggleFrontmatter: StateEffectType<boolean>,
  ) { super(); }
  eq(other: FrontmatterWidget): boolean {
    return other.range.from === this.range.from && other.range.to === this.range.to && other.open === this.open;
  }
  toDOM(view: EditorView): HTMLElement {
    const wrapper = document.createElement('div');
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = `cm-fm-collapsed${this.open ? ' is-open' : ''}`;
    chip.textContent = 'Properties';
    chip.title = this.open ? 'Hide properties source' : 'Show properties source';
    chip.setAttribute('aria-expanded', String(this.open));
    chip.addEventListener('mousedown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const { doc } = view.state;
      // Closing moves the caret out, or non-persistent mode would keep the lines revealed.
      const anchor = this.open
        ? Math.min(this.range.to + 1, doc.length)
        : Math.min(doc.lineAt(this.range.from).to + 1, this.range.to);
      view.dispatch({ effects: this.toggleFrontmatter.of(!this.open), selection: { anchor } });
      view.focus();
    });
    wrapper.append(chip);
    return wrapper;
  }
  ignoreEvent(): boolean { return true; }
}

export class TaskWidget extends WidgetType {
  constructor(private readonly symbol: string, private readonly from: number) { super(); }
  eq(other: TaskWidget): boolean { return other.symbol === this.symbol && other.from === this.from; }
  toDOM(view: EditorView): HTMLElement {
    const select = document.createElement('select');
    select.className = 'cm-taskbox';
    select.dataset.status = this.symbol;
    select.title = 'Task status';
    select.setAttribute('aria-label', 'Task status');
    appendStatusOptions(select, this.symbol);
    select.addEventListener('change', () => {
      select.dataset.status = select.value;
      view.dispatch({ changes: { from: this.from, to: this.from + 3, insert: `[${select.value}]` } });
      view.focus();
    });
    return select;
  }
  ignoreEvent(): boolean { return true; }
}

export class WikiLinkWidget extends WidgetType {
  constructor(
    private readonly target: string,
    private readonly label: string,
    private readonly options: LivePreviewOptions,
    private readonly from: number,
  ) { super(); }
  eq(other: WikiLinkWidget): boolean {
    return other.target === this.target && other.label === this.label && other.from === this.from;
  }
  toDOM(): HTMLElement {
    return internalLinkButton(this.label, this.target, this.options, true);
  }
  ignoreEvent(): boolean { return false; }
}

export class HyperlinkWidget extends WidgetType {
  constructor(
    private readonly label: string,
    private readonly href: string,
    private readonly options: LivePreviewOptions,
    private readonly from: number,
  ) { super(); }
  eq(other: HyperlinkWidget): boolean {
    return other.label === this.label && other.href === this.href && other.from === this.from;
  }
  toDOM(): HTMLElement {
    if (!/^(?:https?:|mailto:)/i.test(this.href)) {
      return internalLinkButton(this.label, this.href, this.options, false);
    }
    const anchor = document.createElement('a');
    anchor.className = 'cm-wikilink';
    anchor.textContent = this.label;
    anchor.href = sanitizeUrl(this.href);
    anchor.target = '_blank';
    anchor.rel = 'noopener noreferrer';
    anchor.addEventListener('mousedown', (event) => event.stopPropagation());
    return anchor;
  }
  ignoreEvent(): boolean { return false; }
}
