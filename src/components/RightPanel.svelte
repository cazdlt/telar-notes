<script lang="ts">
  import Calendar from './Calendar.svelte';
  import GraphView from './GraphView.svelte';
  import { buildGraph, localScope, type Graph } from '../lib/graph';
  import { parseMetadata } from '../lib/metadata';
  import type { LinksIndex, PeriodicNotesSettings } from '../lib/types';

  type Tab = 'backlinks' | 'outline' | 'meta' | 'graph' | 'calendar';

  let {
    open,
    tab,
    path,
    content,
    links,
    graphColors,
    snippets,
    periodic,
    files,
    onOpenDate,
    onOpenChange,
    onTab,
    onOpenFile,
    onOpenOutline,
  }: {
    open: boolean;
    tab: Tab;
    path: string | null;
    content: string;
    links: LinksIndex;
    graphColors: Map<string, string>;
    snippets: Record<string, string>;
    periodic: PeriodicNotesSettings | null;
    files: Set<string>;
    onOpenDate: (date: Date) => void;
    onOpenChange: (open: boolean) => void;
    onTab: (tab: Tab) => void;
    onOpenFile: (path: string) => void;
    onOpenOutline: (heading: string) => void;
  } = $props();

  const metadata = $derived(parseMetadata(content));
  const backlinks = $derived(path ? links[path]?.linked_from ?? [] : []);
  const outgoing = $derived(path ? links[path]?.links_to ?? [] : []);

  // Heading outline, skipping fenced code blocks so ``` #comments aren't picked up.
  const outline = $derived.by(() => {
    const items: { level: number; text: string }[] = [];
    let fenced = false;
    for (const line of content.split('\n')) {
      if (/^\s*(```|~~~)/.test(line)) { fenced = !fenced; continue; }
      if (fenced) continue;
      const match = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
      if (match) items.push({ level: match[1].length, text: match[2].replace(/[*_~`]/g, '').trim() });
    }
    return items;
  });

  let depth = $state(1);
  let localGraph: Graph | null = null;
  let localKey = '';
  // Links refresh on every save; keep the settled layout unless the neighborhood actually changed.
  const local = $derived.by(() => {
    if (!path || tab !== 'graph') return null;
    const next = buildGraph(links, { scope: localScope(links, path, depth) });
    const key = [path, ...next.nodes.map((node) => node.id), ...next.edges.map((edge) => `${edge.source}-${edge.target}`)].join('|');
    if (key !== localKey) { localKey = key; localGraph = next; }
    return localGraph;
  });

  // Falls back when Periodic Notes is disabled while the calendar tab is selected.
  const activeTab = $derived(tab === 'calendar' && !periodic ? 'backlinks' : tab);

  const tabs = $derived<{ id: Tab; label: string }[]>([
    { id: 'backlinks', label: 'Backlinks' },
    { id: 'outline', label: 'Outline' },
    { id: 'graph', label: 'Local graph' },
    { id: 'meta', label: 'Metadata' },
    ...(periodic ? [{ id: 'calendar' as const, label: 'Calendar' }] : []),
  ]);

  function open_(next: Tab) { onTab(next); onOpenChange(true); }
</script>

<aside id="right-panel" class:expanded={open}>
  {#snippet icon(id: Tab)}
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {#if id === 'backlinks'}<path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"/>
      {:else if id === 'outline'}<path d="M8 6h12M10 12h10M12 18h8M4 6h.01M6 12h.01M8 18h.01"/>
      {:else if id === 'graph'}<circle cx="6" cy="7" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.3 8.2 10.8 16M15.9 7.6 13.2 15.9M8.5 6.8l7-.6"/>
      {:else if id === 'meta'}<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5h.01"/>
      {:else}<path d="M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z"/><path d="M8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01M16 17h.01"/>{/if}
    </svg>
  {/snippet}
  <div class="right-rail">
    {#each tabs as item}<button class="rail-btn" onclick={() => open_(item.id)} title={item.label} aria-label={item.label}>{@render icon(item.id)}</button>{/each}
  </div>
  {#if open}
    <div id="right-panel-content">
      <div id="panel-tabs" role="tablist" aria-label="Note details">
        <div class="panel-tab-selector">
          {#each tabs as item}<button type="button" role="tab" aria-selected={activeTab === item.id} class="panel-tab" class:active={activeTab === item.id} onclick={() => onTab(item.id)} title={item.label} aria-label={item.label}>{@render icon(item.id)}</button>{/each}
        </div>
        <button type="button" class="panel-close" onclick={() => onOpenChange(false)} title="Close panel" aria-label="Close panel">×</button>
      </div>
      <div id="panel-body" class:graph-tab={activeTab === 'graph'}>
        {#if activeTab === 'calendar' && periodic}
          <Calendar settings={periodic} {files} currentFile={path} {onOpenDate} />
        {:else if !path}<span class="panel-empty">Open a note to see its links, outline, and metadata.</span>
        {:else if activeTab === 'backlinks'}
          <div class="meta-key">Backlinks ({backlinks.length})</div>
          {#each backlinks as backlink}
            <button class="backlink-card" onclick={() => onOpenFile(backlink)}>
              <span class="bl-path">{backlink}</span>
              {#if snippets[backlink]}<span class="bl-snippet">{snippets[backlink]}</span>{/if}
            </button>
          {:else}<span class="panel-empty">No backlinks yet.</span>{/each}
          {#if outgoing.length}<div class="meta-key section">Links out ({outgoing.length})</div>{/if}
          {#each outgoing as target}<button class="backlink-card" onclick={() => onOpenFile(target)}><span class="bl-path">{target}</span></button>{/each}
        {:else if activeTab === 'graph'}
          <label class="local-depth">Depth <select bind:value={depth}>{#each [1, 2, 3] as value}<option {value}>{value}</option>{/each}</select></label>
          {#if local}{#key local}<GraphView graph={local} current={path} groupColors={graphColors} onOpen={onOpenFile} />{/key}{/if}
        {:else if activeTab === 'outline'}
          {#each outline as heading}
            <button class="outline-item lvl-{heading.level}" style={`padding-left:${(heading.level - 1) * 12 + 8}px`} onclick={() => onOpenOutline(heading.text)}>{heading.text}</button>
          {:else}<span class="panel-empty">No headings in this note.</span>{/each}
        {:else}
          {#if metadata.error}<div class="cm-diagram-err">{metadata.error}</div>{/if}
          {#each metadata.fields as field}
            <div class="meta-row"><span class="meta-key">{field.key}</span><span class="meta-val">{field.key === 'tags' ? '' : field.value}{#if field.key === 'tags'}{#each metadata.tags as tag}<span class="panel-chip">{tag}</span>{/each}{/if}</span></div>
          {/each}
          <div class="meta-row"><span class="meta-key">words</span><span class="meta-val">{metadata.words}</span></div>
        {/if}
      </div>
    </div>
  {/if}
</aside>

<style>
  .backlink-card { display: flex; flex-direction: column; }
  .section { margin-top: 14px; }
  #panel-body.graph-tab { display: flex; flex-direction: column; overflow: hidden; }
  .local-depth { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; color: var(--text-sec); font-size: calc(12px * var(--ui-scale, 1)); }
  .local-depth select { border: 1px solid var(--border); border-radius: 4px; color: inherit; background: var(--bg-elev); }
</style>
