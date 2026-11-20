import { describe, expect, it } from 'vitest';

import { dropRecent, isRecentFile, loadRecent, pushRecent, RECENT_LIMIT, relativeTime, remapRecent, saveRecent } from './recent';

const entries = (...paths: string[]) => paths.map((path, index) => ({ path, openedAt: index }));

describe('pushRecent', () => {
  it('moves a reopened path to the front without duplicating it', () => {
    const list = pushRecent(entries('a.md', 'b.md', 'c.md'), 'b.md', 99);
    expect(list).toEqual([{ path: 'b.md', openedAt: 99 }, { path: 'a.md', openedAt: 0 }, { path: 'c.md', openedAt: 2 }]);
  });

  it('caps the list', () => {
    const full = entries(...Array.from({ length: RECENT_LIMIT }, (_, index) => `${index}.md`));
    const list = pushRecent(full, 'new.md');
    expect(list).toHaveLength(RECENT_LIMIT);
    expect(list[0].path).toBe('new.md');
    expect(list.at(-1)?.path).toBe(`${RECENT_LIMIT - 2}.md`);
  });
});

describe('remapRecent', () => {
  it('follows a renamed file', () => {
    expect(remapRecent(entries('a.md', 'b.md'), 'a.md', 'z.md').map((entry) => entry.path)).toEqual(['z.md', 'b.md']);
  });

  it('follows a moved folder without touching sibling prefixes', () => {
    const list = remapRecent(entries('notes/a.md', 'notes-old/b.md', 'notes'), 'notes', 'archive/notes');
    expect(list.map((entry) => entry.path)).toEqual(['archive/notes/a.md', 'notes-old/b.md', 'archive/notes']);
  });
});

describe('dropRecent', () => {
  it('removes a file and everything under a folder', () => {
    expect(dropRecent(entries('a.md', 'dir/b.md', 'dir2/c.md'), 'dir').map((entry) => entry.path)).toEqual(['a.md', 'dir2/c.md']);
  });
});

describe('loadRecent / saveRecent', () => {
  const storage = (value: string | null) => ({ getItem: () => value });

  it('round-trips per vault', () => {
    const store = new Map<string, string>();
    saveRecent('work', entries('a.md'), { setItem: (key, value) => store.set(key, value) });
    expect(store.has('telar-recent:work')).toBe(true);
    expect(loadRecent('work', { getItem: (key) => store.get(key) ?? null })).toEqual(entries('a.md'));
    expect(loadRecent('personal', { getItem: (key) => store.get(key) ?? null })).toEqual([]);
  });

  it('ignores malformed storage', () => {
    expect(loadRecent('work', storage('{not json'))).toEqual([]);
    expect(loadRecent('work', storage('{"path":"a.md"}'))).toEqual([]);
    expect(loadRecent('work', storage('[null, {"path":1,"openedAt":2}, {"path":"a.md","openedAt":3}, "x"]')))
      .toEqual([{ path: 'a.md', openedAt: 3 }]);
  });
});

describe('isRecentFile', () => {
  it('accepts notes, drawings and images and rejects everything else', () => {
    for (const path of ['a.md', 'b.markdown', 'd.excalidraw', 'd.excalidraw.md', 'i.PNG', 'i.jpeg', 'i.svg']) expect(isRecentFile(path)).toBe(true);
    for (const path of ['scripts/__pycache__/cli.cpython-312.pyc', 'scripts/cli.py', 'scripts/vault', 'data.json']) expect(isRecentFile(path)).toBe(false);
  });
});

describe('relativeTime', () => {
  const now = new Date(2026, 8, 28, 12).getTime();

  it('uses compact units within a week', () => {
    expect(relativeTime(now - 10_000, now)).toBe('now');
    expect(relativeTime(now - 2 * 60_000, now)).toBe('2m');
    expect(relativeTime(now - 3 * 3_600_000, now)).toBe('3h');
    expect(relativeTime(now - 4 * 86_400_000, now)).toBe('4d');
  });

  it('falls back to a date, with the year only when it differs', () => {
    expect(relativeTime(new Date(2026, 8, 1).getTime(), now)).toBe('Sep 1');
    expect(relativeTime(new Date(2025, 8, 21).getTime(), now)).toBe('Sep 21, 2025');
  });
});
