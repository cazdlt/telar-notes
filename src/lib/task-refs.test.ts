import { describe, expect, it } from 'vitest';
import { blockRefId, noteLinkName, taskLabel, taskRefBadge } from './task-refs';

const done = (date?: string) => ({ status: { symbol: 'x', name: 'Done', type: 'DONE' as const }, dates: (date ? { done: date } : {}) as Record<string, string> });
const open = { status: { symbol: ' ', name: 'Todo', type: 'TODO' as const }, dates: {} };

describe('blockRefId', () => {
  it('accepts only block fragments', () => {
    expect(blockRefId('#^ship-v3')).toBe('ship-v3');
    expect(blockRefId('#Heading')).toBeNull();
    expect(blockRefId('|alias')).toBeNull();
    expect(blockRefId('')).toBeNull();
  });
});

describe('taskLabel', () => {
  it('keeps wikilink labels and drops inline markup', () => {
    expect(taskLabel('**Revisar** v3 de [[Alice Smith|Alice]] y [[Backend]] `code`')).toBe('Revisar v3 de Alice y Backend code');
  });
});

describe('noteLinkName', () => {
  it('uses the basename unless another note shares it', () => {
    const files = new Set(['a/Backend.md', 'b/Roadmap.md', 'c/Roadmap.md']);
    expect(noteLinkName('a/Backend.md', files)).toBe('Backend');
    expect(noteLinkName('b/Roadmap.md', files)).toBe('b/Roadmap');
  });
});

describe('taskRefBadge', () => {
  const daily = 'diario/2026/10/2026-10-09.md';
  it('shows a closing date that differs from the daily note date', () => {
    expect(taskRefBadge(done('2026-10-11'), daily)).toBe('done 10-11');
    expect(taskRefBadge({ status: { symbol: '-', name: 'Cancelled', type: 'CANCELLED' }, dates: { cancelled: '2026-10-08' } }, daily)).toBe('cancelled 10-08');
  });
  it('stays quiet for same-day, open, undated, or non-daily cases', () => {
    expect(taskRefBadge(done('2026-10-09'), daily)).toBeNull();
    expect(taskRefBadge(open, daily)).toBeNull();
    expect(taskRefBadge(done(), daily)).toBeNull();
    expect(taskRefBadge(done('2026-10-11'), 'work/Backend.md')).toBeNull();
  });
});
