import type { FileNode } from './types';

export function normalizeVaultPath(path: string): string {
  const parts: string[] = [];
  for (const part of path.replaceAll('\\', '/').split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') parts.pop();
    else parts.push(part);
  }
  return parts.join('/');
}

function comparableVaultPath(path: string): string {
  return normalizeVaultPath(path).normalize('NFC').toLocaleLowerCase();
}

export function parentPath(path: string): string {
  const normalized = normalizeVaultPath(path);
  const slash = normalized.lastIndexOf('/');
  return slash < 0 ? '' : normalized.slice(0, slash);
}

export function flattenFiles(nodes: FileNode[]): Set<string> {
  const paths = new Set<string>();
  const visit = (items: FileNode[]) => {
    for (const item of items) {
      if (item.type === 'dir') visit(item.children);
      else paths.add(item.path);
    }
  };
  visit(nodes);
  return paths;
}

function nearestByProximity(matches: string[], sourcePath: string): string {
  const sourceParts = parentPath(sourcePath).split('/').filter(Boolean);
  const proximity = (path: string): [number, number, string] => {
    const candidateParts = parentPath(path).split('/').filter(Boolean);
    let common = 0;
    while (
      common < sourceParts.length
      && common < candidateParts.length
      && sourceParts[common].normalize('NFC').toLocaleLowerCase()
        === candidateParts[common].normalize('NFC').toLocaleLowerCase()
    ) common += 1;
    return [
      sourceParts.length + candidateParts.length - (2 * common),
      candidateParts.length,
      path.normalize('NFC').toLocaleLowerCase(),
    ];
  };
  return [...matches].sort((left, right) => {
    const a = proximity(left);
    const b = proximity(right);
    return a[0] - b[0] || a[1] - b[1] || a[2].localeCompare(b[2]);
  })[0];
}

function resolveVaultPathStrict(
  target: string,
  sourcePath: string,
  files: ReadonlySet<string>,
): { path: string; exists: boolean } {
  const cleanTarget = normalizeVaultPath(target.split('#', 1)[0].trim());
  const relative = normalizeVaultPath(`${parentPath(sourcePath)}/${cleanTarget}`);
  if (files.has(relative)) return { path: relative, exists: true };
  return { path: cleanTarget, exists: files.has(cleanTarget) };
}

// Obsidian retries a missing target as `<target>.md`; that is how `![[x.excalidraw]]`
// reaches `x.excalidraw.md`.
function withMarkdownFallback(
  target: string,
  resolve: (target: string) => { path: string; exists: boolean },
): { path: string; exists: boolean } {
  const found = resolve(target);
  const path = target.split('#', 1)[0].trim();
  if (found.exists || !path || /\.md$/i.test(path)) return found;
  const note = resolve(`${path}.md`);
  return note.exists ? note : found;
}

export function resolveVaultPath(
  target: string,
  sourcePath: string,
  files: ReadonlySet<string>,
): { path: string; exists: boolean } {
  return withMarkdownFallback(target, (candidate) => resolveVaultPathOnce(candidate, sourcePath, files));
}

function resolveVaultPathOnce(
  target: string,
  sourcePath: string,
  files: ReadonlySet<string>,
): { path: string; exists: boolean } {
  const direct = resolveVaultPathStrict(target, sourcePath, files);
  if (direct.exists || direct.path.includes('/')) return direct;
  // Bare filename: Obsidian looks vault-wide, which is how attachments stored in the
  // configured attachment folder (e.g. adjuntos/) resolve from an embed with no path.
  const normalized = comparableVaultPath(direct.path);
  const matches = [...files].filter(
    (path) => comparableVaultPath(path.slice(path.lastIndexOf('/') + 1)) === normalized,
  );
  if (!matches.length) return direct;
  return { path: nearestByProximity(matches, sourcePath), exists: true };
}

export function resolveNotePath(
  target: string,
  sourcePath: string,
  files: ReadonlySet<string>,
): { path: string; exists: boolean } {
  return withMarkdownFallback(target, (candidate) => resolveNotePathOnce(candidate, sourcePath, files));
}

function resolveNotePathOnce(
  target: string,
  sourcePath: string,
  files: ReadonlySet<string>,
): { path: string; exists: boolean } {
  const withoutAnchor = target.split('#', 1)[0].trim();
  const note = /\.[a-z0-9]+$/i.test(withoutAnchor) ? withoutAnchor : `${withoutAnchor}.md`;
  const direct = resolveVaultPathStrict(note, sourcePath, files);
  if (direct.exists) return direct;

  const normalized = comparableVaultPath(note);
  const suffix = `/${normalized}`;
  const matches = [...files].filter((path) => {
    const candidate = comparableVaultPath(path);
    return candidate === normalized || candidate.endsWith(suffix);
  });
  if (!matches.length) return direct;
  return { path: nearestByProximity(matches, sourcePath), exists: true };
}

export function remapDescendant(path: string | null, from: string, to: string): string | null {
  if (!path) return null;
  if (path === from) return to;
  return path.startsWith(`${from}/`) ? `${to}${path.slice(from.length)}` : path;
}

export function containsPath(container: string, path: string | null): boolean {
  return !!path && (path === container || path.startsWith(`${container}/`));
}
