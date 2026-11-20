import { indentUnit } from '@codemirror/language';
import { markdown } from '@codemirror/lang-markdown';
import { EditorState, type StateCommand } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import {
  deleteListMarkup,
  foldedListItems,
  indentListItems,
  insertListNewline,
  outdentListItems,
} from './list-edit';
import { ObsidianGFM } from './tasks';

// `|` marks the caret.
function editor(source: string, folded: number[] = []): EditorState {
  const anchor = source.indexOf('|');
  const doc = source.replace('|', '');
  return EditorState.create({
    doc,
    selection: { anchor },
    extensions: [
      EditorState.tabSize.of(4),
      indentUnit.of('\t'),
      markdown({ extensions: ObsidianGFM }),
      foldedListItems.of(folded),
    ],
  });
}

function run(command: StateCommand, state: EditorState): string | false {
  let result = state;
  if (!command({ state, dispatch: (transaction) => { result = transaction.state; } })) return false;
  const doc = result.doc.toString();
  const head = result.selection.main.head;
  return `${doc.slice(0, head)}|${doc.slice(head)}`;
}

describe('indentListItems', () => {
  it('nests an item together with its children', () => {
    expect(run(indentListItems, editor('- a\n- b|\n\t- c'))).toBe('- a\n\t- b|\n\t\t- c');
  });

  it('refuses to nest an item with no preceding sibling', () => {
    expect(run(indentListItems, editor('- a\n\t- b|'))).toBe('- a\n\t- b|');
  });

  it('starts a new ordered sublist at 1 and renumbers the outer list', () => {
    expect(run(indentListItems, editor('1. a\n2. b|\n3. c'))).toBe('1. a\n\t1. b|\n2. c');
  });

  it('indents every selected item', () => {
    let state = editor('- a\n- b\n- c');
    state = state.update({ selection: { anchor: 4, head: 11 } }).state;
    expect(run(indentListItems, state)).toBe('- a\n\t- b\n\t- c|');
  });

  it('leaves non-list lines to the default Tab', () => {
    expect(run(indentListItems, editor('plain| text'))).toBe(false);
  });
});

describe('outdentListItems', () => {
  it('moves an item up a level together with its children', () => {
    expect(run(outdentListItems, editor('- a\n\t- b|\n\t\t- c'))).toBe('- a\n- b|\n\t- c');
  });

  it('handles space indentation', () => {
    expect(run(outdentListItems, editor('- a\n  - b|\n    - c'))).toBe('- a\n- b|\n  - c');
  });

  it('does nothing on a top-level item', () => {
    expect(run(outdentListItems, editor('- a|'))).toBe('- a|');
  });

  it('renumbers the list the item joins and the one it leaves', () => {
    expect(run(outdentListItems, editor('1. p\n\t1. a\n\t2. b|\n\t3. c\n2. q')))
      .toBe('1. p\n\t1. a\n2. b|\n\t1. c\n3. q');
  });
});

describe('deleteListMarkup', () => {
  it('removes only the checkbox and keeps the indentation', () => {
    expect(run(deleteListMarkup, editor('- a\n\t- [ ] |foo'))).toBe('- a\n\t- |foo');
    expect(run(deleteListMarkup, editor('- a\n\t- [x] |'))).toBe('- a\n\t- |');
  });

  it('then removes the marker, keeping the indentation and lifting the children', () => {
    expect(run(deleteListMarkup, editor('- a\n\t- |foo\n\t\t- c'))).toBe('- a\n\t|foo\n\t- c');
  });

  it('removes a number and renumbers the rest of the list', () => {
    expect(run(deleteListMarkup, editor('1. a\n2. |b\n3. c'))).toBe('1. a\n|b\n2. c');
  });

  it('removes a top-level marker and lifts its children', () => {
    expect(run(deleteListMarkup, editor('- |foo\n\t- c'))).toBe('|foo\n- c');
  });

  it('ignores a caret inside the text', () => {
    expect(run(deleteListMarkup, editor('- fo|o'))).toBe(false);
  });

  it('removes one indent level from a marker-less line deeper than its item\'s text', () => {
    expect(run(deleteListMarkup, editor('- a\n\t- b\n\t\t\t|text'))).toBe('- a\n\t- b\n\t\t|text');
    expect(run(deleteListMarkup, editor('- a\n  - b\n        |text'))).toBe('- a\n  - b\n    |text');
  });

  it('joins a marker-less line aligned with its item\'s text to the line above', () => {
    expect(run(deleteListMarkup, editor('- a\n\t- b\n\t  |text'))).toBe('- a\n\t- b|text');
  });

  it('leaves indented lines outside lists to the default Backspace', () => {
    expect(run(deleteListMarkup, editor('para\n\t|text'))).toBe(false);
  });
});

describe('insertListNewline', () => {
  it('outdents an empty nested item', () => {
    expect(run(insertListNewline, editor('- a\n\t- [ ] b\n\t- [ ] |'))).toBe('- a\n\t- [ ] b\n- [ ] |');
  });

  it('removes the marker of an empty top-level item', () => {
    expect(run(insertListNewline, editor('- a\n- |'))).toBe('- a\n|');
  });

  it('adds the sibling of a folded item after its children', () => {
    expect(run(insertListNewline, editor('1. a|\n\t- b\n2. c', [0]))).toBe('1. a\n\t- b\n2. |\n3. c');
  });

  it('leaves non-empty, unfolded items to the default Enter', () => {
    expect(run(insertListNewline, editor('- a|\n\t- b'))).toBe(false);
  });
});
