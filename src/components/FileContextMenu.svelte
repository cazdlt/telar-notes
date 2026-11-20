<script lang="ts">
  import { folderNotePath } from '../lib/folder-notes';

  export interface ContextMenuState {
    x: number;
    y: number;
    path: string;
    isDir: boolean;
  }

  let {
    context,
    folderNotesEnabled,
    fileSet,
    onClose,
    onFolderNote,
    onNewFile,
    onNewFolder,
    onRename,
    onReveal,
    onCopyPath,
    onRemove,
  }: {
    context: ContextMenuState | null;
    folderNotesEnabled: boolean;
    fileSet: Set<string>;
    onClose: () => void;
    onFolderNote: (dir: string) => void;
    onNewFile: (dir: string) => void;
    onNewFolder: (dir: string) => void;
    onRename: (path: string) => void;
    onReveal: (path: string) => void;
    onCopyPath: (path: string) => void;
    onRemove: (path: string) => void;
  } = $props();

  function clampToViewport(node: HTMLElement): void {
    const { width, height } = node.getBoundingClientRect();
    const x = Math.max(8, Math.min(context?.x ?? 0, window.innerWidth - width - 8));
    const y = Math.max(8, Math.min(context?.y ?? 0, window.innerHeight - height - 8));
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
  }
</script>

{#if context}
  {#key context}
    <div
      id="tree-context-menu"
      class="open"
      role="menu"
      tabindex="-1"
      use:clampToViewport
      style={`left:${context.x}px;top:${context.y}px`}
      onclick={(event) => event.stopPropagation()}
      onkeydown={(event) => event.key === 'Escape' && onClose()}
    >
      {#if context.isDir}
        {#if context.path && folderNotesEnabled}
          <button class="tcm-item" role="menuitem" onclick={() => { const dir = context?.path || ''; onClose(); onFolderNote(dir); }}>
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 2.5h6l3 3v8H3z"/><path d="M9 2.5v3h3"/></svg>
            {fileSet.has(folderNotePath(context.path)) ? 'Open folder note' : 'Create folder note'}
          </button>
        {/if}
        <button class="tcm-item" role="menuitem" onclick={() => { const dir = context?.path || ''; onClose(); onNewFile(dir); }}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 2.5h6l3 3v8H3z"/><path d="M7.5 7.5v4M5.5 9.5h4"/></svg>New file here
        </button>
        <button class="tcm-item" role="menuitem" onclick={() => { const dir = context?.path || ''; onClose(); onNewFolder(dir); }}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4.5h4l1.5 1.5H14v7H2z"/><path d="M8 8v3M6.5 9.5h3"/></svg>New folder here
        </button>
      {/if}
      {#if context.path}
        {#if context.isDir}<div class="tcm-sep" role="separator"></div>{/if}
        <button class="tcm-item" role="menuitem" onclick={() => { const path = context?.path || ''; onClose(); onRename(path); }}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13l.7-3L11 2.7a1.2 1.2 0 011.7 0l.6.6a1.2 1.2 0 010 1.7L6 12.3z"/><path d="M9.5 4.5l2 2"/></svg>Rename
        </button>
        <button class="tcm-item" role="menuitem" onclick={() => { const path = context?.path; onClose(); if (path) onReveal(path); }}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4.5h4l1.5 1.5H14v7H2z"/></svg>Reveal in Finder
        </button>
        <button class="tcm-item" role="menuitem" onclick={() => { const path = context?.path; onClose(); if (path) onCopyPath(path); }}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1.2"/><path d="M10.5 5.5v-2a1 1 0 00-1-1h-6a1 1 0 00-1 1v6a1 1 0 001 1h2"/></svg>Copy absolute path
        </button>
        <div class="tcm-sep" role="separator"></div>
        <button class="tcm-item danger" role="menuitem" onclick={() => { const path = context?.path || ''; onClose(); onRemove(path); }}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5v-2h3v2M4.5 4.5l.6 9h5.8l.6-9M6.8 7v4M9.2 7v4"/></svg>Move to trash
        </button>
      {/if}
    </div>
  {/key}
{/if}
