import type { Completion, CompletionContext, CompletionResult, CompletionSource } from '@codemirror/autocomplete';
import { syntaxTree } from '@codemirror/language';
import { startsWithTaskMarker } from './tasks';
import {
  addDays,
  addMonths,
  formatIsoDate,
  formatShortDate,
  normalizeDateQuery,
  parseNaturalDate,
  WEEKDAY_HINTS,
} from './natural-date';

export type TaskIdCandidate = { id: string; description: string };

export type TaskSuggestOptions = {
  /** Whether Tasks auto-suggest is enabled for the active vault (defaults to true). */
  enabled?: () => boolean;
  /** Override current date (useful for deterministic tests). */
  now?: () => Date;
  /** Optional async loader for tasks with `🆔` across the vault (used by `depends on`). */
  loadTasksWithId?: () => Promise<TaskIdCandidate[]>;
  /** Optional ID generator override (useful for deterministic tests). */
  generateId?: () => string;
};

type DateKind = {
  key: string;
  emoji: string;
  triggers: readonly string[];
};

const DATE_KINDS: readonly DateKind[] = [
  { key: 'due', emoji: '📅', triggers: ['due', 'vence'] },
  { key: 'scheduled', emoji: '⏳', triggers: ['scheduled', 'programada'] },
  { key: 'start', emoji: '🛫', triggers: ['start', 'inicio'] },
  { key: 'created', emoji: '➕', triggers: ['created', 'creada'] },
  { key: 'done', emoji: '✅', triggers: ['done', 'hecha'] },
  { key: 'cancelled', emoji: '❌', triggers: ['cancelled', 'canceled', 'cancelada'] },
];

const DATE_TRIGGER_MAP = new Map<string, DateKind>();
for (const kind of DATE_KINDS) {
  for (const trigger of kind.triggers) DATE_TRIGGER_MAP.set(trigger, kind);
}

const PRIORITIES: readonly { emoji: string; label: string; triggers: readonly string[] }[] = [
  { emoji: '🔺', label: 'Highest priority', triggers: ['highest', 'priority', 'prioridad'] },
  { emoji: '⏫', label: 'High priority', triggers: ['high', 'priority', 'prioridad', 'alta'] },
  { emoji: '🔼', label: 'Medium priority', triggers: ['medium', 'med', 'priority', 'prioridad', 'media'] },
  { emoji: '🔽', label: 'Low priority', triggers: ['low', 'priority', 'prioridad', 'baja'] },
  { emoji: '⏬', label: 'Lowest priority', triggers: ['lowest', 'priority', 'prioridad'] },
];

const RECURRENCE_PRESETS: readonly { rule: string; hints: readonly string[] }[] = [
  { rule: 'every day', hints: ['day', 'daily', 'dia'] },
  { rule: 'every weekday', hints: ['weekday', 'weekdays', 'laborable'] },
  { rule: 'every week', hints: ['week', 'weekly', 'semana'] },
  { rule: 'every 2 weeks', hints: ['2 weeks', '2 semanas', 'biweekly'] },
  { rule: 'every month', hints: ['month', 'monthly', 'mes'] },
  { rule: 'every year', hints: ['year', 'yearly', 'ano'] },
];

const QUICK_DATE_HINTS: readonly { query: string; label: string; terms: readonly string[] }[] = [
  { query: 'today', label: 'today', terms: ['today', 'hoy'] },
  { query: 'tomorrow', label: 'tomorrow', terms: ['tomorrow', 'manana'] },
  { query: 'next week', label: 'next week', terms: ['next week', 'proxima semana'] },
  { query: 'weekend', label: 'weekend', terms: ['weekend', 'fin de semana'] },
  { query: 'next month', label: 'next month', terms: ['next month', 'proximo mes'] },
];

