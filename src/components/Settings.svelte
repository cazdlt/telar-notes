<script lang="ts">
  import { untrack } from 'svelte';
  import { api } from '../lib/api';
  import type { AppSettings, VaultsInfo } from '../lib/types';
  import { dailyNotePath } from '../lib/periodic';

  let { settings, vaults, onClose, onSaved, onVaultsChanged, onSwitchVault, onOpenDocs }: { settings: AppSettings; vaults: VaultsInfo; onClose: () => void; onSaved: (settings: AppSettings) => void; onVaultsChanged: (vaults: VaultsInfo) => void; onSwitchVault: (name: string) => void; onOpenDocs: () => void } = $props();
  function copySettings(value: AppSettings): AppSettings {
    return {
      preferences: { ...value.preferences },
      vault: value.vault,
      vault_settings: {
        files: { ...value.vault_settings.files },
        plugins: {
          tasks: { ...value.vault_settings.plugins.tasks },
          'periodic-notes': { ...value.vault_settings.plugins['periodic-notes'] },
          'recent-files': { ...value.vault_settings.plugins['recent-files'] },
          excalidraw: { ...value.vault_settings.plugins.excalidraw },
          'folder-notes': { ...value.vault_settings.plugins['folder-notes'] },
        },
      },
      settings_version: value.settings_version,
    };
  }

  const APP_PANES = [['appearance', 'Appearance'], ['vaults', 'Vaults']] as const;
  const VAULT_PANES = [['files', 'Files'], ['tasks', 'Tasks'], ['periodic-notes', 'Periodic notes'], ['recent-files', 'Recent files'], ['excalidraw', 'Excalidraw'], ['folder-notes', 'Folder notes']] as const;
  type Pane = (typeof APP_PANES)[number][0] | (typeof VAULT_PANES)[number][0];

  let pane = $state<Pane>('appearance');
  let notice = $state<string | null>(null);
  let draft = $state<AppSettings>(untrack(() => copySettings(settings)));
  let error = $state<string | null>(null);
  let status = $state<'idle' | 'saving' | 'saved'>('idle');
  let lastSaved = untrack(() => JSON.stringify(draft));
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inflight: Promise<void> = Promise.resolve();

  function inRange(value: unknown, min: number, max: number): boolean {
    return typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;
  }
  function isValid(value: AppSettings): boolean {
    const { preferences: prefs, vault_settings: vault } = value;
    return inRange(prefs.font_size, 10, 32) && inRange(prefs.ui_font_size, 10, 24)
      && inRange(vault.plugins['recent-files'].limit, 1, 200) && inRange(vault.plugins.excalidraw.embed_width, 100, 2000);
  }

  function persist(): Promise<void> {
    inflight = inflight.then(async () => {
      const sent = $state.snapshot(draft);
      const payload = JSON.stringify(sent);
      if (payload === lastSaved || !isValid(sent)) return;
      status = 'saving'; error = null;
      try {
        const saved = await api.saveSettings(sent.preferences, sent.vault_settings);
        lastSaved = JSON.stringify(copySettings(saved));
        onSaved(saved);
        if (JSON.stringify($state.snapshot(draft)) === payload && lastSaved !== payload) draft = copySettings(saved);
        status = 'saved';
      } catch (cause) { error = cause instanceof Error ? cause.message : 'Could not save settings.'; status = 'idle'; }
    });
    return inflight;
  }
  $effect(() => {
    JSON.stringify($state.snapshot(draft));
    clearTimeout(timer);
    timer = setTimeout(() => void persist(), 400);
    return () => clearTimeout(timer);
  });
  function revertInvalid(): void {
    const saved: AppSettings = JSON.parse(lastSaved);
    const { preferences: prefs, vault_settings: vault } = draft;
    if (!inRange(prefs.font_size, 10, 32)) prefs.font_size = saved.preferences.font_size;
    if (!inRange(prefs.ui_font_size, 10, 24)) prefs.ui_font_size = saved.preferences.ui_font_size;
    if (!inRange(vault.plugins['recent-files'].limit, 1, 200)) vault.plugins['recent-files'].limit = saved.vault_settings.plugins['recent-files'].limit;
    if (!inRange(vault.plugins.excalidraw.embed_width, 100, 2000)) vault.plugins.excalidraw.embed_width = saved.vault_settings.plugins.excalidraw.embed_width;
  }
  async function close(): Promise<void> {
    clearTimeout(timer);
    revertInvalid();
    await persist();
    onClose();
  }
  let manualPath = $state('');
  let vaultError = $state<string | null>(null);
  let vaultBusy = $state(false);

  async function updateVaults(change: () => Promise<VaultsInfo>): Promise<boolean> {
    vaultBusy = true; vaultError = null;
    try { onVaultsChanged(await change()); return true; }
    catch (cause) { vaultError = cause instanceof Error ? cause.message : 'Could not update vaults.'; return false; }
    finally { vaultBusy = false; }
  }
  async function pickVault(): Promise<void> {
    vaultError = null;
    try {
      const picked = await api.pickVaultFolder();
      if ('path' in picked) await updateVaults(() => api.addVault(picked.path));
    } catch (cause) { vaultError = cause instanceof Error ? `${cause.message}. Enter the folder path instead.` : 'Could not open the folder picker.'; }
  }
  async function addManualVault(): Promise<void> {
    if (await updateVaults(() => api.addVault(manualPath.trim()))) manualPath = '';
  }
  async function importSettings(): Promise<void> {
    try {
      draft.vault_settings = copySettings(await api.importObsidianSettings()).vault_settings;
      error = null;
      notice = `Imported settings from ${vaults.active}/.obsidian. They are saved automatically.`;
    } catch (cause) { notice = null; error = cause instanceof Error ? cause.message : 'Could not import Obsidian settings.'; }
  }
