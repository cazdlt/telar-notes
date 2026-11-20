<script lang="ts">
  let { path = '', directory = false }: { path?: string; directory?: boolean } = $props();
  const kind = $derived(
    directory ? 'folder'
      : /\.excalidraw(?:\.md)?$/i.test(path) ? 'drawing'
        : /\.(png|jpe?g|gif|webp|svg)$/i.test(path) ? 'image'
          : /\.(md|markdown)$/i.test(path) ? 'note'
            : 'file',
  );
</script>

<svg class="file-icon" viewBox="0 0 16 16" aria-hidden="true">
  {#if kind === 'folder'}
    <path d="M1.5 4.25h5l1.2 1.5h6.8v6.75a1 1 0 0 1-1 1h-12z" />
    <path d="M1.5 4.25v-.5a1 1 0 0 1 1-1h3.25l1.1 1.5" />
  {:else if kind === 'image'}
    <rect x="2" y="2" width="12" height="12" rx="1.5" />
    <circle cx="5.5" cy="5.5" r="1" />
    <path d="m3.5 12 3-3 2 2 1.5-1.5 2.5 2.5" />
  {:else if kind === 'drawing'}
    <path d="M3 13h2.4l7.2-7.2-2.4-2.4L3 10.6z" />
    <path d="m8.9 4.7 2.4 2.4M2 14h12" />
  {:else}
    <path d="M3 1.75h6l4 4v8.5H3z" />
    <path d="M9 1.75v4h4" />
    {#if kind === 'note'}<path d="M5.25 8h5.5M5.25 10.25h5.5M5.25 12.5h3.5" />{/if}
  {/if}
</svg>

<style>
  .file-icon { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.2; stroke-linecap: round; stroke-linejoin: round; }
</style>
