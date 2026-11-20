const ILLEGAL = /[/\\:*?"<>|[\]#^]/g;
const MAX_TITLE = 100;

/** Note title from the first H1, else the first non-empty line; front matter skipped. */
export function titleFromContent(md: string): string {
  let text = md.replace(/^﻿/, '');
  const front = text.match(/^---\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/);
  if (front) text = text.slice(front[0].length);
  const lines = text.split(/\r?\n/);
  const h1 = lines.find((line) => /^#\s+\S/.test(line));
  const raw = h1 ?? lines.find((line) => line.trim()) ?? '';
  return raw
    .replace(/^\s*(?:(?:#{1,6}|[-*+>])\s+|\d+[.)]\s+)*(?:\[.\]\s+)?/, '')
    .replace(ILLEGAL, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, MAX_TITLE)
    .trim();
}

/** First free `base.md`, `base 1.md`, `base 2.md`... inside `dir`. */
export function uniqueNotePath(dir: string, base: string, existing: Set<string>): string {
  const prefix = dir ? `${dir}/` : '';
  let path = `${prefix}${base}.md`;
  for (let n = 1; existing.has(path); n += 1) path = `${prefix}${base} ${n}.md`;
  return path;
}
