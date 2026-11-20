import { api } from './api';
import { sanitizeSvg } from './markdown-renderer';
import { parseExcalidraw, type Scene } from './excalidraw-format';

type Pending = { resolve: (svg: string) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> };

class ExcalidrawRenderer {
  private iframe: HTMLIFrameElement | null = null;
  private ready: Promise<void> | null = null;
  private resolveReady: (() => void) | null = null;
  private sequence = 0;
  private pending = new Map<number, Pending>();
  private cache = new Map<string, Promise<string>>();

  constructor() {
    if (typeof window !== 'undefined') window.addEventListener('message', this.message);
  }

  render(path: string): Promise<string> {
    const cached = this.cache.get(path);
    if (cached) return cached;
    const rendering = api.note(path).then(({ content }) => this.renderScene(parseExcalidraw(path, content)));
    rendering.catch(() => this.cache.delete(path));
    this.cache.set(path, rendering);
    return rendering;
  }

  invalidate(path: string): void { this.cache.delete(path); }

  private ensureFrame(): Promise<void> {
    if (this.ready) return this.ready;
    this.ready = new Promise((resolve) => { this.resolveReady = resolve; });
    const iframe = document.createElement('iframe');
    iframe.src = '/excalidraw-editor.html?preview=1';
    iframe.title = 'Excalidraw preview renderer';
    iframe.style.cssText = 'position:fixed;width:1px;height:1px;left:-10000px;top:-10000px;border:0';
    document.body.append(iframe);
    this.iframe = iframe;
    return this.ready;
  }

  private async renderScene(scene: Scene): Promise<string> {
    await this.ensureFrame();
    const requestId = this.sequence++;
    return new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new Error('Excalidraw preview timed out.'));
      }, 15000);
      this.pending.set(requestId, { resolve, reject, timer });
      this.iframe?.contentWindow?.postMessage({ type: 'preview', requestId, elements: scene.elements || [], appState: scene.appState || {}, files: scene.files || {} }, window.location.origin);
    });
  }

  private message = (event: MessageEvent): void => {
    if (event.origin !== window.location.origin || event.source !== this.iframe?.contentWindow) return;
    const data = event.data as { type?: string; requestId?: number; svg?: string; error?: string };
    if (data.type === 'preview-ready') { this.resolveReady?.(); this.resolveReady = null; return; }
    if (data.requestId === undefined) return;
    const pending = this.pending.get(data.requestId);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pending.delete(data.requestId);
    if (data.type === 'preview-result' && data.svg) pending.resolve(sanitizeSvg(data.svg));
    else pending.reject(new Error(data.error || 'Could not render Excalidraw preview.'));
  };
}

export const excalidrawRenderer = new ExcalidrawRenderer();
