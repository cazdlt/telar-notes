import type { PeriodicNotesSettings } from './types';

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const pad = (value: number) => String(value).padStart(2, '0');

/** Formats a date with the Moment subset the server's `_format_periodic_date` supports. */
export function formatPeriodicDate(date: Date, format: string): string {
  const values: Record<string, string> = {
    YYYY: String(date.getFullYear()).padStart(4, '0'),
    MM: pad(date.getMonth() + 1),
    DD: pad(date.getDate()),
    HH: pad(date.getHours()),
    mm: pad(date.getMinutes()),
    dddd: WEEKDAYS[date.getDay()],
  };
  return format.replace(/\[([^\]]*)\]|YYYY|MM|DD|HH|mm|dddd/g, (token, literal?: string) => literal ?? values[token]);
}

export function isoDate(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Vault-relative path of the daily note for `date`, as the server would create it. */
export function dailyNotePath(settings: Pick<PeriodicNotesSettings, 'folder' | 'format'>, date: Date): string {
  const folder = settings.folder.replace(/^\/+|\/+$/g, '');
  const name = `${formatPeriodicDate(date, settings.format)}.md`;
  return folder ? `${folder}/${name}` : name;
}

/**
 * Days shown for a month view, Monday-first, padded with neighbouring-month days
 * to whole weeks.
 */
export function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - ((first.getDay() + 6) % 7));
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = Math.ceil(((first.getDay() + 6) % 7 + daysInMonth) / 7) * 7;
  return Array.from({ length: cells }, (_, index) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + index));
}
