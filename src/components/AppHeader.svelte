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
      <rect x="0.5" y="0.5" width="31" height="31" rx="7.5" fill="var(--bg-elev)" stroke="var(--border)" stroke-width="1"/>
      <path d="M9.5 6V12.3M9.5 19.7V26M16 6V26M22.5 6V12.3M22.5 19.7V26" fill="none" stroke="var(--text-pri)" stroke-width="2.6" stroke-linecap="round"/>
      <path d="M5.5 16H12.3M19.7 16H26.5" fill="none" stroke="var(--accent)" stroke-width="2.9" stroke-linecap="round"/>
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
