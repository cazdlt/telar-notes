import { describe, expect, it } from 'vitest';
import {
  GRAPH_ENTRY,
  HISTORY_LIMIT,
  canGoBack,
  canGoForward,
  createHistoryState,
  dropHistory,
  peekHistory,
  recordHistoryVisit,
  remapHistory,
} from './history';

describe('history', () => {
  it('tracks visits, back/forward availability, and truncates forward branch on new visit', () => {
    let state = createHistoryState();
    expect(canGoBack(state)).toBe(false);
    expect(canGoForward(state)).toBe(false);

    state = recordHistoryVisit(state, 'a.md');
    state = recordHistoryVisit(state, 'a.md');
    expect(state).toEqual({ visited: ['a.md'], index: 0 });

    state = recordHistoryVisit(state, 'b.md');
    state = recordHistoryVisit(state, GRAPH_ENTRY);
    expect(canGoBack(state)).toBe(true);
    expect(canGoForward(state)).toBe(false);
    expect(peekHistory(state, -1)).toBe('b.md');

    state = { ...state, index: 1 };
    expect(canGoBack(state)).toBe(true);
    expect(canGoForward(state)).toBe(true);
    expect(peekHistory(state, 1)).toBe(GRAPH_ENTRY);

    state = recordHistoryVisit(state, 'c.md');
    expect(state).toEqual({ visited: ['a.md', 'b.md', 'c.md'], index: 2 });
    expect(canGoForward(state)).toBe(false);
  });

  it('caps history at HISTORY_LIMIT', () => {
    let state = createHistoryState();
    for (let i = 0; i < HISTORY_LIMIT + 10; i += 1) {
      state = recordHistoryVisit(state, `note-${i}.md`);
    }
    expect(state.visited).toHaveLength(HISTORY_LIMIT);
    expect(state.visited[0]).toBe('note-10.md');
    expect(state.index).toBe(HISTORY_LIMIT - 1);
  });

  it('remaps renamed paths and folders without disturbing graph entry', () => {
    let state = createHistoryState();
    state = recordHistoryVisit(state, 'dir/a.md');
    state = recordHistoryVisit(state, GRAPH_ENTRY);
    state = recordHistoryVisit(state, 'other.md');

    const remapped = remapHistory(state, 'dir', 'renamed');
    expect(remapped).toEqual({
      visited: ['renamed/a.md', GRAPH_ENTRY, 'other.md'],
      index: 2,
    });
  });

  it('drops deleted paths and adjusts index cleanly', () => {
    let state = createHistoryState();
    state = recordHistoryVisit(state, 'dir/a.md');
    state = recordHistoryVisit(state, 'dir/b.md');
    state = recordHistoryVisit(state, 'keep.md');

    const dropped = dropHistory(state, 'dir');
    expect(dropped).toEqual({ visited: ['keep.md'], index: 0 });

    const empty = dropHistory(dropped, 'keep.md');
    expect(empty).toEqual({ visited: [], index: -1 });
  });
});
