import type { Completion, CompletionContext, CompletionResult, CompletionSource } from '@codemirror/autocomplete';
import { syntaxTree } from '@codemirror/language';
import { api } from './api';
import type { TagEntry } from './types';

export type TagSuggestOptions = {
  /** Override vault tag loader (useful for deterministic tests). */
  loadTags?: () => Promise<TagEntry[]>;
};

const TAG_CACHE_TTL_MS = 30_000;
const TAG_TRIGGER_RE = /(?:^|[\s(])(#[\p{L}\p{N}_/-]*)$/u;
const DOC_TAG_RE = /(?:^|[\s(])#([\p{L}\p{N}_/-]+)/gu;
const HAS_TAG_CHAR_RE = /[\p{L}_-]/u;

let cachedTags: { at: number; tags: Promise<TagEntry[]> } | null = null;

function defaultLoadTags(): Promise<TagEntry[]> {
  if (!cachedTags || Date.now() - cachedTags.at > TAG_CACHE_TTL_MS) {
    const tags = api.tags().then((result) => result.tags);
    cachedTags = { at: Date.now(), tags };
    tags.catch(() => { cachedTags = null; });
  }
  return cachedTags.tags;
}

function insideFrontmatter(doc: string, pos: number): boolean {
  if (!doc.startsWith('---\n') && !doc.startsWith('---\r\n')) return false;
  const close = doc.indexOf('\n---', 3);
  return close === -1 || pos <= close + 4;
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

function extractDocTags(doc: string, excludeFrom: number, excludeTo: number): string[] {
  const masked = `${doc.slice(0, excludeFrom)}${' '.repeat(Math.max(0, excludeTo - excludeFrom))}${doc.slice(excludeTo)}`;
  const tags = new Set<string>();
  let match: RegExpExecArray | null;
  DOC_TAG_RE.lastIndex = 0;
  while ((match = DOC_TAG_RE.exec(masked)) !== null) {
    const cleaned = match[1].replace(/^\/+|\/+$/g, '');
    if (cleaned && HAS_TAG_CHAR_RE.test(cleaned)) tags.add(cleaned);
  }
  return [...tags];
}

/**
 * CodeMirror completion source for `#tag` autocomplete across the editor,
 * merging vault tags from `GET /api/tags` with tags present in the current document.
 */
export function tagAutoSuggest(options: TagSuggestOptions = {}): CompletionSource {
  const loadTags = options.loadTags ?? defaultLoadTags;

  return async (context: CompletionContext): Promise<CompletionResult | null> => {
    const line = context.state.doc.lineAt(context.pos);
    const before = line.text.slice(0, context.pos - line.from);
    const match = TAG_TRIGGER_RE.exec(before);
    if (!match) return null;

    const token = match[1];
    const hashFrom = context.pos - token.length;
    const docText = context.state.doc.toString();
    if (insideFrontmatter(docText, hashFrom)) return null;
    if (insideCode(context)) return null;

    const query = token.slice(1).toLowerCase();
    const vaultTags = await loadTags().catch(() => []);
    const counts = new Map<string, number>();
    for (const entry of vaultTags) counts.set(entry.tag, entry.count);
    for (const docTag of extractDocTags(docText, hashFrom, context.pos)) {
      if (!counts.has(docTag)) counts.set(docTag, 0);
    }

    const completions: Completion[] = [];
    for (const [tag, count] of counts) {
      const lower = tag.toLowerCase();
      if (query && !lower.includes(query)) continue;
      const boost = query && lower.startsWith(query) ? 20 + count : count;
      completions.push({
        label: `#${tag}`,
        detail: count > 0 ? String(count) : undefined,
        apply: `#${tag}`,
        boost,
      });
    }

    if (completions.length === 0) return null;
    completions.sort((a, b) => (b.boost ?? 0) - (a.boost ?? 0) || a.label.localeCompare(b.label));
    return { from: hashFrom, options: completions, filter: false };
  };
}
