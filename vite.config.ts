import { cpSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig, type Plugin } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// Excalidraw loads its fonts at runtime from EXCALIDRAW_ASSET_PATH (see src/excalidraw/editor.ts).
function excalidrawFonts(): Plugin {
  return {
    name: 'excalidraw-fonts',
    apply: 'build',
    writeBundle(options) {
      cpSync(resolve(process.cwd(), 'node_modules/@excalidraw/excalidraw/dist/prod/fonts'), resolve(options.dir!, 'assets/excalidraw/fonts'), { recursive: true });
    },
  };
}

export default defineConfig({
  plugins: [svelte(), excalidrawFonts()],
  optimizeDeps: { entries: ['index.html', 'excalidraw-editor.html'] },
  define: { 'process.env.IS_PREACT': JSON.stringify('false') },
  build: {
    outDir: 'web/dist',
    emptyOutDir: true,
    rollupOptions: { input: { index: resolve(process.cwd(), 'index.html'), excalidraw: resolve(process.cwd(), 'excalidraw-editor.html') } },
  },
  server: {
    strictPort: true,
    proxy: {
      '/api': `http://127.0.0.1:${process.env.TELAR_API_PORT || '7732'}`,
    },
  },
});
