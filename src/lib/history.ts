import { containsPath, remapDescendant } from './paths';

export const HISTORY_LIMIT = 100;

/** History entry for the graph view; the NUL byte keeps it from colliding with a vault path. */
export const GRAPH_ENTRY = '\0graph';

export interface HistoryState {
  visited: string[];
  index: number;
}

export function createHistoryState(): HistoryState {
  return { visited: [], index: -1 };
}

export function canGoBack(state: HistoryState): boolean {
  return state.index > 0;
}

export function canGoForward(state: HistoryState): boolean {
  return state.index >= 0 && state.index < state.visited.length - 1;
}

export function peekHistory(state: HistoryState, delta: number): string | undefined {
  return state.visited[state.index + delta];
}

export function recordHistoryVisit(state: HistoryState, path: string): HistoryState {
  if (state.visited[state.index] === path) return state;
  const next = [...state.visited.slice(0, state.index + 1), path].slice(-HISTORY_LIMIT);
  return { visited: next, index: next.length - 1 };
}

export function remapHistory(state: HistoryState, from: string, to: string): HistoryState {
  return {
    visited: state.visited.map((path) => remapDescendant(path, from, to) ?? path),
    index: state.index,
  };
}

export function dropHistory(state: HistoryState, path: string): HistoryState {
  const kept: string[] = [];
  let index = state.index;
  state.visited.forEach((entry, position) => {
    if (containsPath(path, entry)) {
      if (position <= state.index) index -= 1;
    } else {
      kept.push(entry);
    }
  });
  return {
    visited: kept,
    index: Math.min(Math.max(index, kept.length ? 0 : -1), kept.length - 1),
  };
}
