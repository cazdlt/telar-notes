import { containsPath, remapDescendant } from './paths';

export type RecentEntry = { path: string; openedAt: number };
export type RecentTab = 'opened' | 'modified' | 'created';

// Storage cap; matches the largest Recent Files `limit` the settings accept.
export const RECENT_LIMIT = 200;
export const DEFAULT_RECENT_DISPLAY = 20;
const storageKey = (vault: string) => `telar-recent:${vault}`;

function dedupe(list: RecentEntry[]): RecentEntry[] {
  const seen = new Set<string>();
  return list.filter((entry) => !seen.has(entry.path) && !!seen.add(entry.path));
}

/** Files Telar Notes renders (notes, drawings, images); mirrors the server's RECENT_EXTENSIONS. */
export function isRecentFile(path: string): boolean {
  return /\.(md|markdown|excalidraw|png|jpe?g|gif|webp|svg)$/i.test(path);
}

/** Put `path` at the front of the list, dropping its older entry and anything past the cap. */
export function pushRecent(list: RecentEntry[], path: string, openedAt = Date.now()): RecentEntry[] {
  return dedupe([{ path, openedAt }, ...list]).slice(0, RECENT_LIMIT);
}

/** Follow a rename or move of a file or folder. */
export function remapRecent(list: RecentEntry[], from: string, to: string): RecentEntry[] {
  return dedupe(list.map((entry) => ({ ...entry, path: remapDescendant(entry.path, from, to) ?? entry.path })));
}

/** Forget a deleted file, or every file under a deleted folder. */
export function dropRecent(list: RecentEntry[], path: string): RecentEntry[] {
  return list.filter((entry) => !containsPath(path, entry.path));
}

/** Read a vault's history, ignoring anything that is not a well-formed entry list. */
export function loadRecent(vault: string, storage: Pick<Storage, 'getItem'> = localStorage): RecentEntry[] {
  let parsed: unknown;
  try { parsed = JSON.parse(storage.getItem(storageKey(vault)) || '[]'); } catch { return []; }
  if (!Array.isArray(parsed)) return [];
  const valid = parsed.filter((entry): entry is RecentEntry =>
    typeof entry?.path === 'string' && !!entry.path && typeof entry.openedAt === 'number');
  return dedupe(valid).slice(0, RECENT_LIMIT);
}

export function saveRecent(vault: string, list: RecentEntry[], storage: Pick<Storage, 'setItem'> = localStorage): void {
  storage.setItem(storageKey(vault), JSON.stringify(list));
}

/** Compact age for a narrow column: "now", "5m", "3h", "4d", then "Sep 21" (plus year when not current). */
export function relativeTime(timestamp: number, now = Date.now()): string {
  const minutes = Math.floor((now - timestamp) / 60_000);
  if (minutes < 1) return 'now';
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}h`;
  if (minutes < 60 * 24 * 7) return `${Math.floor(minutes / (60 * 24))}d`;
  const date = new Date(timestamp);
  const sameYear = date.getFullYear() === new Date(now).getFullYear();
  return date.toLocaleDateString('en-US', sameYear ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' });
}
