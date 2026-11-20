import { sanitizeSvg } from './markdown-renderer';

type MermaidTheme = 'default' | 'dark';

let sequence = 0;
const cache = new Map<string, Promise<string>>();
let library: Promise<typeof import('mermaid').default> | null = null;
let initializedTheme: MermaidTheme | null = null;

async function loadMermaid(theme: MermaidTheme): Promise<typeof import('mermaid').default> {
  if (!library) library = import('mermaid').then(({ default: mermaid }) => mermaid);
  const mermaid = await library;
  if (initializedTheme !== theme) {
    // SVG <text> labels instead of <foreignObject> HTML, which sanitizeSvg strips.
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme,
      fontFamily: 'Inter, sans-serif',
      htmlLabels: false,
      flowchart: { htmlLabels: false },
    });
    initializedTheme = theme;
  }
  return mermaid;
}

function currentTheme(): MermaidTheme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'default';
}

export class MermaidRenderer {
  render(code: string): Promise<string> {
    const theme = currentTheme();
    const key = `${theme}\n${code}`;
    const cached = cache.get(key);
    if (cached) return cached;
    const rendering = loadMermaid(theme)
      .then((mermaid) => mermaid.render(`telar-mermaid-${sequence++}`, code))
      .then(({ svg }) => sanitizeSvg(svg))
      .catch((error: unknown) => {
        cache.delete(key);
        throw error;
      });
    cache.set(key, rendering);
    return rendering;
  }

  clear(): void {
    cache.clear();
  }
}

export const mermaidRenderer = new MermaidRenderer();
