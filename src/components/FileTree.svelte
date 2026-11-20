<script lang="ts">
  import type { FileNode } from '../lib/types';
  import FileIcon from './FileIcon.svelte';
  import FileTree from './FileTree.svelte';
  let { nodes, currentFile, selectedDir = null, expanded, onToggle, onOpen, onOpenFolder, onSelectDir, onContext, onMove }: { nodes: FileNode[]; currentFile: string | null; selectedDir?: string | null; expanded: Set<string>; onToggle: (path: string) => void; onOpen: (path: string) => void; onOpenFolder: (dir: string, note: string) => void; onSelectDir: (path: string) => void; onContext: (event: MouseEvent, path: string, isDir: boolean) => void; onMove: (from: string, target: string) => void } = $props();
  let dragTarget = $state<string | null>(null);
</script>
<div class="svelte-tree">
  {#each nodes as node}
    {#if node.type === 'dir'}
      <button type="button" role="treeitem" aria-selected={selectedDir === node.path} aria-expanded={expanded.has(node.path)} data-path={node.path} data-dir="true" class:dir-selected={selectedDir === node.path} class:has-note={!!node.folderNote} class:selected={!!node.folderNote && node.folderNote === currentFile} class:drag-over={dragTarget === node.path} class="node tree-item" oncontextmenu={(e) => onContext(e, node.path, true)} ondragover={(e) => { e.preventDefault(); dragTarget = node.path; }} ondragleave={() => dragTarget = null} ondrop={(e) => { e.preventDefault(); dragTarget = null; void onMove(e.dataTransfer?.getData('text/plain') || '', node.path); }} onclick={(e) => { if (node.folderNote && !(e.target as HTMLElement).closest('.arrow')) { onOpenFolder(node.path, node.folderNote); return; } onSelectDir(node.path); onToggle(node.path); }} draggable="true" ondragstart={(e) => { e.dataTransfer?.setData('text/plain', node.path); if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'; }}><span class="arrow"></span><span class="name">{node.path.split('/').at(-1)}</span></button>
      {#if expanded.has(node.path)}<div class="tree-nest"><FileTree nodes={node.children} {currentFile} {selectedDir} {expanded} {onToggle} {onOpen} {onOpenFolder} {onSelectDir} {onContext} {onMove}/></div>{/if}
    {:else}
      <button type="button" role="treeitem" aria-selected={node.path === currentFile} class:selected={node.path === currentFile} class="node tree-item" data-path={node.path} data-dir="false" oncontextmenu={(e) => onContext(e, node.path, false)} onclick={() => void onOpen(node.path)} draggable="true" ondragstart={(e) => { e.dataTransfer?.setData('text/plain', node.path); if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'; }}><span class="arrow"></span>{#if !node.name.endsWith('.md')}<span class="icon"><FileIcon path={node.path} /></span>{/if}<span class="name">{node.name.replace(/\.md$/, '')}</span></button>
    {/if}
  {/each}
</div>
