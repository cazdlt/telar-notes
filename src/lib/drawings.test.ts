import { describe, expect, it } from 'vitest';

import { parseExcalidraw } from './excalidraw-format';
import { newDrawingContent, newDrawingFilename } from './drawings';

describe('newDrawingFilename', () => {
  it('prefixes the note name to a zero-padded timestamp', () => {
    expect(newDrawingFilename('trabajo/Entrega.md', new Date(2025, 5, 2, 8, 4, 9))).toBe('Entrega 2025-06-02 08.04.09.excalidraw.md');
  });
});

describe('newDrawingContent', () => {
  it('is an empty scene Obsidian Excalidraw can read back', () => {
    const content = newDrawingContent();
    expect(content).toContain('excalidraw-plugin: raw');
    expect(parseExcalidraw('x.excalidraw.md', content).elements).toEqual([]);
  });
});
