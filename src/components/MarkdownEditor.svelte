<script lang="ts" module>
  export type EditorViewState = { top: number; anchor: number };
</script>

<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { HighlightStyle, indentUnit, syntaxHighlighting } from '@codemirror/language';
  import { EditorState } from '@codemirror/state';
  import { drawSelection, EditorView, keymap } from '@codemirror/view';
  import {
    defaultKeymap,
    history,
    historyKeymap,
    indentWithTab,
    redo,
    undo,
  } from '@codemirror/commands';
  import {
    closeSearchPanel,
    highlightSelectionMatches,
    openSearchPanel,
    search,
    searchKeymap,
  } from '@codemirror/search';
  import { markdown } from '@codemirror/lang-markdown';
  import { languages } from '@codemirror/language-data';
  import { tags } from '@lezer/highlight';
  import { autocompletion } from '@codemirror/autocomplete';
  import { createLivePreview } from '../lib/live-preview';
  import { ObsidianGFM } from '../lib/tasks';
  import { loadOpenTasksWithId, taskReferenceCompletionSource } from '../lib/task-refs';
  import { taskAutoSuggest } from '../lib/task-suggest';
  import { tagAutoSuggest } from '../lib/tag-suggest';
  import { codeLanguageCompletionSource } from '../lib/code-lang';
  import { taskQueryFind } from '../lib/task-query-find';
  import { listEditing } from '../lib/list-edit';
  let {
    content = '',
    currentPath,
    files,
    reading,
    persistent,
    drawings,
    drawingWidth,
    onChange,
    onOpenFile,
    onOpenDrawing,
    onMissingLink,
  }: {
    content?: string;
    currentPath: string;
    files: () => ReadonlySet<string>;
    reading: () => boolean;
    persistent: () => boolean;
    drawings: () => boolean;
    drawingWidth: () => number;
    onChange: (value: string) => void;
    onOpenFile: (path: string, anchor?: string, line?: number) => void;
    onOpenDrawing: (path: string) => void;
    onMissingLink: (target: string) => void;
  } = $props();
  let host: HTMLDivElement;
  let view: EditorView | undefined;
  const codeHighlightStyle = HighlightStyle.define([
    { tag: [tags.keyword, tags.modifier, tags.operatorKeyword, tags.tagName], color: 'var(--hl-keyword)' },
    { tag: [tags.string, tags.regexp, tags.special(tags.string)], color: 'var(--hl-string)' },
    { tag: [tags.number, tags.bool], color: 'var(--hl-number)' },
    { tag: [tags.null, tags.invalid, tags.atom, tags.self], color: 'var(--hl-null)' },
    { tag: [tags.comment, tags.meta], color: 'var(--text-dim)', fontStyle: 'italic' },
    { tag: [tags.function(tags.variableName), tags.function(tags.propertyName), tags.definition(tags.variableName), tags.definition(tags.propertyName)], color: 'var(--accent)' },
    { tag: [tags.typeName, tags.className, tags.namespace, tags.macroName], color: 'var(--cal-tip)' },
    { tag: [tags.propertyName, tags.attributeName, tags.labelName], color: 'var(--hl-key)' },
    { tag: [tags.operator, tags.punctuation, tags.bracket], color: 'var(--hl-punct)' },
  ]);

  onMount(() => {
    view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: content,
        extensions: [
          // The vault indents with tab characters, so Tab inserts one rather than indentUnit's
          // default two spaces. tabSize counts space widths in a proportional font, so the
          // rendered indent is narrower than the number suggests.
          EditorState.tabSize.of(4),
          indentUnit.of('\t'),
          markdown({ extensions: ObsidianGFM, codeLanguages: languages }),
          syntaxHighlighting(codeHighlightStyle),
          createLivePreview({
            currentPath,
            files,
            reading,
            persistent,
            drawings,
            drawingWidth,
            openFile: onOpenFile,
            openDrawing: onOpenDrawing,
            missingLink: onMissingLink,
          }),
          autocompletion({
            override: [
              taskReferenceCompletionSource(files),
              taskAutoSuggest({ loadTasksWithId: loadOpenTasksWithId }),
              tagAutoSuggest(),
              codeLanguageCompletionSource(),
            ],
            activateOnTyping: true,
            maxRenderedOptions: 30,
          }),
          history(),
          drawSelection(),
          search({ top: true }),
          taskQueryFind(currentPath),
          listEditing(),
          EditorState.phrases.of({
            next: 'Next', previous: 'Previous', all: 'All', 'match case': 'Match case', regexp: 'Regex',
            'by word': 'Whole word', replace: 'Replace', 'replace all': 'Replace all', close: 'Close',
          }),
          highlightSelectionMatches(),
          keymap.of([
            ...defaultKeymap,
            ...historyKeymap,
            ...searchKeymap,
            indentWithTab,
            { key: 'Ctrl-z', run: undo },
            { key: 'Ctrl-Shift-z', run: redo },
            { key: 'Ctrl-y', run: redo },
          ]),
          EditorView.lineWrapping,
          EditorView.updateListener.of((update) => {
            if (update.docChanged) onChange(update.state.doc.toString());
          }),
        ],
      }),
    });
  });

  $effect(() => {
    if (view && content !== view.state.doc.toString()) {
      const anchor = Math.min(view.state.selection.main.anchor, content.length);
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: content },
        selection: { anchor },
      });
    }
  });
  onDestroy(() => view?.destroy());

  function replaceSelection(before: string, after: string) {
    if (!view) return;
    const { from, to } = view.state.selection.main;
    const selected = view.state.sliceDoc(from, to);
    view.dispatch({ changes: { from, to, insert: `${before}${selected}${after}` }, selection: { anchor: from + before.length, head: from + before.length + selected.length } });
    view.focus();
  }
  function insert(text: string, caret = text.length) {
    if (!view) return;
    const { from, to } = view.state.selection.main;
    view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + caret } });
    view.focus();
  }
  function toggleLinePrefix(prefix: string) {
    if (!view) return;
    const { state } = view;
    const lines = [];
    for (let n = state.doc.lineAt(state.selection.main.from).number; n <= state.doc.lineAt(state.selection.main.to).number; n += 1) lines.push(state.doc.line(n));
    const remove = lines.every((line) => line.text.startsWith(prefix));
    view.dispatch({ changes: lines.map((line) => remove ? { from: line.from, to: line.from + prefix.length } : { from: line.from, insert: prefix }) });
    view.focus();
  }
  export function bold() { replaceSelection('**', '**'); }
  export function italic() { replaceSelection('*', '*'); }
  export function strike() { replaceSelection('~~', '~~'); }
  export function link() { replaceSelection('[[', ']]'); }
  export function tag() { insert('#'); }
  export function inlineCode() { replaceSelection('`', '`'); }
  export function codeBlock() {
    if (!view) return;
    const { from } = view.state.selection.main;
    const lead = from === view.state.doc.lineAt(from).from ? '' : '\n';
    replaceSelection(`${lead}\`\`\`\n`, '\n```\n');
  }
  export function task() { toggleLinePrefix('- [ ] '); }
  export function quote() { toggleLinePrefix('> '); }
  export function table() { insert('\n| Column | Column |\n| --- | --- |\n|  |  |\n', 3); }
  export function mermaid() { insert('\n```mermaid\nflowchart TD\n  A[Start] --> B[End]\n```\n', 22); }
  export function insertText(text: string) { insert(text); }
  export function refresh() { view?.dispatch({ selection: view.state.selection }); }
  export function focus() { view?.focus(); }
  export function openFind() { if (view) { view.focus(); openSearchPanel(view); } }
  export function closeFind() { if (view) closeSearchPanel(view); }
  export function value() { return view?.state.doc.toString() ?? content; }
  export function revealAnchor(anchor: string): boolean {
    if (!view) return false;
    const source = view.state.doc;
    const decode = (value: string) => {
      try { return decodeURIComponent(value); } catch { return value; }
    };
    const normalize = (value: string) => decode(value)
      .trim()
      .replace(/^\^/, '')
      .replace(/[*_~`]/g, '')
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '');
    const requested = normalize(anchor);
    for (let number = 1; number <= source.lines; number += 1) {
      const line = source.line(number);
      const block = line.text.match(/(?:^|\s)\^([\w-]+)\s*$/)?.[1];
      const heading = line.text.match(/^\s*#{1,6}\s+(.+?)\s*#*\s*$/)?.[1];
      if ((block && normalize(block) === requested) || (heading && normalize(heading) === requested)) {
        view.dispatch({
          selection: { anchor: line.from },
          effects: EditorView.scrollIntoView(line.from, { y: 'center' }),
        });
        view.focus();
        return true;
      }
    }
    return false;
  }
  /** Top visible position and caret, anchored to the document so they survive reflow. */
  export function viewState(): EditorViewState | undefined {
    if (!view) return undefined;
    const frame = view.scrollDOM.getBoundingClientRect();
    const content = view.contentDOM.getBoundingClientRect();
    if (!frame.height) return undefined;
    const top = view.posAtCoords({ x: content.left + content.width / 2, y: Math.max(frame.top, content.top) + 1 }, false);
    return { top, anchor: view.state.selection.main.anchor };
  }
  export function restoreView(state: EditorViewState): void {
    if (!view) return;
    const clamp = (pos: number) => Math.min(pos, view!.state.doc.length);
    view.dispatch({
      selection: { anchor: clamp(state.anchor) },
      effects: EditorView.scrollIntoView(clamp(state.top), { y: 'start' }),
    });
  }
  export function revealLine(number: number): boolean {
    if (!view || !Number.isInteger(number) || number < 1 || number > view.state.doc.lines) return false;
    const line = view.state.doc.line(number);
    view.dispatch({
      selection: { anchor: line.from },
      effects: EditorView.scrollIntoView(line.from, { y: 'center' }),
    });
    view.focus();
    return true;
  }
</script>
<div bind:this={host} class="cm-host"></div>
<style>.cm-host { height: 100%; overflow: auto; }.cm-host :global(.cm-editor) { min-height: 100%; font-size: var(--editor-font-size, 16px); }</style>
