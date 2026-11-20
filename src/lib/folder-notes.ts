import type { FileNode } from './types';

const baseName = (path: string) => path.split('/').at(-1) ?? path;

export function folderNotePath(dir: string): string {
  return `${dir}/${baseName(dir)}.md`;
}

/** Display tree: dirs holding `Dir/Dir.md` get `folderNote` and lose that child. */
export function withFolderNotes(tree: FileNode[]): FileNode[] {
  return tree.map((node) => {
    if (node.type !== 'dir') return node;
    const note = folderNotePath(node.path);
    const hasNote = node.children.some((child) => child.type === 'file' && child.path === note);
    const children = withFolderNotes(hasNote ? node.children.filter((child) => child.path !== note) : node.children);
    return hasNote ? { ...node, children, folderNote: note } : { ...node, children };
  });
}

/** The folder whose note is `path`, if `path` is one in `tree`. */
export function folderForNote(path: string, tree: FileNode[]): string | null {
  const slash = path.lastIndexOf('/');
  if (slash < 0) return null;
  const dir = path.slice(0, slash);
  return folderNotePath(dir) === path && findDir(tree, dir) ? dir : null;
}

/** Rename pair for a folder note after its folder moved from `from` to `to`, or null when nothing applies. */
export function folderNoteRename(from: string, to: string, tree: FileNode[]): [string, string] | null {
  const before = baseName(from);
  const after = baseName(to);
  if (before === after) return null;
  const dir = findDir(tree, to);
  if (!dir) return null;
  const old = `${to}/${before}.md`;
  const next = `${to}/${after}.md`;
  const has = (path: string) => dir.children.some((child) => child.type === 'file' && child.path === path);
  return has(old) && !has(next) ? [old, next] : null;
}

function findDir(nodes: FileNode[], path: string): Extract<FileNode, { type: 'dir' }> | null {
  for (const node of nodes) {
    if (node.type !== 'dir') continue;
    if (node.path === path) return node;
    if (path.startsWith(`${node.path}/`)) return findDir(node.children, path);
  }
  return null;
}
