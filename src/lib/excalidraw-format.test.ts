import { describe, expect, it } from 'vitest';

import { parseExcalidraw, serializeExcalidraw } from './excalidraw-format';

const scene = {
  type: 'excalidraw',
  version: 2,
  elements: [{ id: 'box', type: 'rectangle', x: 1, y: 2 }],
  appState: { viewBackgroundColor: '#fff' },
  files: {},
};

describe('parseExcalidraw', () => {
  it('reads legacy raw and Obsidian plain-json drawings', () => {
    expect(parseExcalidraw('drawing.excalidraw', JSON.stringify(scene)).elements).toEqual(scene.elements);
    const markdown = `# Drawing\n\n\`\`\`json\n${JSON.stringify(scene)}\n\`\`\``;
    expect(parseExcalidraw('drawing.excalidraw.md', markdown).elements).toEqual(scene.elements);
  });

  it('returns an empty recoverable scene for malformed input', () => {
    const parsed = parseExcalidraw('drawing.excalidraw.md', 'not a drawing');
    expect(parsed.elements).toEqual([]);
    expect(parsed.files).toEqual({});
  });
});

describe('serializeExcalidraw', () => {
  it('preserves a drawing through Obsidian serialization', () => {
    const parsed = parseExcalidraw('drawing.excalidraw.md', serializeExcalidraw(scene));
    expect(parsed.elements).toEqual(scene.elements);
    expect(parsed.appState).toEqual(scene.appState);
    expect(parsed.files).toEqual(scene.files);
  });
});
