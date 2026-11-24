/** Lightweight bilingual (EN/ES) natural-language date parser for task metadata. */

const WEEKDAYS: Record<string, number> = {
  sunday: 0, sun: 0, domingo: 0, dom: 0,
  monday: 1, mon: 1, lunes: 1, lun: 1,
  tuesday: 2, tue: 2, tues: 2, martes: 2, mar: 2,
  wednesday: 3, wed: 3, miercoles: 3, mie: 3,
  thursday: 4, thu: 4, thur: 4, thurs: 4, jueves: 4, jue: 4,
  friday: 5, fri: 5, viernes: 5, vie: 5,
  saturday: 6, sat: 6, sabado: 6, sab: 6,
};

const MONTHS: Record<string, number> = {
  january: 0, jan: 0, enero: 0, ene: 0,
  february: 1, feb: 1, febrero: 1,
  march: 2, mar: 2, marzo: 2,
  april: 3, apr: 3, abril: 3, abr: 3,
  may: 4, mayo: 4,
  june: 5, jun: 5, junio: 5,
  july: 6, jul: 6, julio: 6,
  august: 7, aug: 7, agosto: 7, ago: 7,
  september: 8, sep: 8, sept: 8, septiembre: 8,
  october: 9, oct: 9, octubre: 9,
  november: 10, nov: 10, noviembre: 10,
  december: 11, dec: 11, diciembre: 11, dic: 11,
};

export const WEEKDAY_NAMES_EN = [
  'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday',
] as const;

export const WEEKDAY_HINTS: readonly { terms: readonly string[]; day: number; label: string }[] = [
  { terms: ['monday', 'lunes'], day: 1, label: 'Monday' },
  { terms: ['tuesday', 'martes'], day: 2, label: 'Tuesday' },
  { terms: ['wednesday', 'miercoles'], day: 3, label: 'Wednesday' },
  { terms: ['thursday', 'jueves'], day: 4, label: 'Thursday' },
  { terms: ['friday', 'viernes'], day: 5, label: 'Friday' },
  { terms: ['saturday', 'sabado'], day: 6, label: 'Saturday' },
  { terms: ['sunday', 'domingo'], day: 0, label: 'Sunday' },
];

