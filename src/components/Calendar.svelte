<script lang="ts">
  import { dailyNotePath, isoDate, monthGrid } from '../lib/periodic';
  import type { PeriodicNotesSettings } from '../lib/types';

  let {
    settings,
    files,
    currentFile,
    onOpenDate,
  }: {
    settings: PeriodicNotesSettings;
    files: Set<string>;
    currentFile: string | null;
    onOpenDate: (date: Date) => void;
  } = $props();

  const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
  const today = new Date();
  let view = $state({ year: today.getFullYear(), month: today.getMonth() });

  const label = $derived(new Date(view.year, view.month, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' }));
  const days = $derived(monthGrid(view.year, view.month).map((date) => {
    const path = dailyNotePath(settings, date);
    return { date, iso: isoDate(date), path, exists: files.has(path), outside: date.getMonth() !== view.month };
  }));
  const todayIso = isoDate(today);

  function shift(delta: number) {
    const next = new Date(view.year, view.month + delta, 1);
    view = { year: next.getFullYear(), month: next.getMonth() };
  }
  function goToday() { view = { year: today.getFullYear(), month: today.getMonth() }; }
</script>

<div class="calendar" aria-label="Daily notes calendar">
  <div class="calendar-head">
    <span class="calendar-month">{label}</span>
    <button type="button" onclick={() => shift(-1)} title="Previous month" aria-label="Previous month">‹</button>
    <button type="button" class="calendar-today" onclick={goToday} title="Current month">Today</button>
    <button type="button" onclick={() => shift(1)} title="Next month" aria-label="Next month">›</button>
  </div>
  <div class="calendar-grid" role="grid">
    {#each WEEKDAYS as weekday}<span class="calendar-weekday">{weekday}</span>{/each}
    {#each days as day (day.iso)}
      <button
        type="button"
        class="calendar-day"
        class:outside={day.outside}
        class:today={day.iso === todayIso}
        class:active={day.path === currentFile}
        title={day.exists ? day.path : `Create ${day.path}`}
        onclick={() => onOpenDate(day.date)}
      >{day.date.getDate()}{#if day.exists}<span class="calendar-dot" aria-label="has note"></span>{/if}</button>
    {/each}
  </div>
</div>

<style>
  .calendar { flex: 0 0 auto; padding: 4px 10px 10px; font-size: calc(12px * var(--ui-scale, 1)); }
  .calendar-head { display: flex; align-items: center; gap: 2px; margin-bottom: 6px; }
  .calendar-month { flex: 1; color: var(--text-pri); font-weight: 600; }
  .calendar-head button { border: 0; border-radius: 4px; background: none; color: var(--text-sec); padding: 2px 6px; cursor: pointer; font: inherit; }
  .calendar-head button:hover { background: var(--accent-bg); color: var(--accent); }
  .calendar-today { font-size: calc(11px * var(--ui-scale, 1)); }
  .calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 1px; }
  .calendar-weekday { padding: 2px 0; color: var(--text-dim); font-size: calc(10.5px * var(--ui-scale, 1)); text-align: center; }
  .calendar-day { position: relative; height: 24px; border: 0; border-radius: 4px; background: none; color: var(--text-sec); cursor: pointer; font: inherit; font-variant-numeric: tabular-nums; }
  .calendar-day:hover { background: var(--accent-bg); }
  .calendar-day.outside { color: var(--text-dim); opacity: 0.6; }
  .calendar-day.today { color: var(--accent); font-weight: 700; }
  .calendar-day.active { background: var(--accent); color: var(--bg-base); }
  .calendar-dot { position: absolute; bottom: 2px; left: 50%; width: 4px; height: 4px; margin-left: -2px; border-radius: 50%; background: currentColor; opacity: 0.7; }
</style>
