<script lang="ts">
  import { tick } from 'svelte';
  import FileIcon from './FileIcon.svelte';
  import type { SearchMode, SearchResult } from '../lib/types';

  let {
    open,
    query,
    mode,
    results,
    loading,
    error,
    onClose,
    onQuery,
    onMode,
    onOpen,
  }: {
    open: boolean;
    query: string;
    mode: SearchMode;
    results: SearchResult[];
    loading: boolean;
    error: string | null;
    onClose: () => void;
    onQuery: (query: string) => void;
    onMode: (mode: SearchMode) => void;
    onOpen: (path: string) => void;
  } = $props();

  let selected = $state(0);
  let input = $state<HTMLInputElement>();
  let resultElements = $state<HTMLElement[]>([]);
  const visible = $derived(results.slice(0, 10));

  $effect(() => {
    if (open) {
      selected = 0;
      void tick().then(() => input?.focus());
    }
  });
  $effect(() => { query; mode; selected = 0; });

  function keydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') onClose();
    else if (event.key === 'ArrowDown') {
      event.preventDefault();
      selected = Math.min(selected + 1, visible.length - 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      selected = Math.max(selected - 1, 0);
    } else if (event.key === 'Enter' && visible[selected]) {
      event.preventDefault();
      onOpen(visible[selected].path);
    }
    void tick().then(() => resultElements[selected]?.scrollIntoView({ block: 'nearest' }));
  }
</script>

{#if open}
  <div id="cmd-k-overlay" class="open" role="presentation" onclick={(event) => event.target === event.currentTarget && onClose()}>
    <div id="cmd-k-modal" role="dialog" aria-label="Search notes" tabindex="-1" onkeydown={keydown}>
      <div id="cmd-k-input-wrap">
        <span>Search</span>
        <input bind:this={input} id="cmd-k-input" value={query} oninput={(event) => onQuery(event.currentTarget.value)} placeholder="Search titles and content…" autocomplete="off" />
        <button type="button" onclick={onClose}>esc</button>
      </div>
      <div id="cmd-k-modes">
        {#each ['all', 'title', 'content', 'links', 'tags'] as option}
          <button type="button" class="mode-pill" class:active={mode === option} onclick={() => onMode(option as SearchMode)}>{option}</button>
        {/each}
      </div>
      <div id="cmd-k-results" aria-live="polite">
        {#if loading}<div class="cmd-state">Searching…</div>
        {:else if error}<div class="cmd-state error">{error}</div>
        {:else if query.trim() && !visible.length}<div class="cmd-state">No results</div>
        {:else}
          {#each visible as result, index}
            <button bind:this={resultElements[index]} type="button" class="cmd-result" class:active={index === selected} onclick={() => onOpen(result.path)}>
              <span class="icon"><FileIcon path={result.path} /></span>
              <span class="result-copy">
                <span class="path">{result.path}</span>
                {#if result.snippet}<span class="snippet">{result.snippet.slice(0, 120)}</span>{/if}
                {#if result.tags?.length}<span class="meta">{result.tags.map((tag) => `#${tag}`).join(' ')}</span>{/if}
                {#if result.direction}<span class="meta">{result.direction.replace('_', ' ')}</span>{/if}
              </span>
            </button>
          {/each}
        {/if}
      </div>
      <div id="cmd-k-footer"><span>↑↓ navigate</span><span>↵ open</span><span>esc close</span><span>{results.length} results</span></div>
    </div>
  </div>
{/if}

<style>
  .result-copy { display: flex; flex: 1; min-width: 0; flex-direction: column; gap: 3px; }
  .cmd-state { padding: 26px 12px; color: var(--text-dim); text-align: center; font-family: var(--font-body); font-style: italic; }
  .cmd-state.error { color: var(--cal-dang); font-style: normal; font-family: var(--font-mono); font-size: calc(12px * var(--ui-scale, 1)); }
</style>
