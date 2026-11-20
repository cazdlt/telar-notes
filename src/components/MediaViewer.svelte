<script lang="ts">
  import { api } from '../lib/api';

  let {
    open,
    file,
    onClose,
  }: {
    open: boolean;
    file: string | null;
    onClose: () => void;
  } = $props();
</script>

{#if open && file}
  <button type="button" id="media-viewer" class="open" aria-label="Close media viewer" onclick={onClose}>
    <span class="mv-close">×</span>
    <img src={api.raw(file)} alt={file} />
    <span class="mv-name">{file}</span>
  </button>
{/if}
