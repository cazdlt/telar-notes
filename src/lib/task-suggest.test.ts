import { CompletionContext } from '@codemirror/autocomplete';
import { markdown } from '@codemirror/lang-markdown';
import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { ObsidianGFM } from './tasks';
import { taskAutoSuggest } from './task-suggest';

// Fixed reference: Monday, 2026-11-23
const REF = new Date(2026, 10, 23);

async function query(doc: string, pos = doc.length, loadTasksWithId?: () => Promise<{ id: string; description: string }[]>) {
  const state = EditorState.create({ doc, extensions: [markdown({ extensions: ObsidianGFM })] });
  const source = taskAutoSuggest({
    now: () => REF,
    generateId: () => 'abc123',
    loadTasksWithId,
  });
  const ctx = new CompletionContext(state, pos, false);
  return source(ctx);
}

describe('taskAutoSuggest', () => {
  it('resolves Spanish and English date keywords with natural dates', async () => {
    const dueTue = await query('- [ ] Enviar reporte due martes');
    expect(dueTue?.from).toBe('- [ ] Enviar reporte '.length);
    expect(dueTue?.options[0].label).toBe('📅 2026-11-24');
    expect(dueTue?.options[0].apply).toBe('📅 2026-11-24 ');

    const startSun = await query('- [ ] Preparar charla start sunday');
    expect(startSun?.from).toBe('- [ ] Preparar charla '.length);
    expect(startSun?.options[0].label).toBe('🛫 2026-11-29');

    const schedNext = await query('- [/] Revisar PR scheduled +2w');
    expect(schedNext?.options[0].label).toBe('⏳ 2026-12-07');
  });

  it('suggests prefix completions while typing a date word', async () => {
    const partial = await query('- [ ] Comprar café due mañ');
    expect(partial?.options.some((o) => o.label === '📅 2026-11-24')).toBe(true);

    const emptyArg = await query('- [ ] Comprar café due ');
    expect(emptyArg?.options.map((o) => o.label)).toContain('📅 2026-11-23');
    expect(emptyArg?.options.map((o) => o.label)).toContain('📅 2026-11-24');
  });

  it('skips properties already present on the task line', async () => {
    expect(await query('- [ ] Ya tiene 📅 2026-11-24 due martes')).toBeNull();
    expect(await query('- [ ] Ya tiene prioridad ⏫ high')).toBeNull();
    expect(await query('- [ ] Ya recurre 🔁 every day every week')).toBeNull();
    expect(await query('- [ ] Ya tiene 🆔 xyz123 id')).toBeNull();
  });

  it('does not trigger on non-task lines or inside fenced code blocks', async () => {
    expect(await query('Normal text due martes')).toBeNull();
    expect(await query('- Regular list item due martes')).toBeNull();
    expect(await query('```\n- [ ] Code task due martes\n```', 28)).toBeNull();
  });

  it('suggests priorities, recurrence, on-completion, ID, and dependencies', async () => {
    const prio = await query('- [ ] Arreglar bug high');
    expect(prio?.options.some((o) => o.label.startsWith('⏫'))).toBe(true);

    const rec = await query('- [ ] Pagar arriendo cada martes');
    expect(rec?.options[0].label).toBe('🔁 every week on Tuesday');

    const comp = await query('- [ ] Temporal on completion del');
    expect(comp?.options.map((o) => o.label)).toEqual(['🏁 delete']);

    const id = await query('- [ ] Bloqueante id');
    expect(id?.options[0].label).toBe('🆔 abc123');

    const doc = '- [ ] Primera tarea 🆔 t1\n- [ ] Segunda tarea depends on t';
    const dep = await query(doc);
    expect(dep?.options[0].label).toBe('⛔ t1');
    expect(dep?.options[0].detail).toBe('Primera tarea');
  });
});
