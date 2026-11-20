import { describe, expect, it } from 'vitest';

import { resolveNotePath, resolveVaultPath } from './paths';

const files = new Set([
  'diario/2026/08/2026-08-21.md',
  'diario/2026/08/adjuntos/Pasted image 20260821143012.png',
  'trabajo/adjuntos/Pasted image 20260821143012.png',
  'trabajo/notas/project.md',
  'project.md',
  'trabajo/adjuntos/Entrega 2025-06-12 18.40.38.excalidraw.md',
  'drawings/plain.excalidraw',
]);

describe('resolveVaultPath', () => {
  it('resolves a bare attachment filename from the note\'s attachment folder', () => {
    expect(resolveVaultPath('Pasted image 20260821143012.png', 'diario/2026/08/2026-08-21.md', files))
      .toEqual({ path: 'diario/2026/08/adjuntos/Pasted image 20260821143012.png', exists: true });
  });

  it('picks the closest match when the filename repeats across folders', () => {
    expect(resolveVaultPath('Pasted image 20260821143012.png', 'trabajo/notas/project.md', files).path)
      .toBe('trabajo/adjuntos/Pasted image 20260821143012.png');
  });

  it('keeps an explicit path explicit instead of searching vault-wide', () => {
    expect(resolveVaultPath('otro/adjuntos/x.png', 'diario/2026/08/2026-08-21.md', files))
      .toEqual({ path: 'otro/adjuntos/x.png', exists: false });
  });

  it('reports a missing attachment as missing', () => {
    expect(resolveVaultPath('nope.png', 'project.md', files).exists).toBe(false);
  });
});

describe('resolveNotePath', () => {
  it('takes a vault-root hit before proximity ranking', () => {
    expect(resolveNotePath('project', 'trabajo/notas/sub/x.md', files).path).toBe('project.md');
  });

  it('ranks by proximity when neither the note folder nor the root matches', () => {
    expect(resolveNotePath('2026-08-21', 'trabajo/otra.md', files).path)
      .toBe('diario/2026/08/2026-08-21.md');
  });
});

describe('Obsidian `.md` fallback', () => {
  it('resolves an embed of `x.excalidraw` to `x.excalidraw.md`', () => {
    expect(resolveVaultPath('Entrega 2025-06-12 18.40.38.excalidraw', 'trabajo/notas/project.md', files))
      .toEqual({ path: 'trabajo/adjuntos/Entrega 2025-06-12 18.40.38.excalidraw.md', exists: true });
  });

  it('resolves a plain link to `x.excalidraw` the same way', () => {
    expect(resolveNotePath('Entrega 2025-06-12 18.40.38.excalidraw', 'trabajo/notas/project.md', files))
      .toEqual({ path: 'trabajo/adjuntos/Entrega 2025-06-12 18.40.38.excalidraw.md', exists: true });
  });

  it('prefers an existing file over the fallback and reports misses unchanged', () => {
    expect(resolveVaultPath('plain.excalidraw', 'drawings/a.md', files)).toEqual({ path: 'drawings/plain.excalidraw', exists: true });
    expect(resolveVaultPath('nope.excalidraw', 'drawings/a.md', files)).toEqual({ path: 'nope.excalidraw', exists: false });
  });
});
