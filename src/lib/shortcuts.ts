import type { SearchMode } from './types';

export type GlobalShortcutAction =
  | 'close-graph'
  | 'search-content'
  | 'search-title'
  | 'search-current'
  | 'find-in-note'
  | 'save'
  | 'toggle-graph'
  | 'new-file'
  | 'history-back'
  | 'history-forward';

export interface KeyEventLike {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
}

export function matchGlobalShortcut(
  event: KeyEventLike,
  context: { graphOpen: boolean; searchOpen: boolean },
): GlobalShortcutAction | null {
  if (event.key === 'Escape' && context.graphOpen) return 'close-graph';
  if (!event.metaKey && !event.ctrlKey) return null;
  const key = event.key.toLowerCase();
  if (event.shiftKey) {
    if (key === 'f') return 'search-content';
    if (key === 'p') return 'search-title';
    return null;
  }
  if (key === 'k') return 'search-current';
  if (key === 'f') return context.searchOpen ? null : 'find-in-note';
  if (key === 's') return 'save';
  if (key === 'g') return 'toggle-graph';
  if (key === 'n') return 'new-file';
  if (key === '[') return 'history-back';
  if (key === ']') return 'history-forward';
  return null;
}

export function detectSearchMode(raw: string, fallback: SearchMode): { query: string; mode: SearchMode } {
  if (raw.startsWith('/')) return { query: raw.slice(1), mode: 'content' };
  if (raw.startsWith('[[')) return { query: raw.slice(2), mode: 'links' };
  if (raw.startsWith('#')) return { query: raw.slice(1), mode: 'tags' };
  return { query: raw, mode: fallback };
}
