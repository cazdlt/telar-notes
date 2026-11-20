<script lang="ts">
  import FileTree from './FileTree.svelte';
  import RecentFiles from './RecentFiles.svelte';
  import type { RecentEntry, RecentTab } from '../lib/recent';
  import type { FileNode, RecentFile } from '../lib/types';

  let {
    explorerOpen,
    leftPanel,
    recentEnabled,
    recentVisible,
    graphOpen,
    recentTab,
    recentOpenedVisible,
    recentFiles,
    recentError,
    currentFile,
    treeNodes,
    selectedDir,
    expanded,
    onToggleLeftPanel,
    onCloseExplorer,
    onOpenSearch,
    onOpenDaily,
    onToggleGraph,
    onNewFile,
    onSelectRecentTab,
    onOpenFile,
    onTogglePath,
    onSelectDir,
    onOpenFolder,
    onContext,
    onMove,
  }: {
    explorerOpen: boolean;
    leftPanel: 'explorer' | 'recent';
    recentEnabled: boolean;
    recentVisible: boolean;
    graphOpen: boolean;
    recentTab: RecentTab;
    recentOpenedVisible: RecentEntry[];
    recentFiles: RecentFile[] | null;
    recentError: string | null;
    currentFile: string | null;
    treeNodes: FileNode[];
    selectedDir: string | null;
    expanded: Set<string>;
    onToggleLeftPanel: (panel: 'explorer' | 'recent') => void;
    onCloseExplorer: () => void;
    onOpenSearch: () => void;
    onOpenDaily: () => void;
    onToggleGraph: () => void;
    onNewFile: () => void;
    onSelectRecentTab: (tab: RecentTab) => void;
    onOpenFile: (path: string) => void;
    onTogglePath: (path: string) => void;
    onSelectDir: (path: string) => void;
    onOpenFolder: (dir: string, note: string) => void;
    onContext: (event: MouseEvent, path: string, isDir: boolean) => void;
    onMove: (from: string, target: string) => void;
  } = $props();

  function treeKeydown(event: KeyboardEvent & { currentTarget: HTMLElement }): void {
    const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('.tree-item')];
    const current = document.activeElement as HTMLButtonElement;
    const index = items.indexOf(current);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const next = event.key === 'ArrowDown' ? Math.min(index + 1, items.length - 1) : Math.max(index - 1, 0);
      items[Math.max(next, 0)]?.focus();
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      current?.click();
    } else if (event.key === 'ArrowRight' && current?.dataset.dir === 'true' && current.getAttribute('aria-expanded') === 'false') {
      event.preventDefault();
      (current.querySelector<HTMLElement>('.arrow') ?? current).click();
    } else if (event.key === 'ArrowLeft' && current?.dataset.dir === 'true' && current.getAttribute('aria-expanded') === 'true') {
      event.preventDefault();
      (current.querySelector<HTMLElement>('.arrow') ?? current).click();
    }
  }
</script>

<aside id="left-sidebar" aria-label="Navigation">
  <div class="ribbon-group">
    <button class="sidebar-action" class:active={explorerOpen && leftPanel === 'explorer'} type="button" onclick={() => onToggleLeftPanel('explorer')} title="Toggle explorer" aria-label="Toggle explorer" aria-controls="tree-panel" aria-expanded={explorerOpen && leftPanel === 'explorer'}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/></svg>
    </button>
    {#if recentEnabled}
      <button class="sidebar-action" class:active={recentVisible} type="button" onclick={() => onToggleLeftPanel('recent')} title="Recent files" aria-label="Recent files" aria-controls="tree-panel" aria-expanded={recentVisible}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>
      </button>
    {/if}
    <button class="sidebar-action" type="button" onclick={onOpenSearch} title="Search (⌘K)" aria-label="Search">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.4-3.4"/></svg>
    </button>
    <button id="today-note-btn" class="sidebar-action" type="button" onclick={onOpenDaily} title="Today's note" aria-label="Today's note">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/></svg>
    </button>
    <button class="sidebar-action" class:active={graphOpen} type="button" onclick={onToggleGraph} title="Graph view (⌘G)" aria-label="Graph view">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="7" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.3 8.2 10.8 16M15.9 7.6 13.2 15.9M8.5 6.8l7-.6"/></svg>
    </button>
    <button class="sidebar-action" type="button" onclick={onNewFile} title="New note (⌘N)" aria-label="New note">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9z"/><path d="M13 3v6h6M12 12v5M9.5 14.5h5"/></svg>
    </button>
  </div>
</aside>

{#if explorerOpen}
  <button id="explorer-scrim" type="button" onclick={onCloseExplorer} aria-label="Close explorer"></button>
{/if}

<section id="tree-panel">
  {#if leftPanel === 'recent'}
    <div id="tree-label"><span>Recent</span></div>
    <RecentFiles tab={recentTab} opened={recentOpenedVisible} files={recentFiles} error={recentError} {currentFile} onTab={onSelectRecentTab} onOpen={onOpenFile} />
  {:else}
    <div id="tree-label"><span>Explorer</span><button id="new-file-btn" onclick={onNewFile} title="New file">＋</button></div>
    <div
      id="tree-scroll"
      role="tree"
      tabindex="0"
      onkeydown={treeKeydown}
      ondragover={(event) => event.preventDefault()}
      ondrop={(event) => { event.preventDefault(); onMove(event.dataTransfer?.getData('text/plain') || '', ''); }}
      oncontextmenu={(event) => { if (event.target === event.currentTarget) onContext(event, selectedDir || '', true); }}
    >
      <FileTree
        nodes={treeNodes}
        currentFile={graphOpen ? null : currentFile}
        {selectedDir}
        {expanded}
        onToggle={onTogglePath}
        {onSelectDir}
        onOpen={onOpenFile}
        {onOpenFolder}
        {onContext}
        {onMove}
      />
    </div>
  {/if}
</section>
