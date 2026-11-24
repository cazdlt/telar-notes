import type { Completion, CompletionContext, CompletionResult, CompletionSource } from '@codemirror/autocomplete';
import { syntaxTree } from '@codemirror/language';
import { languages } from '@codemirror/language-data';

export type CodeLanguageOption = {
  id: string;
  label: string;
};

/** Common languages prioritized in the code block selector and autocomplete. */
export const COMMON_CODE_LANGUAGES: readonly CodeLanguageOption[] = [
  { id: 'sql', label: 'sql' },
  { id: 'python', label: 'python' },
  { id: 'typescript', label: 'typescript' },
  { id: 'javascript', label: 'javascript' },
  { id: 'bash', label: 'bash' },
  { id: 'json', label: 'json' },
  { id: 'yaml', label: 'yaml' },
  { id: 'html', label: 'html' },
  { id: 'css', label: 'css' },
  { id: 'markdown', label: 'markdown' },
  { id: 'rust', label: 'rust' },
  { id: 'go', label: 'go' },
  { id: 'java', label: 'java' },
  { id: 'c', label: 'c' },
  { id: 'cpp', label: 'cpp' },
  { id: 'diff', label: 'diff' },
  { id: 'toml', label: 'toml' },
  { id: 'xml', label: 'xml' },
  { id: 'mermaid', label: 'mermaid' },
  { id: 'tasks', label: 'tasks' },
];

const FENCE_OPEN_RE = /^(\s*(?:>\s*)*(?:`{3,}|~{3,}))([a-zA-Z0-9_+-]*)$/;
const FENCE_PREFIX_RE = /^(\s*(?:>\s*)*(?:`{3,}|~{3,}))/;

type RankedLanguage = { id: string; label: string; detail?: string; boost: number };

let cachedAllLanguages: RankedLanguage[] | null = null;

function buildAllLanguages(): RankedLanguage[] {
  if (cachedAllLanguages) return cachedAllLanguages;
  const seen = new Set<string>();
  const result: RankedLanguage[] = [];

  COMMON_CODE_LANGUAGES.forEach((lang, index) => {
    seen.add(lang.id);
    result.push({ id: lang.id, label: lang.label, boost: 100 - index });
  });

  for (const desc of languages) {
    const id = (desc.alias[0] ?? desc.name).toLowerCase();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    result.push({ id, label: id, detail: desc.name !== id ? desc.name : undefined, boost: 0 });
  }

  cachedAllLanguages = result;
  return result;
}

/**
 * Returns language options for the code block header `<select>`, always including
 * a plain `code` (`""`) option and the current language if outside the common list.
 */
export function codeLanguageOptions(current?: string): CodeLanguageOption[] {
  const normalized = (current ?? '').trim().toLowerCase();
  const options: CodeLanguageOption[] = [{ id: '', label: 'code' }, ...COMMON_CODE_LANGUAGES];
  if (normalized && !options.some((opt) => opt.id === normalized)) {
    options.push({ id: normalized, label: normalized });
  }
  return options;
}

/**
 * Computes the document change required to set the language info string on a
 * fenced code opening line while preserving indentation, blockquote prefix, and fence marker.
 */
export function fenceInfoChange(
  lineText: string,
  lineFrom: number,
  newLanguage: string,
): { from: number; to: number; insert: string } | null {
  const match = FENCE_PREFIX_RE.exec(lineText);
  if (!match) return null;
  const infoFrom = lineFrom + match[1].length;
  const infoTo = lineFrom + lineText.length;
  return { from: infoFrom, to: infoTo, insert: newLanguage.trim() };
}

function isClosingFence(context: CompletionContext, lineNumber: number): boolean {
  let node: { name: string; from: number; parent: typeof node } | null =
    syntaxTree(context.state).resolveInner(context.pos, -1);
  while (node) {
    if (node.name === 'FencedCode') {
      return context.state.doc.lineAt(node.from).number < lineNumber;
    }
    node = node.parent;
  }
  return false;
}

/**
 * CodeMirror completion source for fenced code block languages right after ```` ``` ```` or `~~~`.
 */
export function codeLanguageCompletionSource(): CompletionSource {
  return (context: CompletionContext): CompletionResult | null => {
    const line = context.state.doc.lineAt(context.pos);
    const before = line.text.slice(0, context.pos - line.from);
    const match = FENCE_OPEN_RE.exec(before);
    if (!match) return null;
    if (isClosingFence(context, line.number)) return null;

    const query = match[2].toLowerCase();
    const from = context.pos - match[2].length;
    const options: Completion[] = buildAllLanguages()
      .filter((lang) => !query || lang.id.includes(query) || lang.detail?.toLowerCase().includes(query))
      .map((lang) => ({
        label: lang.id,
        detail: lang.detail,
        type: 'keyword',
        boost: lang.id.startsWith(query) ? lang.boost + 20 : lang.boost,
      }));

    if (options.length === 0) return null;
    return { from, options, validFor: /^[a-zA-Z0-9_+-]*$/ };
  };
}
