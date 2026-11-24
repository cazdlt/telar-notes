<script lang="ts">
  import ExcalidrawEditor from './ExcalidrawEditor.svelte';
  import GraphView from './GraphView.svelte';
  import MarkdownEditor from './MarkdownEditor.svelte';
  import { api } from '../lib/api';
  import type { Graph } from '../lib/graph';

  let {
    editor = $bindable<MarkdownEditor | undefined>(),
    drawingEditor = $bindable<ExcalidrawEditor | undefined>(),
    graph,
    graphOrphans = $bindable<boolean>(),
    rebuildingLinks,
    graphColors,
    graphHidden,
    currentFile,
    title,
    tags,
    pathCopied,
    isMarkdown,
    isDrawing,
    isMedia,
    loading,
    editorKey,
    content,
    fontSize,
    fileSet,
    reading,
    persistentLivePreview,
    drawingsEnabled,
    taskAutoSuggestEnabled,
    drawingWidth,
    error,
    conflict,
    onRebuildGraph,
    onRebuildLinks,
    onFocusExplorer,
    onCopyPath,
    onToggleGraphGroup,
    onOpenFile,
    onChange,
    onSaveDrawing,
    onMissingLink,
    onOpenMedia,
    onPickImage,
    onNewDrawing,
    onPaste,
    onDismissError,
    onReloadExternal,
    onOverwriteWithLocal,
  }: {
    editor: MarkdownEditor | undefined;
    drawingEditor: ExcalidrawEditor | undefined;
    graph: Graph | null;
    graphOrphans: boolean;
    rebuildingLinks: boolean;
    graphColors: Map<string, string>;
    graphHidden: Set<string>;
    currentFile: string | null;
    title: string;
    tags: string[];
    pathCopied: boolean;
    isMarkdown: boolean;
    isDrawing: boolean;
    isMedia: boolean;
    loading: boolean;
    editorKey: number;
    content: string;
    fontSize: number;
    fileSet: Set<string>;
    reading: boolean;
    persistentLivePreview: boolean;
    drawingsEnabled: boolean;
    taskAutoSuggestEnabled: boolean;
    drawingWidth: number;
    error: string | null;
    conflict: { external: string; revision: string } | null;
    onRebuildGraph: () => void;
    onRebuildLinks: () => void;
    onFocusExplorer: () => void;
    onCopyPath: (path: string) => void;
    onToggleGraphGroup: (group: string) => void;
    onOpenFile: (path: string, anchor?: string, line?: number) => void;
    onChange: (value: string) => void;
    onSaveDrawing: (path: string, value: string) => Promise<void>;
    onMissingLink: (target: string) => void;
    onOpenMedia: () => void;
    onPickImage: () => void;
    onNewDrawing: () => void;
    onPaste: (event: ClipboardEvent) => void;
    onDismissError: () => void;
    onReloadExternal: () => void;
    onOverwriteWithLocal: () => void;
  } = $props();
</script>

