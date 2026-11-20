import { describe, expect, it } from 'vitest';
import { parseMetadata } from './metadata';
import { normalizeVaultPath, remapDescendant, resolveNotePath } from './paths';

describe('note metadata', () => {
  it('reads YAML fields, flow tags, and body words', () => {
    const metadata = parseMetadata('---\ntitle: "Daily note"\ntags: [work, llm]\nnested:\n  owner: alice\n---\nTwo words');
    expect(metadata.title).toBe('Daily note');
    expect(metadata.tags).toEqual(['work', 'llm']);
    expect(metadata.fields.find(({ key }) => key === 'nested')?.value).toBe('{"owner":"alice"}');
    expect(metadata.words).toBe(2);
  });
});

describe('vault paths', () => {
  it('normalizes links and remaps descendants', () => {
    const files = new Set(['folder/target.md']);
    expect(resolveNotePath('../folder/target', 'notes/current.md', files)).toEqual({ path: 'folder/target.md', exists: true });
    expect(normalizeVaultPath('one/../two/file.md')).toBe('two/file.md');
    expect(remapDescendant('old/note.md', 'old', 'new')).toBe('new/note.md');
  });

  it('resolves Obsidian shortest-path wikilinks anywhere in the vault', () => {
    const files = new Set([
      'work/acme/LLMs/people/Eve.md',
      'personal/people/Eve.md',
    ]);

    expect(resolveNotePath('Eve', 'work/acme/LLMs/daily/today.md', files)).toEqual({
      path: 'work/acme/LLMs/people/Eve.md',
      exists: true,
    });
  });

  it('resolves wikilinks across equivalent Unicode compositions', () => {
    const files = new Set([
      'trabajo/people/Omar Castan\u0303o.md',
      'trabajo/people/Pablo Garci\u0301a.md',
    ]);

    expect(resolveNotePath('Omar Castaño', 'diario/today.md', files)).toEqual({
      path: 'trabajo/people/Omar Castan\u0303o.md',
      exists: true,
    });
    expect(resolveNotePath('Pablo García', 'diario/today.md', files)).toEqual({
      path: 'trabajo/people/Pablo Garci\u0301a.md',
      exists: true,
    });
  });
});
