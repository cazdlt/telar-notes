import { describe, expect, it } from 'vitest';
import { detectSearchMode, matchGlobalShortcut } from './shortcuts';

describe('shortcuts', () => {
  it('matches global shortcuts and Escape on graph view', () => {
    expect(
      matchGlobalShortcut({ key: 'Escape', metaKey: false, ctrlKey: false, shiftKey: false }, { graphOpen: true, searchOpen: false }),
    ).toBe('close-graph');
    expect(
      matchGlobalShortcut({ key: 'Escape', metaKey: false, ctrlKey: false, shiftKey: false }, { graphOpen: false, searchOpen: false }),
    ).toBeNull();
    expect(
      matchGlobalShortcut({ key: 'F', metaKey: true, ctrlKey: false, shiftKey: true }, { graphOpen: false, searchOpen: false }),
    ).toBe('search-content');
    expect(
      matchGlobalShortcut({ key: 'p', metaKey: false, ctrlKey: true, shiftKey: true }, { graphOpen: false, searchOpen: false }),
    ).toBe('search-title');
    expect(
      matchGlobalShortcut({ key: 'f', metaKey: true, ctrlKey: false, shiftKey: false }, { graphOpen: false, searchOpen: true }),
    ).toBeNull();
    expect(
      matchGlobalShortcut({ key: 'f', metaKey: true, ctrlKey: false, shiftKey: false }, { graphOpen: false, searchOpen: false }),
    ).toBe('find-in-note');
    expect(
      matchGlobalShortcut({ key: '[', metaKey: true, ctrlKey: false, shiftKey: false }, { graphOpen: false, searchOpen: false }),
    ).toBe('history-back');
    expect(
      matchGlobalShortcut({ key: ']', metaKey: true, ctrlKey: false, shiftKey: false }, { graphOpen: false, searchOpen: false }),
    ).toBe('history-forward');
  });

  it('detects search prefix modes and falls back cleanly', () => {
    expect(detectSearchMode('/hello', 'all')).toEqual({ query: 'hello', mode: 'content' });
    expect(detectSearchMode('[[Note', 'all')).toEqual({ query: 'Note', mode: 'links' });
    expect(detectSearchMode('#tag', 'all')).toEqual({ query: 'tag', mode: 'tags' });
    expect(detectSearchMode('plain', 'title')).toEqual({ query: 'plain', mode: 'title' });
  });
});
