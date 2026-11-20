import { serializeExcalidraw } from './excalidraw-format';

const pad = (value: number) => String(value).padStart(2, '0');

/** Obsidian Excalidraw's embed naming: `<note name> YYYY-MM-DD HH.mm.ss.excalidraw.md`. */
export function newDrawingFilename(notePath: string, date: Date): string {
  const note = notePath.split('/').at(-1)?.replace(/\.(md|markdown)$/i, '') || 'Drawing';
  const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  const time = `${pad(date.getHours())}.${pad(date.getMinutes())}.${pad(date.getSeconds())}`;
  return `${note} ${day} ${time}.excalidraw.md`;
}

export function newDrawingContent(): string {
  return serializeExcalidraw({ elements: [], appState: {}, files: {} });
}
