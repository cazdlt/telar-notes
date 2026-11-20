<script lang="ts">
  import { onDestroy } from 'svelte';
  import { parentPath } from '../lib/paths';
  import { relativeTime, type RecentEntry, type RecentTab } from '../lib/recent';
  import type { RecentFile } from '../lib/types';

  let {
    tab,
    opened,
    files,
    error,
    currentFile,
    onTab,
    onOpen,
  }: {
    tab: RecentTab;
    opened: RecentEntry[];
    files: RecentFile[] | null;
    error: string | null;
    currentFile: string | null;
    onTab: (tab: RecentTab) => void;
    onOpen: (path: string) => void;
  } = $props();

  const tabs: { id: RecentTab; label: string }[] = [
    { id: 'opened', label: 'Opened' },
    { id: 'modified', label: 'Modified' },
    { id: 'created', label: 'Created' },
  ];

  // Keeps the relative "When" labels from going stale while the panel stays open.
  let now = $state(Date.now());
  const clock = setInterval(() => { now = Date.now(); }, 30_000);
  onDestroy(() => clearInterval(clock));

  const rows = $derived(tab === 'opened'
    ? opened.map((entry) => ({ path: entry.path, at: entry.openedAt }))
    : files?.map((file) => ({ path: file.path, at: tab === 'created' ? file.created : file.modified })) ?? []);

  const displayName = (path: string) => path.split('/').at(-1)?.replace(/\.(md|markdown)$/i, '') || path;
  const tooltip = (path: string, at: number) => `${parentPath(path) || '/'}\n${new Date(at).toLocaleString()}`;
</script>

<div class="recent-files">
  <div class="panel-tab-selector" role="tablist" aria-label="Recent files">
    {#each tabs as item}
      <button type="button" role="tab" aria-selected={tab === item.id} class="panel-tab" class:active={tab === item.id} onclick={() => onTab(item.id)}>{item.label}</button>
    {/each}
  </div>
  <div class="recent-scroll">
    {#if error}<p class="recent-empty error">{error}</p>
    {:else if tab !== 'opened' && files === null}<p class="recent-empty">Loading…</p>
    {:else if !rows.length}<p class="recent-empty">{tab === 'opened' ? 'No files opened yet.' : 'No files.'}</p>
    {:else}
      <table class="recent-table">
        <thead><tr><th>Name</th><th>When</th></tr></thead>
        <tbody>
          {#each rows as row (row.path)}
            <tr class:current={row.path === currentFile}>
              <td><button type="button" class="recent-name" title={tooltip(row.path, row.at)} onclick={() => onOpen(row.path)}>{displayName(row.path)}</button></td>
              <td class="recent-when">{relativeTime(row.at, now)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</div>
