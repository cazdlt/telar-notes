/// <reference types="vite/client" />
// Excalidraw iframe page, bundled locally (previously loaded from esm.sh). The parent
// window talks to it over postMessage: `load`/`flush` for editing, `preview` for SVG export.
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { Excalidraw, exportToSvg } from '@excalidraw/excalidraw';
import '@excalidraw/excalidraw/index.css';

type ExcalidrawApi = Parameters<NonNullable<Parameters<typeof Excalidraw>[0]['excalidrawAPI']>>[0];
type SceneMessage = { elements?: unknown[]; appState?: Record<string, unknown>; files?: Record<string, unknown> };

declare global { interface Window { EXCALIDRAW_ASSET_PATH?: string | string[] } }

// Fonts are copied next to the build (see vite.config.ts); in dev Vite serves them from node_modules.
window.EXCALIDRAW_ASSET_PATH = import.meta.env.DEV ? '/node_modules/@excalidraw/excalidraw/dist/prod/' : '/assets/excalidraw/';

// Only ever talk to / trust the same-origin parent SPA — never "*".
const PARENT_ORIGIN = window.location.origin;
const previewMode = new URLSearchParams(location.search).has('preview');

// `loaded` gates all saving until the parent's real content is applied. Excalidraw fires
// onChange once on mount with an empty scene; persisting that would clobber the file. It
// also stays false briefly after the load so the load's own echo change isn't re-saved.
let api: ExcalidrawApi | null = null;
let saveTimer: ReturnType<typeof setTimeout> | undefined;
let loaded = false;

function currentJson() {
  const current = api!;
  const appState = current.getAppState();
  return {
    type: 'excalidraw', version: 2, source: 'telar-notes',
    elements: current.getSceneElements(),
    appState: { viewBackgroundColor: appState.viewBackgroundColor, gridSize: appState.gridSize },
    files: current.getFiles() || {},
  };
}
function postSave(): void { if (api && loaded) parent.postMessage({ type: 'save', json: currentJson() }, PARENT_ORIGIN); }
function onChange(): void {
  if (!loaded) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(postSave, 500);
}
function flushNow(): void { clearTimeout(saveTimer); postSave(); }

if (!previewMode) {
  createRoot(document.getElementById('root')!).render(createElement(Excalidraw, { onChange, excalidrawAPI: (value: ExcalidrawApi) => { api = value; } }));
}

window.addEventListener('message', (event: MessageEvent) => {
  if (event.origin !== PARENT_ORIGIN) return;
  const data = (event.data || {}) as SceneMessage & { type?: string; requestId?: number };
  if (data.type === 'preview' && previewMode) {
    // The scene arrives as untyped JSON from the file; Excalidraw validates it on export.
    exportToSvg({ elements: (data.elements || []) as never, appState: (data.appState || {}) as never, files: (data.files || {}) as never })
      .then((svg: SVGSVGElement) => parent.postMessage({ type: 'preview-result', requestId: data.requestId, svg: svg.outerHTML }, PARENT_ORIGIN))
      .catch((error: unknown) => parent.postMessage({ type: 'preview-error', requestId: data.requestId, error: String((error as Error)?.message || error) }, PARENT_ORIGIN));
  } else if (data.type === 'load' && api) {
    api.updateScene({ elements: (data.elements || []) as never, appState: (data.appState || {}) as never });
    if (data.files) api.addFiles(Object.values(data.files) as never);
    setTimeout(() => { loaded = true; }, 300);
  } else if (data.type === 'flush') {
    // The parent is about to remove the iframe: hand back the state, or ack if nothing to save.
    clearTimeout(saveTimer);
    if (api && loaded) parent.postMessage({ type: 'save', json: currentJson() }, PARENT_ORIGIN);
    else parent.postMessage({ type: 'flushed' }, PARENT_ORIGIN);
  }
});

window.addEventListener('blur', flushNow);
document.addEventListener('visibilitychange', () => { if (document.hidden) flushNow(); });
window.addEventListener('pagehide', flushNow);

if (previewMode) parent.postMessage({ type: 'preview-ready' }, PARENT_ORIGIN);
else {
  const ready = setInterval(() => { if (api) { clearInterval(ready); parent.postMessage({ type: 'ready' }, PARENT_ORIGIN); } }, 100);
}
