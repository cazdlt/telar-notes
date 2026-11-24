import { describe, expect, it } from 'vitest';
import { formatIsoDate, parseNaturalDate } from './natural-date';

// Fixed reference: Monday, 2026-11-23
const REF = new Date(2026, 10, 23);
const parse = (input: string) => {
  const result = parseNaturalDate(input, REF);
  return result ? formatIsoDate(result) : null;
};

describe('parseNaturalDate', () => {
  it('resolves English and Spanish relative days', () => {
    expect(parse('today')).toBe('2026-11-23');
    expect(parse('hoy')).toBe('2026-11-23');
    expect(parse('tomorrow')).toBe('2026-11-24');
    expect(parse('mañana')).toBe('2026-11-24');
    expect(parse('manana')).toBe('2026-11-24');
    expect(parse('pasado mañana')).toBe('2026-11-25');
    expect(parse('yesterday')).toBe('2026-11-22');
    expect(parse('ayer')).toBe('2026-11-22');
  });

  it('resolves weekdays in English and Spanish with accents and modifiers', () => {
    expect(parse('martes')).toBe('2026-11-24');
    expect(parse('tuesday')).toBe('2026-11-24');
    expect(parse('sunday')).toBe('2026-11-29');
    expect(parse('domingo')).toBe('2026-11-29');
    expect(parse('miércoles')).toBe('2026-11-25');
    expect(parse('miercoles')).toBe('2026-11-25');
    expect(parse('sábado')).toBe('2026-11-28');
    // Same weekday: bare and next roll forward a week; this stays today.
    expect(parse('monday')).toBe('2026-11-30');
    expect(parse('próximo lunes')).toBe('2026-11-30');
    expect(parse('this monday')).toBe('2026-11-23');
    expect(parse('este lunes')).toBe('2026-11-23');
    expect(parse('last friday')).toBe('2026-11-20');
  });

  it('resolves shorthand and natural offsets', () => {
    expect(parse('+3d')).toBe('2026-11-26');
    expect(parse('+2w')).toBe('2026-12-07');
    expect(parse('+1m')).toBe('2026-12-23');
    expect(parse('in 3 days')).toBe('2026-11-26');
    expect(parse('en 2 semanas')).toBe('2026-12-07');
    expect(parse('en un mes')).toBe('2026-12-23');
    expect(parse('next week')).toBe('2026-11-30');
    expect(parse('próxima semana')).toBe('2026-11-30');
    expect(parse('fin de mes')).toBe('2026-11-30');
    expect(parse('weekend')).toBe('2026-11-28');
  });

  it('resolves explicit dates and rolls past month/day forward', () => {
    expect(parse('2026-12-15')).toBe('2026-12-15');
    expect(parse('15 dic')).toBe('2026-12-15');
    expect(parse('15 de diciembre')).toBe('2026-12-15');
    expect(parse('dec 15')).toBe('2026-12-15');
    expect(parse('15/12')).toBe('2026-12-15');
    expect(parse('10 ene')).toBe('2027-01-10');
    expect(parse('jan 10')).toBe('2027-01-10');
    expect(parse('2026-02-30')).toBeNull();
    expect(parse('nonsense')).toBeNull();
  });
});