<section id="editor-col">
  {#if graph}
    <div id="note-title-header" class="visible">
      <div id="note-title-main">Graph</div>
      <div id="note-title-sub">
        <span>{graph.nodes.length} notes · {graph.edges.length} links</span>
        <label class="graph-orphans"><input type="checkbox" bind:checked={graphOrphans} onchange={onRebuildGraph} /> Orphans</label>
        <button class="header-btn" title="Re-scan the vault and rebuild the link index" disabled={rebuildingLinks} onclick={onRebuildLinks}>
          {rebuildingLinks ? 'Rebuilding…' : 'Rebuild'}
        </button>
      </div>
    </div>
  {:else}
    <div id="note-title-header" class:visible={!!currentFile}>
      <div id="note-title-main">{title}</div>
      <div id="note-title-sub">
        <button id="note-title-breadcrumb" onclick={onFocusExplorer}>{currentFile}</button>
        <button id="copy-path-btn" type="button" title="Copy absolute path" aria-label="Copy absolute path" onclick={() => currentFile && onCopyPath(currentFile)}>
          {pathCopied ? '✓' : '⧉'}
        </button>
        {#each tags as tag}
          <span class="panel-chip">{tag}</span>
        {/each}
      </div>
    </div>
  {/if}

  {#if !graph && isMarkdown && !isDrawing}
    <div id="editor-toolbar">
      <div id="md-format-buttons">
        <button class="fmt-btn" onclick={() => editor?.bold()}><strong>B</strong></button>
        <button class="fmt-btn" onclick={() => editor?.italic()}><em>I</em></button>
        <button class="fmt-btn" onclick={() => editor?.strike()}><s>S</s></button>
        <span class="fmt-sep">|</span>
        <button class="fmt-btn" onclick={() => editor?.link()}>[[</button>
        <button class="fmt-btn" onclick={() => editor?.tag()}>#</button>
        <span class="fmt-sep">|</span>
        <button class="fmt-btn fmt-code" title="Inline code" onclick={() => editor?.inlineCode()}>`x`</button>
        <button class="fmt-btn" title="Code block" onclick={() => editor?.codeBlock()}>Code</button>
        <button class="fmt-btn" title="Task" onclick={() => editor?.task()}>Task</button>
        <button class="fmt-btn" title="Quote" onclick={() => editor?.quote()}>Quote</button>
        <button class="fmt-btn" title="Table" onclick={() => editor?.table()}>Table</button>
        <span class="fmt-sep">|</span>
        <button class="fmt-btn" onclick={() => editor?.mermaid()}>Diagram</button>
        <button class="fmt-btn" onclick={onPickImage}>Image</button>
        {#if drawingsEnabled}
          <button class="fmt-btn" title="New Excalidraw drawing" onclick={onNewDrawing}>Drawing</button>
        {/if}
      </div>
    </div>
  {/if}

  <div id="editor-area" hidden={graph !== null} style={`--editor-font-size:${fontSize}px`} onpaste={onPaste}>
    {#if loading}
      <div class="empty-state">Loading…</div>
    {:else if currentFile && isMarkdown && !isDrawing}
      {#key editorKey}
        <MarkdownEditor
          bind:this={editor}
          {content}
          currentPath={currentFile}
          files={() => fileSet}
          reading={() => reading}
          persistent={() => persistentLivePreview}
          drawings={() => drawingsEnabled}
          taskAutoSuggestEnabled={() => taskAutoSuggestEnabled}
          drawingWidth={() => drawingWidth}
          onChange={onChange}
          onOpenFile={onOpenFile}
          onOpenDrawing={(path) => onOpenFile(path)}
          onMissingLink={onMissingLink}
        />
      {/key}
    {:else if currentFile && isDrawing}
      {#key editorKey}
        <ExcalidrawEditor
          bind:this={drawingEditor}
          path={currentFile}
          {content}
          onSave={(value) => onSaveDrawing(currentFile!, value)}
        />
      {/key}
    {:else if currentFile}
      <div class="raw-file">
        {#if isMedia}
          <button class="media-button" onclick={onOpenMedia}><img src={api.raw(currentFile)} alt={currentFile} /></button>
        {:else}
          <pre>{content}</pre>
        {/if}
      </div>
    {:else}
      <div class="empty-state">
        <div>Telar Notes</div>
        <div>Open a note from the explorer or press ⌘K</div>
      </div>
    {/if}
  </div>

  {#if graph}
    <div id="graph-pane" aria-label="Graph view">
      {#key graph}
        <GraphView {graph} current={currentFile} groupColors={graphColors} hiddenGroups={graphHidden} onToggleGroup={onToggleGraphGroup} onOpen={(path) => onOpenFile(path)} />
      {/key}
    </div>
  {/if}

  {#if error}
    <div class="save-error" role="alert">{error}<button onclick={onDismissError}>×</button></div>
  {/if}
  {#if conflict}
    <div class="save-error" role="alert">
      <span>This note changed externally. Your local buffer is preserved.</span>
      <button class="header-btn" onclick={onReloadExternal}>Reload external</button>
      <button class="header-btn" onclick={onOverwriteWithLocal}>Overwrite with local</button>
    </div>
  {/if}
</section>
