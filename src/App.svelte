<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import ActionModal, { type ModalState } from './components/ActionModal.svelte';
  import AppHeader from './components/AppHeader.svelte';
  import EditorPane from './components/EditorPane.svelte';
  import ExcalidrawEditor from './components/ExcalidrawEditor.svelte';
  import FileContextMenu, { type ContextMenuState } from './components/FileContextMenu.svelte';
  import LeftSidebar from './components/LeftSidebar.svelte';
  import MarkdownEditor, { type EditorViewState } from './components/MarkdownEditor.svelte';
  import MediaViewer from './components/MediaViewer.svelte';
  import RightPanel from './components/RightPanel.svelte';
  import SearchPalette from './components/SearchPalette.svelte';
  import Settings from './components/Settings.svelte';
  import { api } from './lib/api';
  import { encodeBase64, pastedImageName } from './lib/attachments';
  import { newDrawingContent, newDrawingFilename } from './lib/drawings';
  import { excalidrawRenderer } from './lib/excalidraw-renderer';
  import { folderNotePath, folderNoteRename, withFolderNotes } from './lib/folder-notes';
  import { buildGraph, groupColors, type Graph } from './lib/graph';
  import {
    GRAPH_ENTRY,
    canGoBack as historyCanGoBack,
    canGoForward as historyCanGoForward,
    createHistoryState,
    dropHistory,
    peekHistory,
    recordHistoryVisit,
    remapHistory,
  } from './lib/history';
  import {
    FLOATING_PANELS_QUERY,
    RIGHT_WIDTH_DEFAULT,
    TREE_WIDTH_DEFAULT,
    computeResizedWidth,
  } from './lib/layout';
  import { parseMetadata } from './lib/metadata';
  import { containsPath, flattenFiles, parentPath, remapDescendant } from './lib/paths';
  import { isoDate } from './lib/periodic';
  import { DEFAULT_RECENT_DISPLAY, dropRecent, isRecentFile, loadRecent, pushRecent, remapRecent, saveRecent, type RecentEntry, type RecentTab } from './lib/recent';
  import { SaveCoordinator } from './lib/save-coordinator';
  import { detectSearchMode, matchGlobalShortcut } from './lib/shortcuts';
  import { createAppState } from './lib/state.svelte';
  import { ApiError, type AppSettings, type LinksIndex, type RecentFile, type SearchMode, type SearchResult, type VaultsInfo } from './lib/types';
  import { titleFromContent, uniqueNotePath } from './lib/untitled';

  const appState = createAppState();
  const saves = new SaveCoordinator();
  let editor = $state<MarkdownEditor | undefined>();
  let drawingEditor = $state<ExcalidrawEditor | undefined>();
  let content = $state('');
  let query = $state('');
  let results = $state<SearchResult[]>([]);
  let searchOpen = $state(false);
  let searchMode = $state<SearchMode>('all');
  let searchLoading = $state(false);
  let searchError = $state<string | null>(null);
  let selectedDir = $state<string | null>(null);
  let panelTab = $state<'backlinks' | 'meta' | 'outline' | 'graph' | 'calendar'>('backlinks');
  let links = $state<LinksIndex>({});
  let backlinkSnippets = $state<Record<string, string>>({});
  let error = $state<string | null>(null);
  let loading = $state(false);
  let editorKey = $state(0);
  let modal = $state<ModalState | null>(null);
  let context = $state<ContextMenuState | null>(null);
  let mediaOpen = $state(false);
  let theme = $state<'light' | 'dark'>('dark');
  let aesthetic = $state<'ink' | 'slate' | 'sage'>('ink');
  let reading = $state(false);
  let persistentLivePreview = $state(true);
  let fontSize = $state(16);
  let settings = $state<AppSettings | null>(null);
  let settingsOpen = $state(false);
  let defaultVault = $state('');
  let graph = $state.raw<Graph | null>(null);
  let graphOrphans = $state(false);
  let rebuildingLinks = $state(false);
  let graphHidden = $state.raw(new Set<string>(JSON.parse(localStorage.getItem('telar-graph-hidden-groups') || '[]')));
  const graphColors = $derived(groupColors(buildGraph(links)));
  let settingsLoading = $state(false);
  let settingsError = $state<string | null>(null);
  let revision = $state<string | null>(null);
  let conflict = $state<{ external: string; revision: string } | null>(null);
  let syncingExternal = false;
  let treeWidth = $state(TREE_WIDTH_DEFAULT);
  let rightWidth = $state(RIGHT_WIDTH_DEFAULT);
  let resizing = $state(false);
  let explorerOpen = $state(true);
  let poll: ReturnType<typeof setInterval> | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let searchSequence = 0;
  let history = $state(createHistoryState());
  let navigatingHistory = false;
  // Where each note was left, so Back/Forward return to the same spot.
  const noteViews = new Map<string, EditorViewState>();
  // A new note that is named from its first line until the user leaves it; `created` flips on first save.
  let draft: { created: boolean } | null = null;
  let recentOpened = $state<RecentEntry[]>([]);
  let recentTab = $state<RecentTab>('opened');
  let recentFiles = $state<RecentFile[] | null>(null);
  let recentError = $state<string | null>(null);
  let recentSequence = 0;
  let pathCopied = $state(false);
  let pathCopiedTimer: ReturnType<typeof setTimeout> | undefined;

  const fileSet = $derived(flattenFiles(appState.tree));
  const folderNotesEnabled = $derived(settings?.vault_settings.plugins['folder-notes']?.enabled ?? true);
  const treeNodes = $derived(folderNotesEnabled ? withFolderNotes(appState.tree) : appState.tree);
  const recentSettings = $derived(settings?.vault_settings.plugins['recent-files']);
  const recentEnabled = $derived(recentSettings?.enabled ?? true);
  const periodicSettings = $derived(settings?.vault_settings.plugins['periodic-notes']);
  const calendarEnabled = $derived(periodicSettings?.enabled ?? false);
  const leftPanel = $derived(recentEnabled ? appState.leftPanel : 'explorer');
  const recentVisible = $derived(explorerOpen && !reading && leftPanel === 'recent');
  const recentLimit = $derived(recentSettings?.limit ?? DEFAULT_RECENT_DISPLAY);
  const recentOpenedVisible = $derived(recentOpened.filter((entry) => isRecentFile(entry.path) && fileSet.has(entry.path)).slice(0, recentLimit));
  const metadata = $derived(parseMetadata(content));
  const canGoBack = $derived(historyCanGoBack(history));
  const canGoForward = $derived(historyCanGoForward(history));
  const markdown = (path: string | null) => !!path && /\.(md|markdown)$/i.test(path);
  const drawingsEnabled = $derived(settings?.vault_settings.plugins.excalidraw.enabled ?? true);
  const taskAutoSuggestEnabled = $derived((settings?.vault_settings.plugins.tasks.enabled ?? true) && (settings?.vault_settings.plugins.tasks.auto_suggest ?? true));
  // With the plugin off, `.excalidraw.md` opens as Markdown and `.excalidraw` as raw text, as in Obsidian.
  const drawing = (path: string | null) => drawingsEnabled && !!path && /\.excalidraw(?:\.md)?$/i.test(path);
  const media = (path: string | null) => !!path && /\.(png|jpe?g|gif|webp|svg)$/i.test(path);
  const title = (path: string | null) => metadata.title || path?.split('/').at(-1)?.replace(/\.(excalidraw\.md|excalidraw|md|markdown)$/i, '') || '';
  const friendlyError = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback;
  const currentFileStorageKey = (vault: string) => `telar-current-file:${vault}`;

  function rememberCurrentFile(path: string | null): void {
    const vault = appState.activeVault;
    if (!vault) return;
    if (path) localStorage.setItem(currentFileStorageKey(vault), path);
    else localStorage.removeItem(currentFileStorageKey(vault));
  }

  async function restoreCurrentFile(): Promise<void> {
    const vault = appState.activeVault;
    if (!vault) return;
    const path = localStorage.getItem(currentFileStorageKey(vault));
    if (!path) return;
    if (!flattenFiles(appState.tree).has(path)) {
      rememberCurrentFile(null);
      return;
    }
    await openFile(path);
  }

  async function refreshTree(): Promise<void> { appState.tree = (await api.files()).tree; }
  async function refreshLinks(): Promise<void> {
    links = await api.links();
    await refreshBacklinkSnippets();
  }

  async function rebuildLinkIndex(): Promise<void> {
    rebuildingLinks = true;
    try {
      links = await api.rebuildLinks();
      rebuildGraph();
      await refreshBacklinkSnippets();
    } catch (e) { error = e instanceof Error ? e.message : String(e); }
    finally { rebuildingLinks = false; }
  }

  async function refreshBacklinkSnippets(): Promise<void> {
    const path = appState.currentFile;
    const sources = path ? links[path]?.linked_from ?? [] : [];
    if (!path || !sources.length) { backlinkSnippets = {}; return; }
    const stem = path.replace(/\.md$/i, '').split('/').at(-1) || '';
    const entries = await Promise.all(sources.map(async (source): Promise<[string, string]> => {
      try {
        const note = await api.note(source);
        const line = note.content.split('\n').find((value) => value.includes(`[[${stem}`) || value.includes(path));
        return [source, (line || '').trim().slice(0, 120)];
      } catch { return [source, '']; }
    }));
    if (appState.currentFile === path) backlinkSnippets = Object.fromEntries(entries);
  }

  function saveError(message: string): void {
    appState.saveStatus = 'error';
    error = message;
  }

  function recordVisit(path: string): void {
    if (navigatingHistory) return;
    history = recordHistoryVisit(history, path);
  }

  function rememberView(): void {
    const view = appState.currentFile ? editor?.viewState() : undefined;
    if (view) noteViews.set(appState.currentFile!, view);
  }

  // Reloading recreates the editor; keep the reader where they were.
  async function remountEditor(): Promise<void> {
    const view = editor?.viewState();
    editorKey += 1;
    if (!view) return;
    await tick();
    editor?.restoreView(view);
  }

  async function goHistory(delta: number): Promise<void> {
    const target = peekHistory(history, delta);
    if (!target) return;
    if (target === GRAPH_ENTRY) {
      rebuildGraph();
      history = { ...history, index: history.index + delta };
      return;
    }
    navigatingHistory = true;
    try {
      await openFile(target);
      if (appState.currentFile !== target) return;
      history = { ...history, index: history.index + delta };
      const view = noteViews.get(target);
      if (view) { await tick(); editor?.restoreView(view); }
    } finally { navigatingHistory = false; }
  }

  function trackRecent(next: RecentEntry[]): void {
    recentOpened = next;
    if (appState.activeVault) saveRecent(appState.activeVault, next);
  }

  async function refreshRecent(): Promise<void> {
    if (!recentVisible || recentTab === 'opened') return;
    const sequence = ++recentSequence;
    try {
      const response = await api.recentFiles(recentTab, recentLimit);
      if (sequence === recentSequence) { recentFiles = response.files; recentError = null; }
    } catch (cause) {
      if (sequence === recentSequence) recentError = friendlyError(cause, 'Could not load recent files.');
    }
  }

  function selectRecentTab(tab: RecentTab): void {
    if (tab === recentTab) return;
    recentTab = tab;
    recentFiles = null;
    recentError = null;
  }

  async function beforeNavigate(): Promise<boolean> {
    if (conflict) {
      saveError('Resolve the external-change conflict before changing notes or vaults.');
      return false;
    }
    rememberView();
    if (drawingEditor && !await drawingEditor.flush()) {
      saveError('Could not save the drawing; navigation was cancelled.');
      return false;
    }
    const flushed = await saves.flush();
    if (!flushed.ok) {
      saveError('Could not save pending changes; navigation was cancelled.');
      return false;
    }
    draft = null;
    return true;
  }

  function rebuildGraph(): void { graph = buildGraph(links, { orphans: graphOrphans, hiddenGroups: graphHidden }); }
  function openGraph(): void {
    rememberView();
    rebuildGraph();
    recordVisit(GRAPH_ENTRY);
  }
  // Leaving the graph without opening another note still adds a step, so Back returns to it.
  function closeGraph(): void {
    graph = null;
    if (appState.currentFile) recordVisit(appState.currentFile);
  }
  function toggleGraph(): void { if (graph) closeGraph(); else openGraph(); }
  function toggleGraphGroup(group: string): void {
    const next = new Set(graphHidden);
    if (!next.delete(group)) next.add(group);
    graphHidden = next;
    localStorage.setItem('telar-graph-hidden-groups', JSON.stringify([...next]));
    rebuildGraph();
  }

  async function openFile(path: string, anchor?: string, line?: number): Promise<void> {
    if (!path) return;
    if (path === appState.currentFile) {
      if (graph) closeGraph();
      if (anchor) editor?.revealAnchor(anchor);
      else if (line !== undefined) editor?.revealLine(line);
      closeSidePanelsOnNarrow();
      return;
    }
    if (!await beforeNavigate()) return;
    graph = null;
    loading = true;
    error = null;
    try {
      let nextContent = '';
      let noteRevision: string | null = null;
      if (!media(path)) {
        const note = await api.note(path);
        nextContent = note.content;
        noteRevision = note.revision;
      }
      appState.currentFile = path;
      rememberCurrentFile(path);
      recordVisit(path);
      trackRecent(pushRecent(recentOpened, path));
      selectedDir = parentPath(path) || null;
      content = nextContent;
      revision = noteRevision;
      conflict = null;
      editorKey += 1;
      mediaOpen = false;
      await refreshLinks();
      loading = false;
      closeSidePanelsOnNarrow();
      if (anchor) {
        await tick();
        editor?.revealAnchor(anchor);
      } else if (line !== undefined) {
        await tick();
        editor?.revealLine(line);
      }
    } catch (cause) { error = friendlyError(cause, 'Could not open file.'); }
    finally { loading = false; }
  }

  async function saveDraft(state: { created: boolean }, value: string): Promise<void> {
    const current = appState.currentFile!;
    const dir = parentPath(current);
    const desiredPath = () => {
      const taken = new Set(fileSet);
      taken.delete(current);
      return uniqueNotePath(dir, titleFromContent(value) || 'Untitled', taken);
    };
    if (!state.created) {
      if (!value.trim()) return;
      let desired = desiredPath();
      let result: { revision: string };
      try { result = await api.saveNote(desired, value, null); }
      catch (cause) {
        if (!(cause instanceof ApiError && cause.status === 409)) throw cause;
        await refreshTree();
        desired = desiredPath();
        result = await api.saveNote(desired, value, null);
      }
      state.created = true;
      appState.currentFile = desired;
      revision = result.revision;
      rememberCurrentFile(desired);
      recordVisit(desired);
      trackRecent(pushRecent(recentOpened, desired));
      return;
    }
    const desired = desiredPath();
    if (desired !== current) {
      try { await applyRename(current, desired); }
      catch (cause) { if (!(cause instanceof ApiError && cause.status === 409)) throw cause; }
    }
    const result = await api.saveNote(appState.currentFile!, value, revision);
    revision = result.revision;
  }

  function changed(value: string): void {
    if (syncingExternal) return;
    content = value;
    const path = appState.currentFile;
    if (!path) return;
    const state = draft;
    appState.saveStatus = 'saving';
    saves.schedule(async () => {
      try {
        if (state && draft === state) await saveDraft(state, value);
        else {
          const result = await api.saveNote(path, value, revision);
          revision = result.revision;
        }
        appState.saveStatus = 'saved';
        error = null;
        await Promise.all([refreshTree(), refreshLinks(), refreshRecent()]);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 409) {
          const latest = await api.note(appState.currentFile ?? path).catch(() => null);
          if (latest) conflict = { external: latest.content, revision: latest.revision };
          saves.discard();
        }
        saveError(friendlyError(cause, 'Could not save note.'));
        throw cause;
      }
    });
  }

  async function saveDrawing(path: string, value: string): Promise<void> {
    appState.saveStatus = 'saving';
    try {
      const result = await api.saveNote(path, value, revision);
      revision = result.revision;
      content = value;
      appState.saveStatus = 'saved';
      excalidrawRenderer.invalidate(path);
      await Promise.all([refreshTree(), refreshLinks(), refreshRecent()]);
    } catch (cause) {
      saveError(friendlyError(cause, 'Could not save drawing.'));
      throw cause;
    }
  }

  async function saveNow(): Promise<void> {
    const flushed = await saves.flush();
    if (!flushed.ok) saveError('Could not save note.');
    else appState.saveStatus = 'saved';
  }

  async function openDaily(date = new Date()): Promise<void> {
    if (!await beforeNavigate()) return;
    try {
      const note = await api.today(isoDate(date));
      if (note.created) await refreshTree();
      appState.currentFile = note.path;
      rememberCurrentFile(note.path);
      recordVisit(note.path);
      trackRecent(pushRecent(recentOpened, note.path));
      selectedDir = parentPath(note.path) || null;
      content = note.content;
      revision = note.revision;
      conflict = null;
      editorKey += 1;
      await refreshLinks();
      closeSidePanelsOnNarrow();
    } catch (cause) { error = friendlyError(cause, 'Could not open daily note.'); }
  }

  function applyVaults(info: VaultsInfo): void {
    appState.vaults = info.vaults;
    appState.activeVault = info.active;
    defaultVault = info.default;
  }

  async function switchFromSettings(name: string): Promise<void> {
    settingsOpen = false;
    await changeVault(name);
  }

  async function openDocs(): Promise<void> {
    try {
      const { help, ...info } = await api.openHelpVault();
      applyVaults(info);
      window.open(`/?vault=${encodeURIComponent(help)}&open=Home.md`, '_blank');
    } catch (cause) {
      error = friendlyError(cause, 'Could not open the docs.');
    }
  }

  async function changeVault(name: string): Promise<void> {
    if (!name || name === appState.activeVault || !await beforeNavigate()) return;
    loading = true;
    try {
      await api.switchVault(name);
      appState.activeVault = name;
      appState.currentFile = null;
      selectedDir = null;
      content = '';
      editorKey += 1;
      history = createHistoryState();
      noteViews.clear();
      recentOpened = loadRecent(name);
      recentFiles = null;
      applySettings(await api.settings());
      await Promise.all([refreshTree(), refreshLinks()]);
      error = null;
      await restoreCurrentFile();
    } catch (cause) { error = friendlyError(cause, 'Could not switch vault.'); }
    finally { loading = false; }
  }

  function scheduleSearch(raw: string): void {
    query = raw;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => void runSearch(raw), 120);
  }

  async function runSearch(raw = query): Promise<void> {
    const detected = detectSearchMode(raw, searchMode);
    searchMode = detected.mode;
    const term = detected.query.trim();
    if (!term) { results = []; searchLoading = false; searchError = null; return; }
    const sequence = ++searchSequence;
    searchLoading = true;
    searchError = null;
    try {
      const response = await api.search(term, detected.mode);
      if (sequence === searchSequence) results = response.results;
    } catch (cause) {
      if (sequence === searchSequence) searchError = friendlyError(cause, 'Search failed.');
    } finally { if (sequence === searchSequence) searchLoading = false; }
  }

  function selectSearchMode(mode: SearchMode): void {
    searchMode = mode;
    void runSearch(query.replace(/^(\/|\[\[|#)/, ''));
  }

  function closeSearch(): void {
    searchOpen = false;
    query = '';
    results = [];
    searchError = null;
  }

  async function newFile(dir = selectedDir || ''): Promise<void> {
    if (!await beforeNavigate()) return;
    graph = null;
    appState.currentFile = uniqueNotePath(dir, 'Untitled', fileSet);
    selectedDir = dir || null;
    content = '';
    revision = null;
    conflict = null;
    mediaOpen = false;
    draft = { created: false };
    editorKey += 1;
    closeSidePanelsOnNarrow();
  }

  function newFolder(dir = selectedDir || ''): void {
    modal = { title: 'New folder', label: 'Create', value: dir ? `${dir}/untitled` : 'untitled', input: true, action: async (path) => {
      await api.mkdir(path);
      await refreshTree();
    } };
  }

  async function applyRename(from: string, to: string): Promise<void> {
    await api.rename(from, to);
    appState.currentFile = remapDescendant(appState.currentFile, from, to);
    rememberCurrentFile(appState.currentFile);
    history = remapHistory(history, from, to);
    trackRecent(remapRecent(recentOpened, from, to));
    selectedDir = remapDescendant(selectedDir, from, to);
  }

  /** After a folder rename, carry its folder note along (`B/A.md` -> `B/B.md`). */
  async function renameFolderNote(from: string, to: string): Promise<void> {
    if (!folderNotesEnabled) return;
    await refreshTree();
    const pair = folderNoteRename(from, to, appState.tree);
    if (!pair) return;
    try { await applyRename(...pair); }
    catch (cause) { if (!(cause instanceof ApiError && cause.status === 409)) throw cause; }
  }

  function rename(path: string): void {
    modal = { title: 'Rename', label: 'Rename', value: path, input: true, action: async (to) => {
      if (containsPath(path, appState.currentFile) && !await beforeNavigate()) return;
      await applyRename(path, to);
      await renameFolderNote(path, to);
      await Promise.all([refreshTree(), refreshLinks()]);
    } };
  }

  function remove(path: string): void {
    modal = { title: 'Move to trash?', label: 'Move to trash', value: '', danger: true, action: async () => {
      if (containsPath(path, appState.currentFile) && !await beforeNavigate()) return;
      await api.delete(path);
      if (containsPath(path, appState.currentFile)) { appState.currentFile = null; rememberCurrentFile(null); content = ''; editorKey += 1; }
      history = dropHistory(history, path);
      trackRecent(dropRecent(recentOpened, path));
      if (containsPath(path, selectedDir)) selectedDir = null;
      await Promise.all([refreshTree(), refreshLinks()]);
    } };
  }

  async function move(from: string, target: string): Promise<void> {
    if (!from || target === from || target.startsWith(`${from}/`)) return;
    const to = target ? `${target}/${from.split('/').at(-1)}` : from.split('/').at(-1) || from;
    if (parentPath(from) === target) return;
    if (containsPath(from, appState.currentFile) && !await beforeNavigate()) return;
    try {
      await applyRename(from, to);
      await renameFolderNote(from, to);
      await Promise.all([refreshTree(), refreshLinks()]);
    } catch (cause) { error = friendlyError(cause, 'Could not move item.'); }
  }

  async function confirmModal(): Promise<void> {
    const current = modal;
    if (!current) return;
    const value = current.value.trim();
    if (current.input && !value) return;
    modal = null;
    try { await current.action(value); }
    catch (cause) { error = friendlyError(cause, 'Operation failed.'); }
  }

  function contextMenu(event: MouseEvent, path: string, isDir: boolean): void {
    event.preventDefault();
    event.stopPropagation();
    context = { x: event.clientX, y: event.clientY, path, isDir };
  }

  function selectDir(path: string): void { selectedDir = path; }

  async function openFolder(dir: string, note: string): Promise<void> {
    await openFile(note);
    if (appState.currentFile !== note) return;
    selectDir(dir);
    if (!appState.explorerExpanded.has(dir)) appState.togglePath(dir);
  }

  async function folderNoteAction(dir: string): Promise<void> {
    const note = folderNotePath(dir);
    try {
      if (!fileSet.has(note)) {
        await api.saveNote(note, '', null);
        await refreshTree();
      }
      await openFolder(dir, note);
    } catch (cause) { error = friendlyError(cause, 'Could not open the folder note.'); }
  }

  async function copyAbsolutePath(path: string): Promise<void> {
    const root = appState.vaults.find((vault) => vault.name === appState.activeVault)?.path;
    if (!root) return;
    try {
      await navigator.clipboard.writeText(`${root.replace(/\/$/, '')}/${path}`);
      pathCopied = true;
      clearTimeout(pathCopiedTimer);
      pathCopiedTimer = setTimeout(() => pathCopied = false, 1200);
    } catch (cause) { error = friendlyError(cause, 'Could not copy the path.'); }
  }

  async function focusInExplorer(): Promise<void> {
    const path = appState.currentFile;
    if (!path) return;
    appState.leftPanel = 'explorer';
    setExplorerOpen(true);
    const parts = path.split('/');
    for (let index = 1; index < parts.length; index += 1) {
      const parent = parts.slice(0, index).join('/');
      if (!appState.explorerExpanded.has(parent)) appState.togglePath(parent);
    }
    await tick();
    const item = document.querySelector<HTMLElement>(`[data-path="${CSS.escape(path)}"]`);
    item?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    item?.focus();
    item?.classList.add('explorer-focus');
    setTimeout(() => item?.classList.remove('explorer-focus'), 1200);
  }

  function toggleReading(): void { reading = !reading; localStorage.setItem('telar-reading', String(reading)); editor?.refresh(); }
  function setExplorerOpen(open: boolean): void {
    explorerOpen = open;
    localStorage.setItem('telar-explorer-open', String(open));
  }
  function closeSidePanelsOnNarrow(): void {
    if (!window.matchMedia(FLOATING_PANELS_QUERY).matches) return;
    setExplorerOpen(false);
    appState.rightOpen = false;
  }
  function toggleLeftPanel(panel: typeof appState.leftPanel): void {
    if (explorerOpen && leftPanel === panel) { setExplorerOpen(false); return; }
    appState.leftPanel = panel;
    setExplorerOpen(true);
  }
  function applySettings(next: AppSettings): void {
    // Embed widgets are built once per editor mount, so a plugin toggle needs a remount.
    if (settings && JSON.stringify(settings.vault_settings.plugins.excalidraw) !== JSON.stringify(next.vault_settings.plugins.excalidraw)) editorKey += 1;
    settings = next;
    theme = next.preferences.theme;
    aesthetic = next.preferences.aesthetic;
    fontSize = next.preferences.font_size;
    document.documentElement.style.setProperty('--ui-scale', String(next.preferences.ui_font_size / 14));
    persistentLivePreview = next.preferences.persistent_live_preview;
    document.documentElement.dataset.theme = theme;
    editor?.refresh();
  }

  async function toggleTheme(): Promise<void> {
    const next = theme === 'dark' ? 'light' : 'dark';
    theme = next;
    document.documentElement.dataset.theme = next;
    if (!settings) return;
    try { applySettings(await api.saveSettings({ ...settings.preferences, theme: next }, settings.vault_settings)); }
    catch (cause) { error = friendlyError(cause, 'Could not save the theme.'); }
  }

  async function openSettings(): Promise<void> {
    settingsOpen = true;
    settingsLoading = true;
    settingsError = null;
    try {
      const [loadedSettings, vaultInfo] = await Promise.all([api.settings(), api.vaults()]);
      applySettings(loadedSettings);
      applyVaults(vaultInfo);
    } catch (cause) {
      settingsError = friendlyError(cause, 'Could not load settings.');
    } finally {
      settingsLoading = false;
    }
  }

  async function pollOpenNote(): Promise<void> {
    const path = appState.currentFile;
    if (!path || !markdown(path) || drawing(path) || conflict) return;
    try {
      const latest = await api.note(path);
      if (path !== appState.currentFile || latest.revision === revision) return;
      if (appState.saveStatus === 'saving') {
        saves.discard();
        conflict = { external: latest.content, revision: latest.revision };
        saveError('This note changed outside Telar Notes. Resolve the conflict.');
        return;
      }
      syncingExternal = true;
      draft = null;
      content = latest.content;
      revision = latest.revision;
      await remountEditor();
      await Promise.all([refreshLinks(), refreshTree()]);
      queueMicrotask(() => { syncingExternal = false; });
    } catch (cause) {
      if (!(cause instanceof ApiError && cause.status === 404)) error = friendlyError(cause, 'Could not sync note.');
    }
  }

  function reloadExternal(): void {
    if (!conflict) return;
    saves.discard();
    draft = null;
    syncingExternal = true;
    content = conflict.external;
    revision = conflict.revision;
    conflict = null;
    void remountEditor();
    queueMicrotask(() => { syncingExternal = false; });
    appState.saveStatus = 'saved';
  }

  async function overwriteWithLocal(): Promise<void> {
    if (!conflict || !appState.currentFile) return;
    try {
      const result = await api.saveNote(appState.currentFile, content, conflict.revision, true);
      revision = result.revision;
      conflict = null;
      appState.saveStatus = 'saved';
      await Promise.all([refreshTree(), refreshLinks()]);
    } catch (cause) { saveError(friendlyError(cause, 'Could not overwrite the external note.')); }
  }

  async function attach(file: File, dir?: string, filename = file.name): Promise<void> {
    const data_b64 = encodeBase64(new Uint8Array(await file.arrayBuffer()));
    const result = await api.attach(dir
      ? { dir, filename, data_b64 }
      : { note: appState.currentFile!, filename, data_b64 });
    await refreshTree();
    if (!dir) editor?.insertText(`![[${result.embed}]]`);
  }

  async function newDrawing(): Promise<void> {
    const note = appState.currentFile;
    if (!note) return;
    try {
      const filename = newDrawingFilename(note, new Date());
      const data_b64 = encodeBase64(new TextEncoder().encode(newDrawingContent()));
      const result = await api.attach({ note, filename, data_b64 });
      await refreshTree();
      // Obsidian writes drawing embeds without the trailing `.md`.
      editor?.insertText(`\n![[${result.embed.replace(/\.md$/i, '')}]]\n`);
    } catch (cause) { error = friendlyError(cause, 'Could not create drawing.'); }
  }

  function pickImage(): void {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.multiple = true;
    input.onchange = () => { for (const file of input.files ?? []) if (appState.currentFile) void attach(file); };
    input.click();
  }

  // Paste inside the editor always attaches to the open note (selectedDir tracks the
  // note's own folder, so it must not route the file into the tree-drop branch).
  function paste(event: ClipboardEvent): void {
    const files = [...(event.clipboardData?.files ?? [])];
    if (!files.length || !appState.currentFile || !files.some((file) => file.type.startsWith('image/'))) return;
    event.preventDefault();
    for (const file of files) {
      if (!file.type.startsWith('image/')) continue;
      void attach(file, undefined, pastedImageName(file)).catch((cause) => { error = friendlyError(cause, 'Could not attach file.'); });
    }
  }

  function beginResize(event: PointerEvent, side: 'left' | 'right' = 'left'): void {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = side === 'left' ? treeWidth : rightWidth;
    resizing = true;
    const movePointer = (move: PointerEvent) => {
      const next = computeResizedWidth(side, startWidth, move.clientX - startX);
      if (side === 'left') treeWidth = next;
      else rightWidth = next;
    };
    const stop = () => {
      resizing = false;
      window.removeEventListener('pointermove', movePointer);
      window.removeEventListener('pointerup', stop);
      localStorage.setItem(side === 'left' ? 'telar-tree-width' : 'telar-right-width', String(side === 'left' ? treeWidth : rightWidth));
    };
    window.addEventListener('pointermove', movePointer);
    window.addEventListener('pointerup', stop, { once: true });
  }

  function openSearch(mode: SearchMode): void {
    searchMode = mode;
    query = '';
    results = [];
    searchError = null;
    searchOpen = true;
  }

  function globalKey(event: KeyboardEvent): void {
    const action = matchGlobalShortcut(event, { graphOpen: !!graph, searchOpen });
    if (!action) return;
    if (action === 'close-graph') { closeGraph(); return; }
    event.preventDefault();
    if (action === 'search-content') openSearch('content');
    else if (action === 'search-title') openSearch('title');
    else if (action === 'search-current') openSearch(searchMode);
    else if (action === 'find-in-note') editor?.openFind();
    else if (action === 'save') void saveNow();
    else if (action === 'toggle-graph') toggleGraph();
    else if (action === 'new-file') void newFile();
    else if (action === 'history-back') void goHistory(-1);
    else if (action === 'history-forward') void goHistory(1);
  }

  function closeContext(): void { context = null; }

  $effect(() => {
    if (recentVisible && recentTab !== 'opened') void refreshRecent();
  });

  $effect(() => {
    void theme;
    void aesthetic;
    const appEl = document.getElementById('app');
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!appEl || !link) return;
    const style = getComputedStyle(appEl);
    const bg = style.getPropertyValue('--bg-elev').trim();
    const border = style.getPropertyValue('--border').trim();
    const warp = style.getPropertyValue('--text-pri').trim();
    const weft = style.getPropertyValue('--accent').trim();
    if (!bg || !warp || !weft) return;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect x="0.5" y="0.5" width="31" height="31" rx="7.5" fill="${bg}" stroke="${border}" stroke-width="1"/><path d="M9.5 6V12.3M9.5 19.7V26M16 6V26M22.5 6V12.3M22.5 19.7V26" fill="none" stroke="${warp}" stroke-width="2.6" stroke-linecap="round"/><path d="M5.5 16H12.3M19.7 16H26.5" fill="none" stroke="${weft}" stroke-width="2.9" stroke-linecap="round"/></svg>`;
    link.href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
  });

  onMount(async () => {
    theme = (localStorage.getItem('telar-theme') as 'light' | 'dark') || 'dark';
    aesthetic = (localStorage.getItem('telar-aesthetic') as 'ink' | 'slate' | 'sage') || 'ink';
    reading = localStorage.getItem('telar-reading') === 'true';
    persistentLivePreview = localStorage.getItem('telar-persistent-live-preview') !== 'false';
    treeWidth = Number(localStorage.getItem('telar-tree-width')) || TREE_WIDTH_DEFAULT;
    rightWidth = Number(localStorage.getItem('telar-right-width')) || RIGHT_WIDTH_DEFAULT;
    const storedExplorerOpen = localStorage.getItem('telar-explorer-open');
    explorerOpen = storedExplorerOpen === null ? !window.matchMedia(FLOATING_PANELS_QUERY).matches : storedExplorerOpen === 'true';
    try {
      applyVaults(await api.vaults());
      if (appState.activeVault) recentOpened = loadRecent(appState.activeVault);
      const loadedSettings = await api.settings();
      if (!localStorage.getItem('telar-settings-migrated')) {
        const migrated = await api.saveSettings({ theme, aesthetic, font_size: fontSize, ui_font_size: 14, persistent_live_preview: persistentLivePreview }, loadedSettings.vault_settings);
        localStorage.setItem('telar-settings-migrated', 'true');
        applySettings(migrated);
      } else applySettings(loadedSettings);
      await Promise.all([refreshTree(), refreshLinks()]);
      await restoreCurrentFile();
      const initial = new URLSearchParams(location.search).get('open');
      if (initial) await openFile(initial);
    } catch (cause) { error = friendlyError(cause, 'Could not load vault.'); }
    poll = setInterval(syncFromDisk, 2000);
    document.addEventListener('visibilitychange', syncFromDisk);
    window.addEventListener('keydown', globalKey);
    document.addEventListener('click', closeContext);
  });

  function syncFromDisk(): void {
    if (document.hidden) return;
    void refreshTree().catch(() => undefined);
    void refreshRecent();
    void pollOpenNote();
  }

  onDestroy(() => {
    if (poll) clearInterval(poll);
    clearTimeout(searchTimer);
    document.removeEventListener('visibilitychange', syncFromDisk);
    window.removeEventListener('keydown', globalKey);
    document.removeEventListener('click', closeContext);
  });
</script>

<svelte:head>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Hanken+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
</svelte:head>

<div id="app" data-theme={theme} data-aesthetic={aesthetic} class:reading class:explorer-open={explorerOpen} class:resizing style={`--tree-width:${treeWidth}px;--right-width:${rightWidth}px`}>
  <AppHeader
    activeVault={appState.activeVault}
    saveStatus={appState.saveStatus}
    {theme}
    {reading}
    {canGoBack}
    {canGoForward}
    onBack={() => void goHistory(-1)}
    onForward={() => void goHistory(1)}
    onOpenSettings={() => void openSettings()}
    onToggleTheme={() => void toggleTheme()}
    onToggleReading={toggleReading}
  />

  <main id="main">
    <LeftSidebar
      {explorerOpen}
      {leftPanel}
      {recentEnabled}
      {recentVisible}
      graphOpen={graph !== null}
      {recentTab}
      {recentOpenedVisible}
      {recentFiles}
      {recentError}
      currentFile={appState.currentFile}
      {treeNodes}
      {selectedDir}
      expanded={appState.explorerExpanded}
      onToggleLeftPanel={toggleLeftPanel}
      onCloseExplorer={() => setExplorerOpen(false)}
      onOpenSearch={() => searchOpen = true}
      onOpenDaily={() => void openDaily()}
      onToggleGraph={toggleGraph}
      onNewFile={() => void newFile()}
      onSelectRecentTab={selectRecentTab}
      onOpenFile={(path) => void openFile(path)}
      onTogglePath={(path) => appState.togglePath(path)}
      onSelectDir={selectDir}
      onOpenFolder={(dir, note) => void openFolder(dir, note)}
      onContext={contextMenu}
      onMove={(from, target) => void move(from, target)}
    />
    <div id="resize-handle" role="separator" aria-orientation="vertical" onpointerdown={beginResize}></div>

    <EditorPane
      bind:editor
      bind:drawingEditor
      {graph}
      bind:graphOrphans
      {rebuildingLinks}
      {graphColors}
      {graphHidden}
      currentFile={appState.currentFile}
      title={title(appState.currentFile)}
      tags={metadata.tags}
      {pathCopied}
      isMarkdown={markdown(appState.currentFile)}
      isDrawing={drawing(appState.currentFile)}
      isMedia={media(appState.currentFile)}
      {loading}
      {editorKey}
      {content}
      {fontSize}
      {fileSet}
      {reading}
      {persistentLivePreview}
      {drawingsEnabled}
      {taskAutoSuggestEnabled}
      drawingWidth={settings?.vault_settings.plugins.excalidraw.embed_width ?? 400}
      {error}
      {conflict}
      onRebuildGraph={rebuildGraph}
      onRebuildLinks={() => void rebuildLinkIndex()}
      onFocusExplorer={() => void focusInExplorer()}
      onCopyPath={(path) => void copyAbsolutePath(path)}
      onToggleGraphGroup={toggleGraphGroup}
      onOpenFile={(path, anchor, line) => void openFile(path, anchor, line)}
      onChange={changed}
      onSaveDrawing={saveDrawing}
      onMissingLink={(target) => { error = `“${target}” not found.`; }}
      onOpenMedia={() => mediaOpen = true}
      onPickImage={pickImage}
      onNewDrawing={() => void newDrawing()}
      onPaste={paste}
      onDismissError={() => error = null}
      onReloadExternal={reloadExternal}
      onOverwriteWithLocal={() => void overwriteWithLocal()}
    />

    {#if appState.rightOpen}<div id="right-resize-handle" role="separator" aria-orientation="vertical" onpointerdown={(event) => beginResize(event, 'right')}></div>{/if}
    <RightPanel open={appState.rightOpen} tab={panelTab} path={appState.currentFile} {content} {links} {graphColors} snippets={backlinkSnippets} periodic={calendarEnabled ? periodicSettings ?? null : null} files={fileSet} onOpenDate={(date) => void openDaily(date)} onOpenChange={(open) => appState.rightOpen = open} onTab={(tab) => panelTab = tab} onOpenFile={(path) => void openFile(path)} onOpenOutline={(heading) => editor?.revealAnchor(heading)} />
  </main>

  <footer id="statusbar"><span>{appState.activeVault || 'Telar Notes'}{appState.currentFile ? ` / ${appState.currentFile}` : ''}</span><span>{metadata.words} words · {media(appState.currentFile) ? 'Media' : drawing(appState.currentFile) ? 'Drawing source' : 'Live Preview'}</span></footer>

  <FileContextMenu
    {context}
    {folderNotesEnabled}
    {fileSet}
    onClose={closeContext}
    onFolderNote={(dir) => void folderNoteAction(dir)}
    onNewFile={(dir) => void newFile(dir)}
    onNewFolder={newFolder}
    onRename={rename}
    onReveal={(path) => void api.reveal(path).catch((cause) => error = friendlyError(cause, 'Could not reveal item.'))}
    onCopyPath={(path) => void copyAbsolutePath(path)}
    onRemove={remove}
  />

  <ActionModal bind:modal onConfirm={() => void confirmModal()} onClose={() => modal = null} />

  <SearchPalette open={searchOpen} {query} mode={searchMode} {results} loading={searchLoading} error={searchError} onClose={closeSearch} onQuery={scheduleSearch} onMode={selectSearchMode} onOpen={(path) => { closeSearch(); void openFile(path); }} />

  {#if settingsOpen}
    {#if settingsLoading}
      <div class="settings-overlay" role="presentation"><div class="settings-dialog settings-state" role="dialog" aria-modal="true" aria-label="Settings"><span>Loading settings…</span></div></div>
    {:else if settingsError}
      <div class="settings-overlay" role="presentation"><div class="settings-dialog settings-state" role="dialog" aria-modal="true" aria-label="Settings"><p class="settings-error" role="alert">{settingsError}</p><button class="header-btn" onclick={() => void openSettings()}>Retry</button><button class="header-btn" onclick={() => settingsOpen = false}>Close</button></div></div>
    {:else if settings}
      <Settings {settings} vaults={{ vaults: appState.vaults, active: appState.activeVault, default: defaultVault }} onClose={() => settingsOpen = false} onSaved={applySettings} onVaultsChanged={applyVaults} onSwitchVault={(name) => void switchFromSettings(name)} onOpenDocs={() => void openDocs()} />
    {/if}
  {/if}

  <MediaViewer open={mediaOpen} file={appState.currentFile} onClose={() => mediaOpen = false} />
</div>
