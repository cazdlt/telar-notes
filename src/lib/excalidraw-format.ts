// Format layer for Obsidian Excalidraw plugin interop (.excalidraw.md).
import LZString from 'lz-string';

export type Scene = {
  type: 'excalidraw';
  version: number;
  source: string;
  elements: unknown[];
  appState: Record<string, unknown>;
  files: Record<string, unknown>;
};

export type SceneInput = Partial<Omit<Scene, 'type'>> & { type?: string };
type TextElement = { type: 'text'; id: string; text: string };

const BANNER =
  '==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠==';

function normalize(scene: SceneInput | null | undefined): Scene {
  scene = scene || {};
  return {
    type: 'excalidraw',
    version: scene.version || 2,
    source: scene.source || 'telar-notes',
    elements: Array.isArray(scene.elements) ? scene.elements : [],
    appState: scene.appState || {},
    files: scene.files || {},
  };
}

function isTextElement(el: unknown): el is TextElement {
  const candidate = el as Partial<TextElement> | null;
  return !!candidate && candidate.type === 'text' && typeof candidate.text === 'string';
}

// path decides legacy (.excalidraw = raw JSON) vs Obsidian (.excalidraw.md).
// Never throws: a malformed file yields an empty scene.
export function parseExcalidraw(path: string, text: string): Scene {
  try {
    if (/\.excalidraw$/i.test(path || '') && !/\.md$/i.test(path || '')) {
      return normalize(JSON.parse(text || '{}'));
    }
    const m = (text || '').match(/```(compressed-json|json)\s*\n([\s\S]*?)```/);
    if (!m) return normalize(null);
    const [, lang, payload] = m;
    const json = lang === 'compressed-json'
      ? JSON.parse(LZString.decompressFromBase64(payload.replace(/\s+/g, '')))
      : JSON.parse(payload);
    return normalize(json);
  } catch {
    return normalize(null);
  }
}

// Build the full Obsidian .excalidraw.md (compressed-json, raw mode).
export function serializeExcalidraw(scene: SceneInput | null | undefined): string {
  const s = normalize(scene);
  const drawing = {
    type: 'excalidraw', version: 2, source: 'telar-notes',
    elements: s.elements, appState: s.appState, files: s.files,
  };
  const b64 = LZString.compressToBase64(JSON.stringify(drawing));
  const wrapped = b64.replace(/(.{200})/g, '$1\n').replace(/\n$/, '');
  const textEls = s.elements
    .filter(isTextElement)
    .map((el) => `${el.text} ^${el.id}`)
    .join('\n\n');
  return [
    '---',
    'excalidraw-plugin: raw',
    'tags: [excalidraw]',
    '---',
    BANNER,
    '',
    '# Excalidraw Data',
    '## Text Elements',
    textEls,
    '',
    '## Drawing',
    '```compressed-json',
    wrapped,
    '```',
    '%%',
    '',
  ].join('\n');
}
