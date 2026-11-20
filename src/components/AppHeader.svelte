<script lang="ts">
  let {
    activeVault,
    saveStatus,
    theme,
    reading,
    canGoBack,
    canGoForward,
    onBack,
    onForward,
    onOpenSettings,
    onToggleTheme,
    onToggleReading,
  }: {
    activeVault: string | null;
    saveStatus: 'saved' | 'saving' | 'error';
    theme: 'light' | 'dark';
    reading: boolean;
    canGoBack: boolean;
    canGoForward: boolean;
    onBack: () => void;
    onForward: () => void;
    onOpenSettings: () => void;
    onToggleTheme: () => void;
    onToggleReading: () => void;
  } = $props();
</script>

<header id="header">
  <div id="nav-history">
    <button class="header-btn nav-btn" type="button" disabled={!canGoBack} onclick={onBack} title="Back (⌘[)" aria-label="Back">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 6l-6 6 6 6"/></svg>
    </button>
    <button class="header-btn nav-btn" type="button" disabled={!canGoForward} onclick={onForward} title="Forward (⌘])" aria-label="Forward">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 6l6 6-6 6"/></svg>
    </button>
  </div>
  <button id="vault-switcher" type="button" title="Manage vaults" onclick={onOpenSettings}>
    <svg class="app-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#1e1e1e"/>
      <g transform="translate(0 1)">
        <path d="M9 6.5H23v5.6h-1.3q-.6-2.6-3.2-2.6h-3v3.7h2.4q1.4 0 1.6-1.5h1.3v5.6h-1.3q-.2-1.5-1.6-1.5h-2.4v4.1q0 .8 1 1l1.5.2v1.1H9v-1.1l1.3-.2q1-.2 1-1V9.1q0-.8-1-1L9 7.9z" fill="#dadada"/>
        <rect x="9" y="24" width="14" height="2.4" rx="1.2" fill="#8a5cf5"/>
      </g>
    </svg>{activeVault ?? 'No vault'}
  </button>
  <div id="header-spacer"></div>
  <span id="save-status" class:error={saveStatus === 'error'}>● {saveStatus === 'saving' ? 'Saving…' : saveStatus === 'error' ? 'Save error' : 'Saved'}</span>
  <button id="theme-toggle" class="header-btn" type="button" onclick={onToggleTheme} title={theme === 'dark' ? 'Light theme' : 'Dark theme'} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>
    {#if theme === 'dark'}
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/></svg>
    {:else}
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>
    {/if}
  </button>
  <button id="reading-toggle" class="header-btn" class:active={reading} onclick={onToggleReading}>Read</button>
  <button class="header-btn" onclick={onOpenSettings} title="Settings" aria-label="Settings">Settings</button>
</header>