const TASK_LINE_PREFIX = /^\s*[-*+]\s+(\[.\])\s/;
const TASK_ID_IN_LINE = /🆔\s*([A-Za-z0-9_-]+)/u;
const DATE_ARG_RE = /(?:^|\s)(due|vence|scheduled|programada|start|inicio|created|creada|done|hecha|cancelled|canceled|cancelada)\s+([^\n📅⏳🛫➕✅❌🔺⏫🔼🔽⏬🔁🏁🆔⛔#]*)$/iu;
const RECURRENCE_ARG_RE = /(?:^|\s)(every|cada)\s+([^\n📅⏳🛫➕✅❌🔺⏫🔼🔽⏬🔁🏁🆔⛔#]*)$/iu;
const ON_COMPLETION_ARG_RE = /(?:^|\s)(on\s+completion|al\s+completar)(?:\s+(\S*))?$/iu;
const DEPENDS_ARG_RE = /(?:^|\s)(depends\s+on|depende\s+de)(?:\s+(\S*))?$/iu;
const TRAILING_WORD_RE = /(?:^|\s)([A-Za-zÀ-ÖØ-öø-ÿ]{2,})$/u;

function defaultGenerateId(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let out = '';
  for (let i = 0; i < 6; i += 1) {
    out += chars[Math.floor(Math.random() * chars.length)];
  }
  return out;
}

function insideCode(context: CompletionContext): boolean {
  let node: { name: string; parent: typeof node } | null = syntaxTree(context.state).resolveInner(context.pos, -1);
  while (node) {
    if (node.name === 'FencedCode' || node.name === 'CodeBlock' || node.name === 'InlineCode' || node.name === 'CodeText') {
      return true;
    }
    node = node.parent;
  }
  return false;
}

function extractDocTasksWithId(docText: string): TaskIdCandidate[] {
  const results: TaskIdCandidate[] = [];
  for (const line of docText.split('\n')) {
    const prefix = TASK_LINE_PREFIX.exec(line);
    if (!prefix || !startsWithTaskMarker(prefix[1])) continue;
    const idMatch = TASK_ID_IN_LINE.exec(line);
    if (!idMatch) continue;
    const description = line
      .slice(prefix[0].length)
      .replace(/(?:📅|⏳|🛫|✅|➕|❌)\s*\d{4}-\d{2}-\d{2}/gu, '')
      .replace(/[🔺⏫🔼🔽⏬]/gu, '')
      .replace(/🆔\s*\S+/gu, '')
      .replace(/⛔\s*\S+/gu, '')
      .replace(/🔁\s*[^📅⏳🛫✅➕❌🔺⏫🔼🔽⏬🆔⛔🏁]+/gu, '')
      .replace(/🏁\s*\S+/gu, '')
      .replace(/\s+\^[A-Za-z0-9-]+$/, '')
      .replace(/\s{2,}/g, ' ')
      .trim();
    results.push({ id: idMatch[1], description: description || idMatch[1] });
  }
  return results;
}

function buildDateSuggestions(kind: DateKind, arg: string, now: Date): Completion[] {
  const trimmed = arg.trim();
  const seen = new Set<string>();
  const options: Completion[] = [];

  const pushDate = (date: Date, hint: string, boost = 0) => {
    const iso = formatIsoDate(date);
    if (seen.has(iso)) return;
    seen.add(iso);
    options.push({
      label: `${kind.emoji} ${iso}`,
      detail: `${kind.key} · ${hint} (${formatShortDate(date)})`,
      apply: `${kind.emoji} ${iso} `,
      boost,
    });
  };

  if (!trimmed) {
    pushDate(now, 'today', 5);
    pushDate(addDays(now, 1), 'tomorrow', 4);
    pushDate(addDays(now, 7), 'next week', 3);
    const satDelta = (6 - now.getDay() + 7) % 7 || 7;
    pushDate(addDays(now, satDelta), 'weekend', 2);
    pushDate(addMonths(now, 1), 'next month', 1);
    return options;
  }

  const parsed = parseNaturalDate(trimmed, now);
  if (parsed) {
    pushDate(parsed, trimmed, 10);
  }

  const norm = normalizeDateQuery(trimmed);
  for (const hint of QUICK_DATE_HINTS) {
    if (hint.terms.some((term) => term.startsWith(norm))) {
      const date = parseNaturalDate(hint.query, now);
      if (date) pushDate(date, hint.label, 5);
    }
  }
  for (const wd of WEEKDAY_HINTS) {
    if (wd.terms.some((term) => term.startsWith(norm))) {
      const date = parseNaturalDate(wd.label, now);
      if (date) pushDate(date, wd.label, 4);
    }
  }

  return options;
}

function buildRecurrenceSuggestions(arg: string): Completion[] {
  const norm = normalizeDateQuery(arg);
  const options: Completion[] = [];
  const seen = new Set<string>();

  const add = (rule: string, detail: string, boost = 0) => {
    if (seen.has(rule)) return;
    seen.add(rule);
    options.push({
      label: `🔁 ${rule}`,
      detail,
      apply: `🔁 ${rule} `,
      boost,
    });
  };

  if (norm) {
    for (const wd of WEEKDAY_HINTS) {
      if (wd.terms.some((term) => term.startsWith(norm) || norm === `week on ${term}` || norm.endsWith(` ${term}`))) {
        add(`every week on ${wd.label}`, 'recurrence', 8);
      }
    }
    for (const preset of RECURRENCE_PRESETS) {
      if (preset.rule.includes(norm) || preset.hints.some((h) => h.startsWith(norm))) {
        add(preset.rule, 'recurrence', 6);
      }
    }
    if (!seen.has(`every ${norm}`)) {
      add(`every ${arg.trim()}`, 'custom recurrence', 2);
    }
    return options;
  }

  for (const preset of RECURRENCE_PRESETS) {
    add(preset.rule, 'recurrence', 5);
  }
  return options;
}

/**
 * CodeMirror completion source implementing Obsidian Tasks Auto-Suggest on task lines:
 * natural-language EN/ES dates, priorities, recurrence, on-completion, and ID/dependencies.
 */
export function taskAutoSuggest(options: TaskSuggestOptions = {}): CompletionSource {
  const isEnabled = options.enabled ?? (() => true);
  const getNow = options.now ?? (() => new Date());
  const genId = options.generateId ?? defaultGenerateId;

  return async (context: CompletionContext): Promise<CompletionResult | null> => {
    if (!isEnabled()) return null;
    const line = context.state.doc.lineAt(context.pos);
    const prefix = TASK_LINE_PREFIX.exec(line.text);
    if (!prefix || !startsWithTaskMarker(prefix[1])) return null;
    if (context.pos < line.from + prefix[0].length) return null;
    if (insideCode(context)) return null;

    const before = line.text.slice(0, context.pos - line.from);
    const fullLine = line.text;
    const now = getNow();

    const hasPriority = /[🔺⏫🔼🔽⏬]/u.test(fullLine);
    const hasRecurrence = /🔁/u.test(fullLine);
    const hasOnCompletion = /🏁/u.test(fullLine);
    const hasId = /🆔/u.test(fullLine);
    const hasDependsOn = /⛔/u.test(fullLine);

    // 1. Date keyword + argument (e.g. `due martes`, `start sunday`, `due `)
    const dateMatch = DATE_ARG_RE.exec(before);
    if (dateMatch) {
      const keyword = dateMatch[1];
      const kind = DATE_TRIGGER_MAP.get(keyword.toLowerCase());
      if (kind && !fullLine.includes(kind.emoji)) {
        const arg = dateMatch[2] ?? '';
        const completions = buildDateSuggestions(kind, arg, now);
        if (completions.length > 0) {
          const from = line.from + dateMatch.index + (dateMatch[0].startsWith(' ') || dateMatch[0].startsWith('\t') ? 1 : 0);
          return { from, options: completions, filter: false };
        }
      }
    }

    // 2. Recurrence keyword + argument (`every ...`, `cada ...`)
    const recMatch = RECURRENCE_ARG_RE.exec(before);
    if (recMatch && !hasRecurrence) {
      const arg = recMatch[2] ?? '';
      const completions = buildRecurrenceSuggestions(arg);
      if (completions.length > 0) {
        const from = line.from + recMatch.index + (/^\s/.test(recMatch[0]) ? 1 : 0);
        return { from, options: completions, filter: false };
      }
    }

    // 3. On completion (`on completion ...`)
    const compMatch = ON_COMPLETION_ARG_RE.exec(before);
    if (compMatch && !hasOnCompletion) {
      const arg = normalizeDateQuery(compMatch[2] ?? '');
      const items: Completion[] = [
        { label: '🏁 delete', detail: 'remove task when completed', apply: '🏁 delete ' },
        { label: '🏁 keep', detail: 'keep task when completed', apply: '🏁 keep ' },
      ].filter((item) => !arg || item.label.slice(2).trim().startsWith(arg));
      if (items.length > 0) {
        const from = line.from + compMatch.index + (/^\s/.test(compMatch[0]) ? 1 : 0);
        return { from, options: items, filter: false };
      }
    }

    // 4. Depends on (`depends on ...`)
    const depMatch = DEPENDS_ARG_RE.exec(before);
    if (depMatch && !hasDependsOn) {
      const arg = (depMatch[2] ?? '').toLowerCase();
      const docCandidates = extractDocTasksWithId(context.state.doc.toString());
      const remoteCandidates = options.loadTasksWithId ? await options.loadTasksWithId().catch(() => []) : [];
      const merged = new Map<string, string>();
      for (const item of [...docCandidates, ...remoteCandidates]) {
        if (!merged.has(item.id)) merged.set(item.id, item.description);
      }
      const items: Completion[] = [];
      for (const [id, description] of merged) {
        if (!arg || id.toLowerCase().includes(arg) || description.toLowerCase().includes(arg)) {
          items.push({ label: `⛔ ${id}`, detail: description, apply: `⛔ ${id} ` });
        }
      }
      if (items.length === 0 && arg) {
        items.push({ label: `⛔ ${arg}`, detail: 'depends on task ID', apply: `⛔ ${arg} ` });
      } else if (items.length === 0) {
        items.push({ label: '⛔ ', detail: 'depends on task ID', apply: '⛔ ' });
      }
      const from = line.from + depMatch.index + (/^\s/.test(depMatch[0]) ? 1 : 0);
      return { from, options: items, filter: false };
    }

    // 5. Single-word trigger prefix (3+ chars, or exact `id`)
    const wordMatch = TRAILING_WORD_RE.exec(before);
    if (!wordMatch) return null;
    const rawWord = wordMatch[1];
    const normWord = normalizeDateQuery(rawWord);
    const wordFrom = line.from + wordMatch.index + (/^\s/.test(wordMatch[0]) ? 1 : 0);
    const completions: Completion[] = [];

    if (normWord === 'id' && !hasId) {
      const id = genId();
      completions.push({ label: `🆔 ${id}`, detail: 'task ID', apply: `🆔 ${id} `, boost: 8 });
    }

    if (normWord.length >= 3) {
      for (const kind of DATE_KINDS) {
        if (fullLine.includes(kind.emoji)) continue;
        if (kind.triggers.some((t) => t.startsWith(normWord))) {
          const todayIso = formatIsoDate(now);
          const tomorrowIso = formatIsoDate(addDays(now, 1));
          completions.push(
            { label: `${kind.emoji} ${todayIso}`, detail: `${kind.key} · today`, apply: `${kind.emoji} ${todayIso} `, boost: 7 },
            { label: `${kind.emoji} ${tomorrowIso}`, detail: `${kind.key} · tomorrow`, apply: `${kind.emoji} ${tomorrowIso} `, boost: 6 },
          );
        }
      }

      if (!hasPriority) {
        for (const prio of PRIORITIES) {
          if (prio.triggers.some((t) => t.startsWith(normWord))) {
            completions.push({ label: `${prio.emoji} ${prio.label}`, apply: `${prio.emoji} `, boost: 5 });
          }
        }
      }

      if (!hasRecurrence && ['every', 'cada', 'repeat', 'recur'].some((t) => t.startsWith(normWord))) {
        completions.push(
          { label: '🔁 every day', detail: 'recurrence', apply: '🔁 every day ', boost: 4 },
          { label: '🔁 every week', detail: 'recurrence', apply: '🔁 every week ', boost: 3 },
          { label: '🔁 every weekday', detail: 'recurrence', apply: '🔁 every weekday ', boost: 2 },
          { label: '🔁 every month', detail: 'recurrence', apply: '🔁 every month ', boost: 1 },
        );
      }

      if (!hasOnCompletion) {
        if ('delete'.startsWith(normWord) || 'completion'.startsWith(normWord)) {
          completions.push({ label: '🏁 delete', detail: 'on completion', apply: '🏁 delete ', boost: 2 });
        }
        if ('keep'.startsWith(normWord) || 'completion'.startsWith(normWord)) {
          completions.push({ label: '🏁 keep', detail: 'on completion', apply: '🏁 keep ', boost: 1 });
        }
      }

      if (!hasDependsOn && ['depends', 'depende'].some((t) => t.startsWith(normWord))) {
        completions.push({ label: '⛔ depends on', detail: 'task dependency', apply: '⛔ ', boost: 2 });
      }
    }

    if (completions.length === 0) return null;
    return { from: wordFrom, options: completions, filter: false };
  };
}