</script>

<svelte:window onkeydown={(event) => event.key === 'Escape' && void close()} />

{#snippet stepper(label: string, help: string, value: number, min: number, max: number, set: (value: number) => void)}
  <div class="settings-row"><span class="settings-label">{label}{#if help}<small>{help}</small>{/if}</span>
    <div class="settings-stepper" role="group" aria-label={label}>
      <button type="button" aria-label="Decrease" disabled={value <= min} onclick={() => set(Math.max(min, value - 1))}>−</button>
      <input type="number" {min} {max} {value} aria-label={`${label} (px)`} oninput={(event) => set(event.currentTarget.valueAsNumber)} />
      <span aria-hidden="true">px</span>
      <button type="button" aria-label="Increase" disabled={value >= max} onclick={() => set(Math.min(max, value + 1))}>+</button>
    </div>
  </div>
{/snippet}

{#snippet toggle(label: string, help: string, checked: boolean, set: (value: boolean) => void)}
  <label class="settings-row"><span class="settings-label">{label}{#if help}<small>{help}</small>{/if}</span><input type="checkbox" role="switch" class="settings-switch" {checked} onchange={(event) => set(event.currentTarget.checked)} /></label>
{/snippet}

<div class="settings-overlay" role="presentation" onclick={(event) => event.target === event.currentTarget && void close()}>
  <div class="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
    <header class="settings-head">
      <h2 id="settings-title">Settings</h2>
      <button class="header-btn" onclick={onOpenDocs}>Open docs</button>
      <button class="settings-close" aria-label="Close settings" onclick={() => void close()}>✕</button>
    </header>
    <nav class="settings-nav" aria-label="Settings sections">
      <p class="settings-nav-group">App</p>
      {#each APP_PANES as [id, name] (id)}
        <button class="settings-nav-item" aria-current={pane === id ? 'page' : undefined} onclick={() => pane = id}>{name}</button>
      {/each}
      <p class="settings-nav-group" title={`These settings apply only to the ${vaults.active} vault`}>Vault: {vaults.active}</p>
      {#each VAULT_PANES as [id, name] (id)}
        <button class="settings-nav-item" aria-current={pane === id ? 'page' : undefined} onclick={() => pane = id}>{name}{#if id !== 'files'}<span class="settings-nav-state" class:on={draft.vault_settings.plugins[id].enabled} title={draft.vault_settings.plugins[id].enabled ? 'On' : 'Off'}></span>{/if}</button>
      {/each}
      <button class="header-btn settings-import" title="Replace this vault's Files and plugin settings with the values in its .obsidian folder. The changes are saved automatically." onclick={importSettings}>Import from Obsidian</button>
    </nav>
    <main class="settings-pane" onfocusout={revertInvalid}>
      {#if notice}<p class="settings-notice" role="status">{notice}</p>{/if}
      {#if pane === 'appearance'}
        <h3>Appearance</h3>
        <div class="settings-row"><span class="settings-label">Theme</span>
          <div class="settings-segmented" role="radiogroup" aria-label="Theme">
            {#each [['dark', 'Dark'], ['light', 'Light']] as [value, name] (value)}
              <label class:selected={draft.preferences.theme === value}><input type="radio" name="theme" {value} bind:group={draft.preferences.theme} />{name}</label>
            {/each}
          </div>
        </div>
        <div class="theme-previews" role="radiogroup" aria-label="Aesthetic">
          {#each [['ink', 'Ink'], ['slate', 'Slate'], ['sage', 'Sage']] as [value, name] (value)}
            <label class="theme-option" class:selected={draft.preferences.aesthetic === value}>
              <input type="radio" name="aesthetic" {value} bind:group={draft.preferences.aesthetic} />
              <span class="theme-preview" data-aesthetic={value} data-theme={draft.preferences.theme} aria-hidden="true">
                <span class="tp-side"></span>
                <span class="tp-page"><span class="tp-title">Aa</span><span class="tp-h3"></span><span class="tp-text"></span><span class="tp-text short"><i></i></span></span>
              </span>
              {name}
            </label>
          {/each}
        </div>
        {@render stepper('Editor font size', 'Note text. 10–32 px.', draft.preferences.font_size, 10, 32, (value) => draft.preferences.font_size = value)}
        {@render stepper('Interface font size', 'Sidebars, panels and menus. 10–24 px.', draft.preferences.ui_font_size, 10, 24, (value) => draft.preferences.ui_font_size = value)}
        {@render toggle('Persistent Live Preview', 'Keep Markdown rendered while the cursor is on a line.', draft.preferences.persistent_live_preview, (value) => draft.preferences.persistent_live_preview = value)}
      {:else if pane === 'vaults'}
        <h3>Vaults</h3>
        <p class="settings-hint">Changes here apply immediately. Removing a vault only drops it from this list; its files stay where they are.</p>
        <ul class="settings-vaults">
          {#each vaults.vaults as vault (vault.name)}
            <li class:active={vault.name === vaults.active}>
              <div class="settings-vault-meta"><strong>{vault.name}</strong><span title={vault.path}>{vault.path}</span></div>
              {#if vault.name === vaults.active}<span class="settings-vault-tag">Open</span>{:else}<button class="header-btn" disabled={vaultBusy} onclick={() => onSwitchVault(vault.name)}>Open</button>{/if}
              {#if vault.name === vaults.default}<span class="settings-vault-tag">Default</span>{:else}<button class="header-btn" disabled={vaultBusy} onclick={() => updateVaults(() => api.setDefaultVault(vault.name))}>Make default</button>{/if}
              <button class="header-btn" disabled={vaultBusy || vault.name === vaults.active} title={vault.name === vaults.active ? 'Open another vault before removing this one.' : 'Remove from the list. Files are not touched.'} onclick={() => updateVaults(() => api.removeVault(vault.name))}>Remove</button>
            </li>
          {/each}
        </ul>
        <form class="settings-vault-add" onsubmit={(event) => { event.preventDefault(); void addManualVault(); }}>
          <button type="button" class="header-btn" disabled={vaultBusy} onclick={pickVault}>Choose folder…</button>
          <input aria-label="Vault folder path" placeholder="or /absolute/path/to/folder" bind:value={manualPath} />
          <button class="header-btn" disabled={vaultBusy || !manualPath.trim()}>Add path</button>
        </form>
        {#if vaultError}<p class="settings-error" role="alert">{vaultError}</p>{/if}
      {:else if pane === 'files'}
        <h3>Files</h3>
        <label class="settings-row"><span class="settings-label">Attachment folder<small><code>/</code> vault root · <code>.</code> the note’s folder · <code>./sub</code> a subfolder next to the note · <code>sub</code> a folder at the vault root</small></span><input placeholder="/" bind:value={draft.vault_settings.files.attachment_folder} /></label>
      {:else}
        {@const plugin = draft.vault_settings.plugins[pane]}
        <div class="settings-plugin-head">
          <h3>{VAULT_PANES.find(([id]) => id === pane)?.[1]}</h3>
          <input type="checkbox" role="switch" class="settings-switch" aria-label="Enabled" bind:checked={plugin.enabled} />
        </div>
        <fieldset class="settings-plugin-body" disabled={!plugin.enabled}>
          {#if pane === 'tasks'}
            {@const tasks = draft.vault_settings.plugins.tasks}
            <label class="settings-row"><span class="settings-label">Next status</span><select bind:value={tasks.next_status_symbol}><option value="x">Done</option><option value="/">In progress</option><option value="-">Cancelled</option></select></label>
            {@render toggle('Set done date', 'Append ✅ with today’s date when a task is done.', tasks.set_done_date, (value) => tasks.set_done_date = value)}
            {@render toggle('Set cancelled date', 'Append ❌ with today’s date when a task is cancelled.', tasks.set_cancelled_date, (value) => tasks.set_cancelled_date = value)}
            {@render toggle('Set created date', '', tasks.set_created_date, (value) => tasks.set_created_date = value)}
          {:else if pane === 'periodic-notes'}
            {@const periodic = draft.vault_settings.plugins['periodic-notes']}
            <label class="settings-row"><span class="settings-label">Daily folder<small>Relative to the vault root. Empty means the root.</small></span><input bind:value={periodic.folder} /></label>
            <label class="settings-row"><span class="settings-label">Daily format<small>Today’s note: <code>{dailyNotePath(periodic, new Date())}</code></small></span><input placeholder="YYYY-MM-DD" bind:value={periodic.format} /></label>
            <label class="settings-row"><span class="settings-label">Daily template<small>Starting content for new daily notes. <code>{'{{date}}'}</code>, <code>{'{{time}}'}</code> and <code>{'{{title}}'}</code> are filled in.</small></span><input bind:value={periodic.template} /></label>
          {:else if pane === 'recent-files'}
            <label class="settings-row"><span class="settings-label">Files shown<small>1–200.</small></span><input type="number" min="1" max="200" bind:value={draft.vault_settings.plugins['recent-files'].limit} /></label>
          {:else if pane === 'excalidraw'}
            <label class="settings-row"><span class="settings-label">Embed width<small>Pixels, 100–2000.</small></span><input type="number" min="100" max="2000" bind:value={draft.vault_settings.plugins.excalidraw.embed_width} /></label>
          {:else if pane === 'folder-notes'}
            <p class="settings-hint">Clicking a folder opens <code>Folder/Folder.md</code>. The note is hidden from the folder’s contents; use the arrow to expand or collapse. Renaming or moving the folder renames the note with it.</p>
          {/if}
        </fieldset>
      {/if}
    </main>
    <footer class="settings-foot">
      {#if error}<p class="settings-error" role="alert">{error}</p>{/if}
      {#if !error && status !== 'idle'}<span class="settings-status" role="status">{status === 'saving' ? 'Saving…' : 'Saved'}</span>{/if}
      <button class="header-btn" onclick={() => void close()}>Close</button>
    </footer>
  </div>
</div>
