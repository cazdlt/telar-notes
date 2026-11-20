import { syntaxTree } from '@codemirror/language';
import { StateEffect, StateField, type Extension } from '@codemirror/state';
import { EditorView, ViewPlugin } from '@codemirror/view';
import { foldedListItems } from '../list-edit';
import { buildDecorations } from './decorations';
import { foldSections } from './folding';
import {
  revealBlock,
  type BlockRange,
  type FoldTarget,
  type LivePreviewOptions,
  type LivePreviewState,
} from './types';

export type { LinkedTextPart, LivePreviewOptions } from './types';
export { buildDecorations } from './decorations';
export { fencedCodeText } from './folding';
export { linkedTextParts } from './links';
export { cachedTaskQuery, loadTaskQuery, taskKey } from './task-cache';

export function createLivePreview(options: LivePreviewOptions): Extension {
  const toggleFold = StateEffect.define<FoldTarget>();
  const toggleFrontmatter = StateEffect.define<boolean>();
  return StateField.define<LivePreviewState>({
    create(state) {
      const folded = foldSections(state)
        .filter((section) => section.defaultCollapsed)
        .map(({ kind, from }) => ({ kind, from }));
      return { folded, frontmatterOpen: false, revealedBlocks: [], ...buildDecorations(state, options, folded, toggleFold, false, toggleFrontmatter) };
    },
    update(value, transaction) {
      const changedTree = syntaxTree(transaction.state) !== syntaxTree(transaction.startState);
      if (!transaction.docChanged && !transaction.selection && !changedTree
        && !transaction.effects.some((effect) => effect.is(toggleFold) || effect.is(toggleFrontmatter) || effect.is(revealBlock))) return value;

      const sections = foldSections(transaction.state);
      const sectionKeys = new Set(sections.map((section) => `${section.kind}:${section.from}`));
      let folded = value.folded
        .map((target) => transaction.docChanged
          ? { ...target, from: transaction.changes.mapPos(target.from, target.kind === 'list' ? -1 : 1) }
          : target)
        .filter((target) => sectionKeys.has(`${target.kind}:${target.from}`));

      for (const effect of transaction.effects) {
        if (!effect.is(toggleFold)) continue;
        const key = `${effect.value.kind}:${effect.value.from}`;
        folded = folded.some((target) => `${target.kind}:${target.from}` === key)
          ? folded.filter((target) => `${target.kind}:${target.from}` !== key)
          : [...folded, effect.value];
      }

      if (transaction.selection) {
        const selectedLines = transaction.state.selection.ranges.map((range) => ({
          first: transaction.state.doc.lineAt(range.from).number,
          last: transaction.state.doc.lineAt(range.to).number,
        }));
        folded = folded.filter((target) => {
          const section = sections.find(
            (candidate) => candidate.kind === target.kind && candidate.from === target.from,
          );
          return !section || !selectedLines.some(
            (selection) => selection.last > section.first && selection.first <= section.last,
          );
        });
      }

      let { frontmatterOpen } = value;
      for (const effect of transaction.effects) if (effect.is(toggleFrontmatter)) frontmatterOpen = effect.value;

      const { state } = transaction;
      const revealedBlocks = [
        ...value.revealedBlocks.map((block) => ({
          from: transaction.changes.mapPos(block.from, -1),
          to: transaction.changes.mapPos(block.to, 1),
        })),
        ...transaction.effects.filter((effect) => effect.is(revealBlock)).map((effect) => effect.value),
      ].filter((block) => state.selection.ranges.some((range) => range.to >= block.from && range.from <= block.to));
      return {
        folded,
        frontmatterOpen,
        revealedBlocks,
        ...buildDecorations(state, options, folded, toggleFold, frontmatterOpen, toggleFrontmatter, revealedBlocks),
      };
    },
    provide: (field) => [
      EditorView.decorations.from(field, (value) => value.decorations),
      foldedListItems.from(field, (value) => value.folded.filter((target) => target.kind === 'list').map((target) => target.from)),
      EditorView.atomicRanges.of((view) => view.state.field(field).atomic),
      altClickEditing(field, options),
    ],
  });
}

// Rendered elements that Alt/Option-click turns back into their markdown source instead of
// following or toggling them.
const SOURCE_EDITABLE = '.cm-wikilink, .cm-task-ref, .cm-table-wrap, .cm-tasks-query, .cm-embed, .cm-mermaid';

/** Alt-click reveals a rendered element's source; holding Alt outlines what can be revealed. */
function altClickEditing(field: StateField<LivePreviewState>, options: LivePreviewOptions): Extension {
  return ViewPlugin.define((view) => {
    const setHeld = (held: boolean) => view.dom.classList.toggle('cm-alt-edit', held && !options.reading());
    const onKey = (event: KeyboardEvent) => setHeld(event.altKey);
    const onMove = (event: MouseEvent) => setHeld(event.altKey);
    const onBlur = () => setHeld(false);
    const editable = (event: MouseEvent): Element | null =>
      event.altKey && !options.reading() && event.target instanceof Element ? event.target.closest(SOURCE_EDITABLE) : null;
    // Capture runs before the widgets' own handlers, which would otherwise navigate or toggle.
    const onMouseDown = (event: MouseEvent) => {
      const element = editable(event);
      if (!element || event.button !== 0) return;
      const pos = view.posAtDOM(element);
      const hits: BlockRange[] = [];
      view.state.field(field).atomic.between(pos, pos, (from, to) => { hits.push({ from, to }); });
      const target = hits.find((hit) => hit.from === pos) ?? hits[0];
      if (!target) return;
      event.preventDefault();
      event.stopPropagation();
      view.dispatch({ selection: { anchor: target.from }, effects: revealBlock.of(target) });
      view.focus();
    };
    // Chrome and Safari download a link's target on Alt-click.
    const onClick = (event: MouseEvent) => {
      if (event.altKey && event.target instanceof Element && event.target.closest('a')) event.preventDefault();
    };
    view.contentDOM.addEventListener('mousedown', onMouseDown, true);
    view.contentDOM.addEventListener('click', onClick, true);
    view.dom.addEventListener('mousemove', onMove);
    window.addEventListener('keydown', onKey);
    window.addEventListener('keyup', onKey);
    window.addEventListener('blur', onBlur);
    return {
      destroy() {
        view.contentDOM.removeEventListener('mousedown', onMouseDown, true);
        view.contentDOM.removeEventListener('click', onClick, true);
        view.dom.removeEventListener('mousemove', onMove);
        window.removeEventListener('keydown', onKey);
        window.removeEventListener('keyup', onKey);
        window.removeEventListener('blur', onBlur);
      },
    };
  });
}
