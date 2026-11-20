import { describe, expect, it } from 'vitest';

import { dailyNotePath, formatPeriodicDate, isoDate, monthGrid } from './periodic';

describe('formatPeriodicDate', () => {
  const date = new Date(2026, 9, 9, 7, 5);

  it('formats the supported tokens', () => {
    expect(formatPeriodicDate(date, 'YYYY/MM/YYYY-MM-DD HH:mm dddd')).toBe('2026/10/2026-10-09 07:05 Friday');
  });

  it('keeps bracketed text literal', () => {
    expect(formatPeriodicDate(date, '[Week of] YYYY-MM-DD')).toBe('Week of 2026-10-09');
  });
});

describe('dailyNotePath', () => {
  it('joins folder and formatted name', () => {
    expect(dailyNotePath({ folder: 'diario/', format: 'YYYY/MM/YYYY-MM-DD' }, new Date(2026, 0, 3))).toBe('diario/2026/01/2026-01-03.md');
  });

  it('allows the vault root', () => {
    expect(dailyNotePath({ folder: '', format: 'YYYY-MM-DD' }, new Date(2026, 0, 3))).toBe('2026-01-03.md');
  });
});

describe('monthGrid', () => {
  it('starts on Monday and pads to whole weeks', () => {
    const days = monthGrid(2026, 9);
    expect(days).toHaveLength(35);
    expect(isoDate(days[0])).toBe('2026-09-28');
    expect(isoDate(days.at(-1)!)).toBe('2026-11-01');
  });

  it('does not add a leading week when the month starts on Monday', () => {
    const days = monthGrid(2026, 5);
    expect(isoDate(days[0])).toBe('2026-06-01');
    expect(days).toHaveLength(35);
  });
});
