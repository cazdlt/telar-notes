<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { parseExcalidraw, serializeExcalidraw, type SceneInput } from '../lib/excalidraw-format';

  let { path, content, onSave }: { path: string; content: string; onSave: (content: string) => Promise<void> } = $props();
  let iframe: HTMLIFrameElement;
  let ready = false;
  let writes = Promise.resolve();
  let flushResolve: ((ok: boolean) => void) | null = null;

  function serialize(scene: SceneInput | undefined): string {
    return path.endsWith('.excalidraw.md') ? serializeExcalidraw(scene) : JSON.stringify(scene, null, 2);
  }

  function persist(scene: SceneInput | undefined): Promise<void> {
    writes = writes.then(() => onSave(serialize(scene)));
    return writes;
  }

  async function message(event: MessageEvent): Promise<void> {
    if (event.origin !== window.location.origin || event.source !== iframe?.contentWindow) return;
    const data = event.data as { type?: string; json?: SceneInput };
    if (data.type === 'ready') {
      const scene = parseExcalidraw(path, content);
      iframe.contentWindow?.postMessage({ type: 'load', elements: scene.elements || [], appState: scene.appState || {}, files: scene.files || {} }, window.location.origin);
      ready = true;
    } else if (data.type === 'save' && ready) {
      try { await persist(data.json); flushResolve?.(true); }
      catch { flushResolve?.(false); }
      finally { flushResolve = null; }
    } else if (data.type === 'flushed') {
      try { await writes; flushResolve?.(true); }
      catch { flushResolve?.(false); }
      finally { flushResolve = null; }
    }
  }

  export function flush(): Promise<boolean> {
    if (!ready || !iframe?.contentWindow) return writes.then(() => true, () => false);
    return new Promise((resolve) => {
      const timeout = setTimeout(() => { flushResolve = null; resolve(false); }, 12000);
      flushResolve = (ok) => { clearTimeout(timeout); resolve(ok); };
      iframe.contentWindow?.postMessage({ type: 'flush' }, window.location.origin);
    });
  }

  onMount(() => window.addEventListener('message', message));
  onDestroy(() => window.removeEventListener('message', message));
</script>

<iframe bind:this={iframe} class="excalidraw-frame" src="/excalidraw-editor.html" title={`Edit ${path}`}></iframe>

<style>.excalidraw-frame { width: 100%; height: 100%; border: 0; background: #fff; }</style>