/** Lowercase, strip diacritics, and collapse whitespace. */
export function normalizeDateQuery(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/** Add `days` calendar days in local time. */
export function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

/** Add `months` calendar months, clamping the day to the target month's length. */
export function addMonths(date: Date, months: number): Date {
  const year = date.getFullYear();
  const month = date.getMonth() + months;
  const maxDay = new Date(year, month + 1, 0).getDate();
  return new Date(year, month, Math.min(date.getDate(), maxDay));
}

function validCalendarDate(year: number, monthIndex: number, day: number): Date | null {
  if (monthIndex < 0 || monthIndex > 11 || day < 1 || day > 31) return null;
  const candidate = new Date(year, monthIndex, day);
  if (
    candidate.getFullYear() !== year
    || candidate.getMonth() !== monthIndex
    || candidate.getDate() !== day
  ) {
    return null;
  }
  return candidate;
}

function rollForwardDate(ref: Date, monthIndex: number, day: number, explicitYear?: number): Date | null {
  const year = explicitYear ?? ref.getFullYear();
  const candidate = validCalendarDate(year, monthIndex, day);
  if (!candidate) return null;
  if (explicitYear === undefined && candidate < ref) {
    return validCalendarDate(year + 1, monthIndex, day);
  }
  return candidate;
}

/** Format a local Date as `YYYY-MM-DD`. */
export function formatIsoDate(date: Date): string {
  const y = String(date.getFullYear()).padStart(4, '0');
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** Format a short readable weekday + date hint, e.g. `Tue, Nov 24`. */
export function formatShortDate(date: Date): string {
  const weekday = WEEKDAY_NAMES_EN[date.getDay()].slice(0, 3);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${weekday}, ${months[date.getMonth()]} ${date.getDate()}`;
}

/** Parse a natural-language EN/ES date phrase relative to `reference` (defaults to today). */
export function parseNaturalDate(input: string, reference: Date = new Date()): Date | null {
  const q = normalizeDateQuery(input);
  if (!q) return null;
  const today = startOfDay(reference);

  if (q === 'today' || q === 'hoy' || q === 'tod') return today;
  if (q === 'tomorrow' || q === 'manana' || q === 'tmr' || q === 'tom' || q === 'tmrw') return addDays(today, 1);
  if (q === 'yesterday' || q === 'ayer') return addDays(today, -1);
  if (q === 'day after tomorrow' || q === 'pasado manana') return addDays(today, 2);
  if (q === 'day before yesterday' || q === 'anteayer') return addDays(today, -2);
  if (q === 'next week' || q === 'proxima semana' || q === 'la proxima semana' || q === 'semana que viene') return addDays(today, 7);
  if (q === 'next month' || q === 'proximo mes' || q === 'el proximo mes' || q === 'mes que viene') return addMonths(today, 1);
  if (q === 'next year' || q === 'proximo ano' || q === 'el proximo ano') return addMonths(today, 12);
  if (q === 'weekend' || q === 'this weekend' || q === 'fin de semana' || q === 'este fin de semana') {
    const delta = (6 - today.getDay() + 7) % 7 || 7;
    return addDays(today, delta);
  }
  if (q === 'end of month' || q === 'fin de mes') {
    return new Date(today.getFullYear(), today.getMonth() + 1, 0);
  }

  // ISO date: YYYY-MM-DD or YYYY/MM/DD
  const iso = /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/.exec(q);
  if (iso) return validCalendarDate(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));

  // Shorthand offset: +3d, +2w, +1m, +1y
  const shortOffset = /^\+(\d+)\s*([dwmsya])$/.exec(q);
  if (shortOffset) {
    const amount = Number(shortOffset[1]);
    const unit = shortOffset[2];
    if (unit === 'd') return addDays(today, amount);
    if (unit === 'w' || unit === 's') return addDays(today, amount * 7);
    if (unit === 'm') return addMonths(today, amount);
    return addMonths(today, amount * 12);
  }

  // Natural offset: "in 3 days", "en 2 semanas", "in a week", "en un mes"
  const natOffset = /^(?:in|en)\s+(a|an|un|una|\d+)\s+(day|days|dia|dias|week|weeks|semana|semanas|month|months|mes|meses|year|years|ano|anos)$/.exec(q);
  if (natOffset) {
    const amount = /^\d+$/.test(natOffset[1]) ? Number(natOffset[1]) : 1;
    const unit = natOffset[2];
    if (unit.startsWith('day') || unit.startsWith('dia')) return addDays(today, amount);
    if (unit.startsWith('week') || unit.startsWith('semana')) return addDays(today, amount * 7);
    if (unit.startsWith('month') || unit.startsWith('mes')) return addMonths(today, amount);
    return addMonths(today, amount * 12);
  }

  // Weekday with optional modifier: "martes", "next sunday", "proximo lunes", "este viernes", "last friday"
  const weekdayMatch = /^(?:(this|next|last|este|esta|el|proximo|proxima|pasado|pasada)\s+)?([a-z]+)$/.exec(q);
  if (weekdayMatch && weekdayMatch[2] in WEEKDAYS) {
    const modifier = weekdayMatch[1] ?? '';
    const target = WEEKDAYS[weekdayMatch[2]];
    const dow = today.getDay();
    if (modifier === 'last' || modifier === 'pasado' || modifier === 'pasada') {
      return addDays(today, -((dow - target + 7) % 7 || 7));
    }
    const delta = (target - dow + 7) % 7;
    if (delta === 0) {
      return modifier === 'this' || modifier === 'este' || modifier === 'esta' ? today : addDays(today, 7);
    }
    return addDays(today, delta);
  }

  // Month + day ("dec 15", "december 15 2027") or day + month ("15 dic", "15 de diciembre", "15 dec 2027")
  const dmy = /^(\d{1,2})\s+(?:de\s+)?([a-z]+)(?:\s+(?:de\s+)?(\d{4}))?$/.exec(q);
  if (dmy && dmy[2] in MONTHS) {
    return rollForwardDate(today, MONTHS[dmy[2]], Number(dmy[1]), dmy[3] ? Number(dmy[3]) : undefined);
  }
  const mdy = /^([a-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?$/.exec(q);
  if (mdy && mdy[1] in MONTHS) {
    return rollForwardDate(today, MONTHS[mdy[1]], Number(mdy[2]), mdy[3] ? Number(mdy[3]) : undefined);
  }

  // DD/MM (Spanish/LatAm convention)
  const slash = /^(\d{1,2})\/(\d{1,2})$/.exec(q);
  if (slash) return rollForwardDate(today, Number(slash[2]) - 1, Number(slash[1]));

  return null;
}
