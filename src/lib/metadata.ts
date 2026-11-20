import { parseDocument } from 'yaml';

export type NoteMetadata = {
  fields: Array<{ key: string; value: string }>;
  title?: string;
  tags: string[];
  body: string;
  words: number;
  error?: string;
};

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value)) return value.map(displayValue).join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function splitFrontmatter(content: string): { yaml: string | null; body: string } {
  const match = content.match(/^---\s*\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  if (!match) return { yaml: null, body: content };
  return { yaml: match[1], body: content.slice(match[0].length) };
}

export function parseMetadata(content: string): NoteMetadata {
  const { yaml, body } = splitFrontmatter(content);
  const words = body.trim() ? body.trim().split(/\s+/).length : 0;
  if (yaml === null) return { fields: [], tags: [], body, words };

  const document = parseDocument(yaml, { prettyErrors: true, uniqueKeys: false });
  const error = document.errors.map((item) => item.message).join('\n') || undefined;
  const value = document.toJS({ mapAsMap: false }) as unknown;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return { fields: [], tags: [], body, words, error };
  }

  const record = value as Record<string, unknown>;
  const fields = Object.entries(record).map(([key, fieldValue]) => ({ key, value: displayValue(fieldValue) }));
  const rawTags = record.tags;
  const tags = (Array.isArray(rawTags) ? rawTags : typeof rawTags === 'string' ? rawTags.split(',') : [])
    .map((tag) => displayValue(tag).replace(/^#/, '').trim())
    .filter(Boolean);
  return {
    fields,
    title: typeof record.title === 'string' ? record.title : undefined,
    tags,
    body,
    words,
    error,
  };
}
