import { CompletionContext } from '@codemirror/autocomplete';
import { markdown } from '@codemirror/lang-markdown';
import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { ObsidianGFM } from './tasks';
import { tagAutoSuggest } from './tag-suggest';

const VAULT_TAGS = [
  { tag: 'work', count: 12 },
  { tag: 'work/urgent', count: 4 },
  { tag: 'salud', count: 3 },
];

async function query(doc: string, pos = doc.length) {
  const state = EditorState.create({ doc, extensions: [markdown({ extensions: ObsidianGFM })] });
  const source = tagAutoSuggest({ loadTags: async () => VAULT_TAGS });
  const ctx = new CompletionContext(state, pos, false);
  return source(ctx);
}

describe('tagAutoSuggest', () => {
  it('suggests vault tags on `#` in tasks and regular notes', async () => {
    const taskResult = await query('- [ ] Enviar reporte #wo');
    expect(taskResult?.from).toBe('- [ ] Enviar reporte '.length);
    expect(taskResult?.options.map((o) => o.label)).toEqual(['#work', '#work/urgent']);

    const proseResult = await query('Nota sobre #sal');
    expect(proseResult?.options.map((o) => o.label)).toEqual(['#salud']);
  });

  it('includes tags written elsewhere in the current document', async () => {
    const doc = 'Primera línea #nuevo-tag\n- [ ] Tarea #nue';
    const result = await query(doc);
    expect(result?.options.map((o) => o.label)).toEqual(['#nuevo-tag']);
  });

  it('does not trigger inside headings, URLs, wikilinks, frontmatter, or code blocks', async () => {
    expect(await query('# Heading')).toBeNull();
    expect(await query('##Sub')).toBeNull();
    expect(await query('https://example.com#wo')).toBeNull();
    expect(await query('[[Note#wo')).toBeNull();
    expect(await query('---\n#wo\n---\n', 7)).toBeNull();
    expect(await query('```\n#wo\n```', 7)).toBeNull();
  });
});
