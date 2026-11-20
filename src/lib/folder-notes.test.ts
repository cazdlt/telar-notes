import { describe, expect, it } from 'vitest';
import { folderForNote, folderNotePath, folderNoteRename, withFolderNotes } from './folder-notes';
import type { FileNode } from './types';

const file = (path: string): FileNode => ({ type: 'file', path, name: path.split('/').at(-1)! });
const dir = (path: string, children: FileNode[]): FileNode => ({ type: 'dir', path, children });

describe('folder notes', () => {
  it('builds the note path inside the folder', () => {
    expect(folderNotePath('a/Projects')).toBe('a/Projects/Projects.md');
  });

  it('hides the matching child and marks the folder', () => {
    const [node] = withFolderNotes([dir('Projects', [file('Projects/Projects.md'), file('Projects/x.md')])]);
    expect(node).toMatchObject({ folderNote: 'Projects/Projects.md', children: [{ path: 'Projects/x.md' }] });
  });

  it('handles nested dirs and leaves folders without a note alone', () => {
    const tree = [dir('a', [dir('a/b', [file('a/b/b.md')]), dir('a/c', [file('a/c/other.md')])])];
    const [a] = withFolderNotes(tree);
    const [b, c] = (a as Extract<FileNode, { type: 'dir' }>).children as Extract<FileNode, { type: 'dir' }>[];
    expect(a).not.toHaveProperty('folderNote');
    expect(b.folderNote).toBe('a/b/b.md');
    expect(b.children).toEqual([]);
    expect(c.folderNote).toBeUndefined();
    expect(c.children).toHaveLength(1);
  });

  it('does not match names differing in case', () => {
    const [node] = withFolderNotes([dir('Projects', [file('Projects/projects.md')])]);
    expect(node).not.toHaveProperty('folderNote');
  });

  it('finds the folder for a note', () => {
    const tree = [dir('a', [dir('a/b', [file('a/b/b.md')])])];
    expect(folderForNote('a/b/b.md', tree)).toBe('a/b');
    expect(folderForNote('a/b/c.md', tree)).toBeNull();
    expect(folderForNote('b.md', tree)).toBeNull();
  });

  it('pairs the note rename after a folder rename', () => {
    const tree = [dir('B', [file('B/A.md')])];
    expect(folderNoteRename('A', 'B', tree)).toEqual(['B/A.md', 'B/B.md']);
  });

  it('skips the rename on a move, a missing note or a collision', () => {
    expect(folderNoteRename('x/A', 'y/A', [dir('y', [dir('y/A', [file('y/A/A.md')])])])).toBeNull();
    expect(folderNoteRename('A', 'B', [dir('B', [file('B/z.md')])])).toBeNull();
    expect(folderNoteRename('A', 'B', [dir('B', [file('B/A.md'), file('B/B.md')])])).toBeNull();
  });
});
