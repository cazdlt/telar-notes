<script lang="ts">
  export interface ModalState {
    title: string;
    label: string;
    value: string;
    action: (value: string) => Promise<void>;
    danger?: boolean;
    input?: boolean;
  }

  let {
    modal = $bindable<ModalState | null>(),
    onConfirm,
    onClose,
  }: {
    modal: ModalState | null;
    onConfirm: () => void;
    onClose: () => void;
  } = $props();
</script>

{#if modal}
  <div id="fm-overlay" class="open" role="presentation" onclick={(event) => event.target === event.currentTarget && onClose()}>
    <form id="fm-modal" onsubmit={(event) => { event.preventDefault(); onConfirm(); }}>
      <div id="fm-title">{modal.title}</div>
      {#if modal.input}
        <input id="fm-input" bind:value={modal.value} autocomplete="off" />
      {/if}
      <div class="fm-actions">
        <button type="button" id="fm-cancel" class="header-btn" onclick={onClose}>Cancel</button>
        <button id="fm-confirm" class:danger={modal.danger} class="header-btn">{modal.label}</button>
      </div>
    </form>
  </div>
{/if}
